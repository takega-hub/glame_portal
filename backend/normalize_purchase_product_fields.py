"""
Нормализация категорий и брендов в истории покупок.

Использование:
  cd backend
  python3 normalize_purchase_product_fields.py
  python3 normalize_purchase_product_fields.py --phone 79787566405
  python3 normalize_purchase_product_fields.py --dry-run
"""
import argparse
import asyncio
import os
import re
import sys
from collections import Counter
from typing import Optional

from sqlalchemy import or_, select

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.connection import AsyncSessionLocal
from app.models.product import Product
from app.models.purchase_history import PurchaseHistory
from app.models.user import User
from app.services.purchase_product_fields import derive_purchase_brand, derive_purchase_category


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 11 and digits.startswith("8"):
        return "7" + digits[1:]
    if len(digits) == 10:
        return "7" + digits
    return digits


async def normalize_all(phone: Optional[str], dry_run: bool) -> None:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(PurchaseHistory, Product.category, Product.brand)
            .outerjoin(Product, PurchaseHistory.product_id == Product.id)
            .order_by(PurchaseHistory.purchase_date.desc())
        )

        if phone:
            normalized = normalize_phone(phone)
            user_result = await db.execute(
                select(User.id).where(
                    User.is_customer == True,
                    or_(User.phone == normalized, User.discount_card_number == normalized),
                )
            )
            user_id = user_result.scalar_one_or_none()
            if not user_id:
                raise RuntimeError(f"Покупатель {phone} не найден")
            stmt = stmt.where(PurchaseHistory.user_id == user_id)

        result = await db.execute(stmt)
        rows = result.all()

        changed = 0
        category_counts: Counter[str] = Counter()
        brand_counts: Counter[str] = Counter()
        examples = []

        for purchase, product_category, product_brand in rows:
            name = purchase.product_name
            raw_category = product_category or purchase.category
            raw_brand = product_brand or purchase.brand
            category = derive_purchase_category(name, raw_category)
            brand = derive_purchase_brand(name, raw_brand, raw_category)

            if category:
                category_counts[category] += 1
            if brand:
                brand_counts[brand] += 1

            if category != purchase.category or brand != purchase.brand:
                changed += 1
                if len(examples) < 20:
                    examples.append(
                        {
                            "article": purchase.product_article,
                            "name": name,
                            "old_category": purchase.category,
                            "new_category": category,
                            "old_brand": purchase.brand,
                            "new_brand": brand,
                        }
                    )
                if not dry_run:
                    purchase.category = category
                    purchase.brand = brand

        if not dry_run:
            await db.commit()

        print("=" * 80)
        print("НОРМАЛИЗАЦИЯ ИСТОРИИ ПОКУПОК")
        print("=" * 80)
        print(f"Строк проверено: {len(rows)}")
        print(f"Строк к изменению: {changed}")
        print(f"Режим: {'dry-run, без записи' if dry_run else 'изменения сохранены'}")
        print()
        print("Топ категорий:")
        for category, count in category_counts.most_common(20):
            print(f"  {category}: {count}")
        print()
        print("Топ брендов:")
        for brand, count in brand_counts.most_common(20):
            print(f"  {brand}: {count}")
        print()
        print("Примеры изменений:")
        for item in examples:
            print(
                f"  {item['article'] or '-'} | {item['name'] or '-'} | "
                f"{item['old_category'] or '-'} -> {item['new_category'] or '-'} | "
                f"{item['old_brand'] or '-'} -> {item['new_brand'] or '-'}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Нормализация category/brand в purchase_history")
    parser.add_argument("--phone", help="Ограничить нормализацию одним покупателем")
    parser.add_argument("--dry-run", action="store_true", help="Показать изменения без записи в БД")
    args = parser.parse_args()
    asyncio.run(normalize_all(args.phone, args.dry_run))


if __name__ == "__main__":
    main()
