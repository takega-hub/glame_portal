"""
Аналитика комплектов украшений по чекам из 1С.

Скрипт группирует строки продаж в чеки и строит простые association rules:
какие изделия чаще покупают вместе, насколько сочетание сильнее случайного,
и какие категории хорошо работают друг с другом.

Использование:
  cd backend
  python3 analyze_receipt_bundles.py
  python3 analyze_receipt_bundles.py --source sales-records --days 365
  python3 analyze_receipt_bundles.py --min-pair-support 3 --min-confidence 0.08
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import func, select

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.connection import AsyncSessionLocal
from app.models.purchase_history import PurchaseHistory
from app.models.sales_record import SalesRecord


@dataclass(frozen=True)
class ReceiptItem:
    key: str
    article: str | None
    product_id_1c: str | None
    name: str | None
    category: str | None
    brand: str | None
    quantity: float
    amount: float


@dataclass(frozen=True)
class ProductPairRule:
    left_key: str
    right_key: str
    left_name: str | None
    right_name: str | None
    left_article: str | None
    right_article: str | None
    left_category: str | None
    right_category: str | None
    pair_receipts: int
    left_receipts: int
    right_receipts: int
    total_receipts: int
    support: float
    confidence_left_to_right: float
    confidence_right_to_left: float
    lift: float
    jaccard: float
    score: float


@dataclass(frozen=True)
class CategoryPairRule:
    left_category: str
    right_category: str
    pair_receipts: int
    left_receipts: int
    right_receipts: int
    total_receipts: int
    support: float
    confidence_left_to_right: float
    confidence_right_to_left: float
    lift: float
    score: float


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def product_key(article: Any, product_id_1c: Any, name: Any) -> str | None:
    article_text = clean_text(article)
    if article_text:
        return f"article:{article_text.lower()}"

    product_id_text = clean_text(product_id_1c)
    if product_id_text:
        return f"1c:{product_id_text.lower()}"

    name_text = clean_text(name)
    if name_text:
        return f"name:{name_text.lower()}"

    return None


def pairwise_sorted(values: Iterable[str]) -> Iterable[tuple[str, str]]:
    ordered = sorted(set(values))
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            yield left, right


def compatibility_score(pair_count: int, confidence: float, lift: float, jaccard: float) -> float:
    frequency_part = min(math.log1p(pair_count) / math.log1p(50), 1.0)
    lift_part = min(max((lift - 1.0) / 4.0, 0.0), 1.0)
    return round(
        (confidence * 0.38)
        + (lift_part * 0.34)
        + (frequency_part * 0.18)
        + (jaccard * 0.10),
        4,
    )


async def count_source_rows(source: str) -> int:
    async with AsyncSessionLocal() as db:
        if source == "purchase-history":
            stmt = select(func.count()).select_from(PurchaseHistory).where(
                PurchaseHistory.document_id_1c.isnot(None)
            )
        else:
            stmt = select(func.count()).select_from(SalesRecord).where(
                (SalesRecord.document_id.isnot(None)) | (SalesRecord.external_id.isnot(None))
            )
        result = await db.execute(stmt)
        return int(result.scalar() or 0)


async def choose_source(requested: str) -> str:
    if requested != "auto":
        return requested

    purchase_rows = await count_source_rows("purchase-history")
    if purchase_rows:
        return "purchase-history"
    return "sales-records"


async def load_receipts(source: str, days: int | None) -> dict[str, list[ReceiptItem]]:
    cutoff = None
    if days and days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    receipts: dict[str, list[ReceiptItem]] = defaultdict(list)

    async with AsyncSessionLocal() as db:
        if source == "purchase-history":
            stmt = select(
                PurchaseHistory.document_id_1c,
                PurchaseHistory.product_article,
                PurchaseHistory.product_id_1c,
                PurchaseHistory.product_name,
                PurchaseHistory.category,
                PurchaseHistory.brand,
                PurchaseHistory.quantity,
                PurchaseHistory.total_amount,
                PurchaseHistory.purchase_date,
            ).where(PurchaseHistory.document_id_1c.isnot(None))
            if cutoff:
                stmt = stmt.where(PurchaseHistory.purchase_date >= cutoff)
        else:
            stmt = select(
                func.coalesce(SalesRecord.document_id, SalesRecord.external_id),
                SalesRecord.product_article,
                SalesRecord.product_id,
                SalesRecord.product_name,
                SalesRecord.product_category,
                SalesRecord.product_brand,
                SalesRecord.quantity,
                SalesRecord.revenue,
                SalesRecord.sale_date,
            ).where((SalesRecord.document_id.isnot(None)) | (SalesRecord.external_id.isnot(None)))
            if cutoff:
                stmt = stmt.where(SalesRecord.sale_date >= cutoff)

        result = await db.execute(stmt)

    for row in result.all():
        document_id, article, product_id_1c, name, category, brand, quantity, amount, _date = row
        receipt_id = clean_text(document_id)
        key = product_key(article, product_id_1c, name)
        if not receipt_id or not key:
            continue

        receipts[receipt_id].append(
            ReceiptItem(
                key=key,
                article=clean_text(article),
                product_id_1c=clean_text(product_id_1c),
                name=clean_text(name),
                category=clean_text(category),
                brand=clean_text(brand),
                quantity=float(quantity or 0),
                amount=float(amount or 0),
            )
        )

    return receipts


def compile_exclude_pattern(pattern: str | None) -> re.Pattern[str] | None:
    if not pattern:
        return None
    return re.compile(pattern, re.IGNORECASE)


def filter_receipts(
    receipts: dict[str, list[ReceiptItem]],
    exclude_name_pattern: re.Pattern[str] | None,
    exclude_categories: set[str],
) -> dict[str, list[ReceiptItem]]:
    if not exclude_name_pattern and not exclude_categories:
        return receipts

    filtered: dict[str, list[ReceiptItem]] = {}
    for receipt_id, items in receipts.items():
        kept_items: list[ReceiptItem] = []
        for item in items:
            name = item.name or ""
            category = (item.category or "").lower()
            if exclude_name_pattern and exclude_name_pattern.search(name):
                continue
            if category and category in exclude_categories:
                continue
            kept_items.append(item)
        if kept_items:
            filtered[receipt_id] = kept_items
    return filtered


def collapse_receipt_items(items: list[ReceiptItem]) -> dict[str, ReceiptItem]:
    collapsed: dict[str, ReceiptItem] = {}
    for item in items:
        existing = collapsed.get(item.key)
        if not existing:
            collapsed[item.key] = item
            continue

        collapsed[item.key] = ReceiptItem(
            key=item.key,
            article=existing.article or item.article,
            product_id_1c=existing.product_id_1c or item.product_id_1c,
            name=existing.name or item.name,
            category=existing.category or item.category,
            brand=existing.brand or item.brand,
            quantity=existing.quantity + item.quantity,
            amount=existing.amount + item.amount,
        )
    return collapsed


def build_product_rules(
    receipts: dict[str, list[ReceiptItem]],
    min_pair_support: int,
    min_confidence: float,
    limit: int,
) -> tuple[list[ProductPairRule], dict[str, Any]]:
    item_receipts: Counter[str] = Counter()
    pair_receipts: Counter[tuple[str, str]] = Counter()
    item_examples: dict[str, ReceiptItem] = {}
    receipt_sizes: Counter[int] = Counter()
    total_revenue = 0.0

    usable_receipts = 0
    multi_item_receipts = 0

    for raw_items in receipts.values():
        items_by_key = collapse_receipt_items(raw_items)
        if not items_by_key:
            continue

        usable_receipts += 1
        receipt_sizes[len(items_by_key)] += 1
        total_revenue += sum(item.amount for item in items_by_key.values())

        for key, item in items_by_key.items():
            item_receipts[key] += 1
            item_examples.setdefault(key, item)

        if len(items_by_key) < 2:
            continue

        multi_item_receipts += 1
        for pair in pairwise_sorted(items_by_key.keys()):
            pair_receipts[pair] += 1

    rules: list[ProductPairRule] = []
    for (left_key, right_key), pair_count in pair_receipts.items():
        if pair_count < min_pair_support:
            continue

        left_count = item_receipts[left_key]
        right_count = item_receipts[right_key]
        if not left_count or not right_count or not usable_receipts:
            continue

        support = pair_count / usable_receipts
        confidence_lr = pair_count / left_count
        confidence_rl = pair_count / right_count
        confidence = max(confidence_lr, confidence_rl)
        if confidence < min_confidence:
            continue

        lift = pair_count * usable_receipts / (left_count * right_count)
        union_count = left_count + right_count - pair_count
        jaccard = pair_count / union_count if union_count else 0.0
        left = item_examples[left_key]
        right = item_examples[right_key]

        rules.append(
            ProductPairRule(
                left_key=left_key,
                right_key=right_key,
                left_name=left.name,
                right_name=right.name,
                left_article=left.article,
                right_article=right.article,
                left_category=left.category,
                right_category=right.category,
                pair_receipts=pair_count,
                left_receipts=left_count,
                right_receipts=right_count,
                total_receipts=usable_receipts,
                support=round(support, 6),
                confidence_left_to_right=round(confidence_lr, 6),
                confidence_right_to_left=round(confidence_rl, 6),
                lift=round(lift, 4),
                jaccard=round(jaccard, 6),
                score=compatibility_score(pair_count, confidence, lift, jaccard),
            )
        )

    rules.sort(key=lambda item: (item.score, item.pair_receipts, item.lift), reverse=True)

    summary = {
        "total_receipts": usable_receipts,
        "multi_item_receipts": multi_item_receipts,
        "multi_item_receipt_share": round(multi_item_receipts / usable_receipts, 4)
        if usable_receipts
        else 0,
        "unique_products": len(item_receipts),
        "candidate_pairs": len(pair_receipts),
        "rules": min(len(rules), limit),
        "avg_receipt_revenue": round(total_revenue / usable_receipts, 2) if usable_receipts else 0,
        "receipt_size_distribution": dict(sorted(receipt_sizes.items())),
    }
    return rules[:limit], summary


def build_category_rules(
    receipts: dict[str, list[ReceiptItem]],
    min_pair_support: int,
    limit: int,
) -> list[CategoryPairRule]:
    category_receipts: Counter[str] = Counter()
    category_pairs: Counter[tuple[str, str]] = Counter()
    total_receipts = 0

    for raw_items in receipts.values():
        items_by_key = collapse_receipt_items(raw_items)
        categories = {
            item.category.strip()
            for item in items_by_key.values()
            if item.category and item.category.strip()
        }
        if not categories:
            continue

        total_receipts += 1
        for category in categories:
            category_receipts[category] += 1
        for pair in pairwise_sorted(categories):
            category_pairs[pair] += 1

    rules: list[CategoryPairRule] = []
    for (left, right), pair_count in category_pairs.items():
        if pair_count < min_pair_support:
            continue
        left_count = category_receipts[left]
        right_count = category_receipts[right]
        confidence_lr = pair_count / left_count
        confidence_rl = pair_count / right_count
        lift = pair_count * total_receipts / (left_count * right_count)
        confidence = max(confidence_lr, confidence_rl)
        rules.append(
            CategoryPairRule(
                left_category=left,
                right_category=right,
                pair_receipts=pair_count,
                left_receipts=left_count,
                right_receipts=right_count,
                total_receipts=total_receipts,
                support=round(pair_count / total_receipts, 6) if total_receipts else 0,
                confidence_left_to_right=round(confidence_lr, 6),
                confidence_right_to_left=round(confidence_rl, 6),
                lift=round(lift, 4),
                score=compatibility_score(pair_count, confidence, lift, pair_count / total_receipts),
            )
        )

    rules.sort(key=lambda item: (item.score, item.pair_receipts, item.lift), reverse=True)
    return rules[:limit]


def write_csv(path: Path, rows: list[Any]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames = list(asdict(rows[0]).keys())
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_outputs(
    output_dir: Path,
    source: str,
    days: int | None,
    summary: dict[str, Any],
    product_rules: list[ProductPairRule],
    category_rules: list[CategoryPairRule],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base_name = f"receipt_bundles_{source}_{suffix}"

    json_path = output_dir / f"{base_name}.json"
    product_csv_path = output_dir / f"{base_name}_product_pairs.csv"
    category_csv_path = output_dir / f"{base_name}_category_pairs.csv"

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "period_days": days,
        "summary": summary,
        "product_pairs": [asdict(rule) for rule in product_rules],
        "category_pairs": [asdict(rule) for rule in category_rules],
    }

    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(product_csv_path, product_rules)
    write_csv(category_csv_path, category_rules)

    return {
        "json": str(json_path),
        "product_csv": str(product_csv_path),
        "category_csv": str(category_csv_path),
    }


async def analyze(args: argparse.Namespace) -> None:
    source = await choose_source(args.source)
    receipts = await load_receipts(source, args.days)
    receipts = filter_receipts(
        receipts,
        exclude_name_pattern=compile_exclude_pattern(args.exclude_name_regex),
        exclude_categories={item.lower() for item in args.exclude_category},
    )
    product_rules, summary = build_product_rules(
        receipts=receipts,
        min_pair_support=args.min_pair_support,
        min_confidence=args.min_confidence,
        limit=args.limit,
    )
    category_rules = build_category_rules(
        receipts=receipts,
        min_pair_support=args.min_category_pair_support,
        limit=args.limit,
    )

    paths = write_outputs(
        output_dir=Path(args.output_dir),
        source=source,
        days=args.days,
        summary=summary,
        product_rules=product_rules,
        category_rules=category_rules,
    )

    print("=" * 88)
    print("АНАЛИТИКА КОМПЛЕКТОВ ПО ЧЕКАМ")
    print("=" * 88)
    print(f"Источник: {source}")
    print(f"Период: {'все данные' if not args.days else f'последние {args.days} дней'}")
    print(f"Чеков: {summary['total_receipts']}")
    print(f"Чеков с 2+ изделиями: {summary['multi_item_receipts']} ({summary['multi_item_receipt_share']:.1%})")
    print(f"Уникальных изделий: {summary['unique_products']}")
    print(f"Найдено продуктовых правил: {len(product_rules)}")
    print(f"Найдено правил категорий: {len(category_rules)}")
    print()
    print("Топ сочетаний:")
    for rule in product_rules[:10]:
        print(
            f"  {rule.score:.3f} | {rule.pair_receipts} чеков | lift {rule.lift:.2f} | "
            f"{rule.left_article or '-'} {rule.left_name or '-'} + "
            f"{rule.right_article or '-'} {rule.right_name or '-'}"
        )
    print()
    print("Файлы:")
    for label, path in paths.items():
        print(f"  {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Аналитика комплектов украшений по чекам из 1С")
    parser.add_argument(
        "--source",
        choices=["auto", "purchase-history", "sales-records"],
        default="auto",
        help="Таблица-источник. auto сначала пробует purchase_history.",
    )
    parser.add_argument("--days", type=int, default=730, help="Период анализа в днях. 0 = все данные.")
    parser.add_argument("--min-pair-support", type=int, default=3, help="Минимум чеков для пары изделий.")
    parser.add_argument(
        "--min-category-pair-support",
        type=int,
        default=3,
        help="Минимум чеков для пары категорий.",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.03,
        help="Минимальная confidence хотя бы в одном направлении.",
    )
    parser.add_argument("--limit", type=int, default=300, help="Сколько правил сохранить по каждому типу.")
    parser.add_argument("--output-dir", default="data/receipt_bundle_analysis", help="Куда сохранить файлы.")
    parser.add_argument(
        "--exclude-name-regex",
        default=r"короб|пакет|мешоч|салфет|доставк|сертификат|упаков",
        help="Regex для исключения служебных позиций по названию. Пустая строка отключает фильтр.",
    )
    parser.add_argument(
        "--exclude-category",
        action="append",
        default=[],
        help="Категория для исключения. Можно передать несколько раз.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.days <= 0:
        args.days = None
    asyncio.run(analyze(args))


if __name__ == "__main__":
    main()
