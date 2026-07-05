#!/usr/bin/env python3
"""Read-only GLAME catalog quality audit.

Fetches /api/products/paged and reports systemic release blockers:
missing photos/descriptions, bad categories, brand/spec mismatches, active zero-stock
products, and non-client HTML/meta descriptions.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib import error, parse, request

ROOT = Path('/root/glame-platform')
PRODUCT_IMAGE_ROOT = ROOT / 'backend' / 'static' / 'product_images'
ENV_FILE = Path('/home/glameAI/.hermes/.env')

EXPECTED_CATEGORY_HINTS = {
    'колье', 'серьги', 'кольца', 'браслеты', 'подвески', 'цепи', 'каффы',
    'броши', 'чокеры', 'анклеты', 'украшения', 'комплекты', 'сумки',
    'аксессуары', 'сопутствующие материалы', 'подарочные сертификаты',
    'обручи', 'заколки', 'ремни', 'очки', 'шармы', 'цепочки', 'кольца для',
}

BRAND_ALIASES = {
    'WRINKLES OG TIME': 'WRINKLES OF TIME',
    'WRINKLES OF TIME': 'WRINKLES OF TIME',
}


def load_env() -> None:
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def norm(s: object) -> str:
    if s is None:
        return ''
    text = unicodedata.normalize('NFKC', str(s)).strip().upper().replace('Ё', 'Е')
    text = re.sub(r'\s+', ' ', text)
    return BRAND_ALIASES.get(text, text)


def url(path: str, params: dict[str, object] | None = None) -> str:
    base = os.environ['GLAME_API_BASE_URL'].rstrip('/')
    u = base + '/' + path.lstrip('/')
    if params:
        u += '?' + parse.urlencode(params)
    return u


def login_for_token() -> str:
    username = os.environ.get('GLAME_AUTH_USERNAME', '').strip()
    password = os.environ.get('GLAME_AUTH_PASSWORD', '').strip()
    if not username or not password:
        return ''
    body = parse.urlencode({'username': username, 'password': password}).encode()
    req = request.Request(
        url('/api/auth/login'),
        data=body,
        headers={
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'glame-catalog-audit/1.0',
        },
        method='POST',
    )
    with request.urlopen(req, timeout=60) as resp:
        return str(json.loads(resp.read().decode('utf-8')).get('access_token') or '').strip()


def get_token() -> str:
    token = os.environ.get('GLAME_API_TOKEN', '').strip()
    return token or login_for_token()


def get_json(path: str, params: dict[str, object] | None = None) -> dict:
    token = get_token()
    req = request.Request(
        url(path, params),
        headers={'Accept': 'application/json', 'Authorization': f'Bearer {token}', 'User-Agent': 'glame-catalog-audit/1.0'},
        method='GET',
    )
    with request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode('utf-8'))


def fetch_all(limit: int = 100) -> list[dict]:
    first = get_json('/api/products/paged', {'skip': 0, 'limit': limit})
    items = list(first.get('items') or [])
    total = int(first.get('total') or len(items))
    for skip in range(limit, total, limit):
        page = get_json('/api/products/paged', {'skip': skip, 'limit': limit})
        items.extend(page.get('items') or [])
    return items


def clean_text(value: object) -> str:
    if not value:
        return ''
    text = str(value).strip()
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def image_exists(path: str) -> bool:
    if not path:
        return False
    if path.startswith('/static/product_images/'):
        return (PRODUCT_IMAGE_ROOT / path.rsplit('/', 1)[-1]).exists()
    return True  # external/unknown path; API presence is still a photo reference


def sample(items, n=12):
    return [
        {
            'id': p.get('id'),
            'article': p.get('article'),
            'name': p.get('name'),
            'brand': p.get('brand'),
            'category': p.get('category'),
            'stock': p.get('stock'),
        }
        for p in items[:n]
    ]


def main() -> int:
    load_env()
    if not os.environ.get('GLAME_API_BASE_URL') or not (os.environ.get('GLAME_API_TOKEN') or (os.environ.get('GLAME_AUTH_USERNAME') and os.environ.get('GLAME_AUTH_PASSWORD'))):
        print('Missing GLAME_API_BASE_URL and auth token/credentials', file=sys.stderr)
        return 2

    products = fetch_all()
    active = [p for p in products if p.get('is_active') is True]

    brands = {norm(p.get('brand')) for p in products if norm(p.get('brand'))}
    spec_brands = {norm((p.get('specifications') or {}).get('Бренд')) for p in products if norm((p.get('specifications') or {}).get('Бренд'))}
    known_brands = brands | spec_brands

    no_images = []
    missing_image_files = []
    no_description = []
    html_or_meta = []
    raw_meta = []
    markdown = []
    active_zero_stock = []
    brand_spec_mismatch = []
    brand_as_category = []
    suspicious_category = []
    variant_base_orphans = []
    quantity_stock_mismatch = []
    ai_seo_tone = []

    cats = Counter()
    active_cats = Counter()

    for p in products:
        specs = p.get('specifications') or {}
        cat = (p.get('category') or '').strip()
        cats[cat or '<empty>'] += 1
        if p.get('is_active') is True:
            active_cats[cat or '<empty>'] += 1

        images = p.get('images') if isinstance(p.get('images'), list) else []
        if not images:
            no_images.append(p)
        else:
            missing = [x for x in images if isinstance(x, str) and not image_exists(x)]
            if missing:
                q = dict(p)
                q['_missing_images'] = missing
                missing_image_files.append(q)

        desc_raw = (p.get('description') or '') + '\n' + (p.get('full_description') or '')
        desc_clean = clean_text(p.get('description')) or clean_text(p.get('full_description'))
        if not desc_clean:
            no_description.append(p)
        if re.search(r'<\s*(meta|h1|h2|h3|p|strong|ul|li|br)\b', desc_raw, re.I):
            html_or_meta.append(p)
        if re.search(r'<\s*meta\b|meta name=|keywords|description" content=', desc_raw, re.I):
            raw_meta.append(p)
        if re.search(r'(^|\n)\s*[-*]\s+|\*\*', desc_raw):
            markdown.append(p)
        if re.search(r'купите|купить|ключев(ые|ые) слова|meta name|seo|выберите свои|роскошн|в золоте и серебре', desc_raw, re.I):
            ai_seo_tone.append(p)

        if p.get('is_active') is True and float(p.get('stock') or 0) <= 0:
            active_zero_stock.append(p)

        b = norm(p.get('brand'))
        sb = norm(specs.get('Бренд'))
        if b and sb and b != sb:
            q = dict(p)
            q['_spec_brand'] = specs.get('Бренд')
            brand_spec_mismatch.append(q)

        ncat = norm(cat)
        if ncat and ncat in known_brands:
            brand_as_category.append(p)
        elif cat and not any(h in cat.lower() for h in EXPECTED_CATEGORY_HINTS):
            suspicious_category.append(p)

        stock = float(p.get('stock') or 0)
        qty = specs.get('quantity')
        if isinstance(qty, (int, float)) and abs(stock - float(qty)) > 0.01:
            quantity_stock_mismatch.append(p)

        if p.get('is_active') is True and specs.get('parent_external_id') and not images:
            variant_base_orphans.append(p)

    # Group brand/spec mismatches and brand-as-category for clearer systemic classes.
    mismatch_groups = Counter((norm(p.get('brand')), norm((p.get('specifications') or {}).get('Бренд'))) for p in brand_spec_mismatch)
    brand_category_groups = Counter((p.get('category') or '<empty>', p.get('brand') or '<empty>') for p in brand_as_category)

    report = {
        'total_products': len(products),
        'active_products': len(active),
        'category_count': len(cats),
        'top_categories': cats.most_common(30),
        'top_active_categories': active_cats.most_common(30),
        'counts': {
            'no_images_all': len(no_images),
            'no_images_active': sum(1 for p in no_images if p.get('is_active') is True),
            'missing_local_image_files_all': len(missing_image_files),
            'no_description_all': len(no_description),
            'no_description_active': sum(1 for p in no_description if p.get('is_active') is True),
            'html_or_heading_tags_all': len(html_or_meta),
            'raw_meta_seo_tags_all': len(raw_meta),
            'markdown_markup_all': len(markdown),
            'ai_seo_tone_all': len(ai_seo_tone),
            'brand_as_category_all': len(brand_as_category),
            'suspicious_category_all': len(suspicious_category),
            'brand_spec_mismatch_all': len(brand_spec_mismatch),
            'active_zero_stock': len(active_zero_stock),
            'quantity_stock_mismatch_all': len(quantity_stock_mismatch),
        },
        'mismatch_groups_top': [{'brand': a, 'spec_brand': b, 'count': c} for (a, b), c in mismatch_groups.most_common(20)],
        'brand_category_groups_top': [{'category': a, 'brand': b, 'count': c} for (a, b), c in brand_category_groups.most_common(20)],
        'samples': {
            'no_images_active': sample([p for p in no_images if p.get('is_active') is True], 15),
            'no_description_active': sample([p for p in no_description if p.get('is_active') is True], 15),
            'raw_meta': sample(raw_meta, 15),
            'brand_as_category': sample(brand_as_category, 20),
            'brand_spec_mismatch': [dict(sample([p], 1)[0], spec_brand=p.get('_spec_brand')) for p in brand_spec_mismatch[:20]],
            'active_zero_stock': sample(active_zero_stock, 20),
            'missing_local_image_files': [dict(sample([p], 1)[0], missing_images=p.get('_missing_images')) for p in missing_image_files[:15]],
            'quantity_stock_mismatch': [dict(sample([p], 1)[0], spec_quantity=(p.get('specifications') or {}).get('quantity')) for p in quantity_stock_mismatch[:20]],
        },
    }

    out = ROOT / 'reports' / 'catalog_quality_audit_t_a7a4c3ce.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    # Print a compact human-readable digest for task handoff.
    print(json.dumps({
        'report_path': str(out),
        'total_products': report['total_products'],
        'active_products': report['active_products'],
        'counts': report['counts'],
        'top_category_anomalies': report['brand_category_groups_top'][:10],
        'top_brand_mismatches': report['mismatch_groups_top'][:10],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
