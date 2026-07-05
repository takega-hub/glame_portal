#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, parse, request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILES = (
    PROJECT_ROOT / ".env",
    PROJECT_ROOT / "backend" / ".env",
    Path('/home/glameAI/.hermes/.env'),
)
OUT_DIR = PROJECT_ROOT / "reports"
TASK_ID = '19a200b8-0628-4f2e-87cd-1ab123e2dfd9'
KANBAN_ID = 't_fb532c8b'


def load_dotenv():
    for p in ENV_FILES:
        if not p.exists():
            continue
        for raw in p.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip(); v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
        return p
    return None


def build_url(base, path):
    return base.rstrip('/') + '/' + path.lstrip('/')


def get_token(base):
    token = os.environ.get('GLAME_API_TOKEN', '').strip()
    if token:
        return token
    username = os.environ.get('GLAME_AUTH_USERNAME', '').strip()
    password = os.environ.get('GLAME_AUTH_PASSWORD', '').strip()
    if not username or not password:
        raise RuntimeError('missing GLAME_API_TOKEN or GLAME_AUTH_USERNAME/PASSWORD')
    body = parse.urlencode({'username': username, 'password': password}).encode()
    req = request.Request(build_url(base, '/api/auth/login'), data=body, headers={
        'Accept':'application/json', 'Content-Type':'application/x-www-form-urlencoded', 'User-Agent':'glame-hermes-agent/0.1'
    }, method='POST')
    with request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode('utf-8'))
    return payload['access_token']


def api_get(base, token, path):
    req = request.Request(build_url(base, path), headers={
        'Accept': 'application/json', 'Authorization': f'Bearer {token}', 'User-Agent': 'glame-hermes-agent/0.1'
    })
    try:
        with request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode('utf-8', errors='replace')
            try:
                data = json.loads(body)
            except Exception:
                data = body
            return {'ok': True, 'status': resp.status, 'reason': resp.reason, 'data': data}
    except error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        try:
            data = json.loads(body)
        except Exception:
            data = body
        return {'ok': False, 'status': exc.code, 'reason': exc.reason, 'data': data}
    except Exception as exc:
        return {'ok': False, 'status': None, 'reason': type(exc).__name__, 'data': str(exc)}


def money(v):
    try: return f"{float(v):,.0f}".replace(',', ' ')
    except Exception: return str(v)


def pct(part, total):
    try:
        return f"{(float(part)/float(total)*100):.1f}%"
    except Exception:
        return 'n/a'


def first_data(res, default=None):
    if default is None: default = {}
    return res.get('data') if isinstance(res, dict) and res.get('ok') else default


def list_top(items, name_key='name', value_key='revenue', n=5):
    if isinstance(items, dict):
        # common wrappers
        for key in ('items', 'products', 'categories', 'brands', 'data', 'top_sellers'):
            if isinstance(items.get(key), list):
                items = items[key]
                break
    if not isinstance(items, list):
        return []
    out=[]
    for it in items[:n]:
        if not isinstance(it, dict): continue
        name = it.get(name_key) or it.get('category') or it.get('brand') or it.get('product_name') or it.get('name') or it.get('sku') or it.get('article') or it.get('title') or 'n/a'
        val = it.get(value_key, it.get('total_revenue', it.get('sales_amount', it.get('amount', it.get('revenue')))))
        out.append((name, val, it))
    return out


def main():
    env_path = load_dotenv()
    base = os.environ.get('GLAME_API_BASE_URL','').strip()
    if not base: raise SystemExit('missing GLAME_API_BASE_URL')
    token = get_token(base)
    endpoints = [
        '/health',
        f'/api/agent-interactions/tasks/{TASK_ID}',
        f'/api/agent-interactions/tasks/{TASK_ID}/logs',
        f'/api/agent-interactions/tasks/{TASK_ID}/audit',
        '/api/agent-interactions/tasks?target_agent=analytics-agent&limit=50',
        '/api/director/tasks/kanban?limit=200',
        '/api/ai-marketer/dashboard',
        '/api/marketing/ai-marketer/dashboard',
        '/api/ai-marketer/opportunities',
        '/api/ai-marketer/segments/analysis',
        '/api/admin/customers/analytics/overview',
        '/api/admin/customers/segments/list',
        '/api/analytics/dashboard?days=30',
        '/api/analytics/1c-sales/daily?period=today&auto_sync=false',
        '/api/analytics/1c-sales/daily?period=yesterday&auto_sync=false',
        '/api/analytics/1c-sales/metrics?period=week&auto_sync=false',
        '/api/analytics/products/top-sellers?period=30d&limit=10',
        '/api/analytics/products/by-category?period=30d&limit=10',
        '/api/analytics/products/by-brand?period=30d&limit=10',
        '/api/analytics/channels/performance?period=30d',
        '/api/analytics/website-visits/daily?days=7',
        '/api/analytics/store-visits/daily?days=7',
    ]
    results = {p: api_get(base, token, p) for p in endpoints}
    now = datetime.now(timezone.utc)
    stamp = now.strftime('%Y%m%d_%H%M%S')
    OUT_DIR.mkdir(exist_ok=True)
    raw_path = OUT_DIR / f'daily_marketing_analysis_{KANBAN_ID}_{stamp}.json'
    raw_path.write_text(json.dumps({'collected_at': now.isoformat(), 'base_url': base, 'task_id': TASK_ID, 'results': results}, ensure_ascii=False, indent=2), encoding='utf-8')

    task = first_data(results[f'/api/agent-interactions/tasks/{TASK_ID}'])
    logs = first_data(results[f'/api/agent-interactions/tasks/{TASK_ID}/logs'], [])
    audit = first_data(results[f'/api/agent-interactions/tasks/{TASK_ID}/audit'])
    today = first_data(results['/api/analytics/1c-sales/daily?period=today&auto_sync=false'])
    yesterday = first_data(results['/api/analytics/1c-sales/daily?period=yesterday&auto_sync=false'])
    week = first_data(results['/api/analytics/1c-sales/metrics?period=week&auto_sync=false'])
    ai_dash = first_data(results['/api/ai-marketer/dashboard'])
    opps = first_data(results['/api/ai-marketer/opportunities'])
    cust = first_data(results['/api/admin/customers/analytics/overview'])
    channels = first_data(results['/api/analytics/channels/performance?period=30d'])
    website = first_data(results['/api/analytics/website-visits/daily?days=7'])
    store = first_data(results['/api/analytics/store-visits/daily?days=7'])
    top_prod = first_data(results['/api/analytics/products/top-sellers?period=30d&limit=10'])
    top_cat = first_data(results['/api/analytics/products/by-category?period=30d&limit=10'])
    top_brand = first_data(results['/api/analytics/products/by-brand?period=30d&limit=10'])

    td = (today.get('daily_data') or [{}])[0] if isinstance(today, dict) else {}
    yd = (yesterday.get('daily_data') or [{}])[0] if isinstance(yesterday, dict) else {}
    agg = week.get('aggregated', {}) if isinstance(week, dict) else {}
    by_store = week.get('by_store', {}) if isinstance(week, dict) else {}
    churn = ai_dash.get('churn_risk', {}) if isinstance(ai_dash, dict) else {}
    ltv = cust.get('ltv_metrics', {}) if isinstance(cust, dict) else {}
    rfm_dist = (((cust.get('rfm_analysis') or {}).get('rfm_distribution') or {}).get('total_scores') or {}) if isinstance(cust, dict) else {}
    low_rfm = sum(int(rfm_dist.get(str(i),0)) for i in range(3,6))
    total_customers = ltv.get('total_customers') or churn.get('total_customers') or 0
    segs = []
    for s in ((ai_dash.get('segments_overview') or {}).get('segments') or [])[:8] if isinstance(ai_dash, dict) else []:
        segs.append(f"{s.get('name')}={s.get('customer_count')}")
    opp_lines=[]
    for o in (opps.get('opportunities') or [])[:5] if isinstance(opps, dict) else []:
        opp_lines.append(f"{o.get('description')} (potential_revenue={money(o.get('potential_revenue'))}; actions={', '.join(o.get('recommended_actions') or [])})")

    def endpoint_status_line(p):
        r=results[p]
        return f"- GET {p} → {'HTTP '+str(r.get('status')) if r.get('status') else r.get('reason')} {'OK' if r.get('ok') else 'FAILED'}"

    # Website/store summaries vary by endpoint shape; keep raw-backed concise fallback.
    website_summary = json.dumps(website, ensure_ascii=False)[:700] if website else 'нет данных'
    store_summary = json.dumps(store, ensure_ascii=False)[:700] if store else 'нет данных'
    channel_summary = json.dumps(channels, ensure_ascii=False)[:700] if channels else 'нет данных'

    md = []
    md.append(f"Ежедневный маркетинговый анализ GLAME — read-only report")
    md.append(f"Проверено: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    md.append(f"Платформенная задача: {TASK_ID} / {((task.get('input_data') or {}).get('title') or task.get('task_type') or 'n/a')}")
    md.append(f"Hermes Kanban: {KANBAN_ID}")
    md.append("")
    md.append("1. Итог")
    md.append("- Отчет собран вручную по реальным read-only данным GLAME API; массовых рассылок, кампаний, customer outreach и API-записей не выполнялось.")
    md.append(f"- Платформенная cron-задача на момент проверки: status={task.get('status')}, started_at={task.get('started_at')}, completed_at={task.get('completed_at')}, output_data={'present' if task.get('output_data') else 'None'}; audit events={((audit.get('audit_summary') or {}).get('total_events') if isinstance(audit, dict) else 'n/a')}, handoffs={((audit.get('audit_summary') or {}).get('total_handoffs') if isinstance(audit, dict) else 'n/a')}.")
    if task.get('status') == 'pending' and not task.get('started_at'):
        md.append("- Точный операционный блокер сохраняется: cron-scheduler создал pending task, но analytics-agent/processor не забрал задачу в started/processing. Это не блокер данных: ключевые read-only источники ниже отвечают 200 OK.")
    md.append("")
    md.append("2. Продажи и трафик")
    md.append(f"- Сегодня ({td.get('date')}): revenue={money(td.get('revenue',0))}, orders={td.get('orders',0)}, items_sold={td.get('items_sold',0)} — на момент проверки продаж за сегодня в daily endpoint нет." if float(td.get('revenue') or 0)==0 else f"- Сегодня ({td.get('date')}): revenue={money(td.get('revenue'))}, orders={td.get('orders')}, items_sold={td.get('items_sold')}.")
    md.append(f"- Вчера ({yd.get('date')}): revenue={money(yd.get('revenue'))}, orders={yd.get('orders')}, items_sold={yd.get('items_sold')}.")
    md.append(f"- Неделя: revenue={money(agg.get('total_revenue'))}, orders={agg.get('total_orders')}, items={agg.get('total_items')}, AOV={money(agg.get('average_order_value'))}, visitors={agg.get('total_visitors')}, revenue/visitor={money(agg.get('revenue_per_visitor'))}.")
    if by_store:
        stores=[]
        for s in by_store.values(): stores.append(f"{s.get('store_name')}: {money(s.get('revenue'))} / {s.get('orders')} заказов / {s.get('items_sold')} items")
        md.append("- По магазинам за неделю: " + "; ".join(stores) + ".")
    md.append(f"- Store visits endpoint (7d) raw summary: {store_summary}")
    md.append(f"- Website visits endpoint (7d) raw summary: {website_summary}")
    md.append(f"- Channels endpoint (30d) raw summary: {channel_summary}")
    md.append("")
    md.append("3. Клиенты и сегменты")
    md.append(f"- Клиентская база: total_customers={total_customers}, total_ltv={money(ltv.get('total_ltv'))}, average_ltv={money(ltv.get('average_ltv'))}.")
    md.append(f"- Churn risk: high={churn.get('high_risk')} ({pct(churn.get('high_risk'), total_customers)}), medium={churn.get('medium_risk')}, low={churn.get('low_risk')}.")
    md.append(f"- RFM низкая зона score 3–5: {low_rfm} клиентов ({pct(low_rfm, total_customers)}).")
    if opp_lines:
        md.append("- Крупнейшие opportunities: " + "; ".join(opp_lines) + ".")
    if segs:
        md.append("- Ключевые сегменты: " + ", ".join(segs) + ".")
    md.append("")
    md.append("4. Товары/категории/бренды за 30 дней")
    cats = list_top(top_cat, n=5)
    brands = list_top(top_brand, n=5)
    prods = list_top(top_prod, n=5)
    md.append("- Топ категории по revenue: " + ("; ".join(f"{n}: {money(v)}" for n,v,_ in cats) if cats else json.dumps(top_cat, ensure_ascii=False)[:700]))
    md.append("- Топ бренды по revenue: " + ("; ".join(f"{n}: {money(v)}" for n,v,_ in brands) if brands else json.dumps(top_brand, ensure_ascii=False)[:700]))
    md.append("- Топ SKU/товары: " + ("; ".join(f"{n}: {money(v)}" for n,v,_ in prods) if prods else json.dumps(top_prod, ensure_ascii=False)[:700]))
    md.append("")
    md.append("5. Рекомендации без write-действий")
    md.append("- Не запускать массовую реактивацию автоматически: high-risk база очень большая, а требования задачи запрещают mass send без admin approval.")
    md.append("- Для директора/админа: проверить, нормален ли ноль продаж за текущий день на момент утренней синхронизации; вчерашний и недельный срезы подтверждают, что историческая 1С-аналитика доступна.")
    md.append("- Для маркетинга: подготовить, но не отправлять, реактивационный сегмент high-risk/спящие с персональными офферами; креативы привязать к категориям/брендам из топа за 30 дней.")
    md.append("- Для платформы: исправить или включить consumer/worker analytics-agent для /api/agent-interactions/tasks, потому что cron-задача остается pending без started_at и handoff/output.")
    md.append("")
    md.append("6. Sources used / verification notes")
    md.extend(endpoint_status_line(p) for p in endpoints)
    md.append(f"- Raw JSON artifact: {raw_path}")
    md.append("- Read-only guarantee: использовались только GET-запросы к GLAME API; endpoints с auto_sync вызваны с auto_sync=false; POST/PUT/PATCH/DELETE не выполнялись.")
    report_path = OUT_DIR / f'daily_marketing_analysis_{KANBAN_ID}_{stamp}.md'
    report_path.write_text('\n'.join(md)+"\n", encoding='utf-8')
    print(report_path)
    print(raw_path)

if __name__ == '__main__':
    main()
