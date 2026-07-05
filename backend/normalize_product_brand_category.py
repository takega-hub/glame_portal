import asyncio

from sqlalchemy import or_, select

from app.database.connection import AsyncSessionLocal
from app.models.product import Product
from app.models.purchase_history import PurchaseHistory
from app.models.sales_record import SalesRecord
from app.services.purchase_product_fields import derive_purchase_brand, derive_purchase_category


BRAND_VALUES = {
    "UNOde50",
    "Kalliope",
    "Raganella Princess",
    "Claudio Canzian",
    "Сlaudio Canzian",
    "GEOMETRY",
    "PEARL",
    "CRYSTAL",
    "MAGNA",
    "BICOLOR",
    "PRISM OF ELEGANCE",
    "BLACK MYSTIQUE",
    "WRINKLES OG TIME",
}


def normalize_brand(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(str(value).replace("\u00a0", " ").split())
    if cleaned == "Сlaudio Canzian":
        return "Claudio Canzian"
    return cleaned or None


async def normalize_products() -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Product).where(
                or_(
                    Product.category.in_(BRAND_VALUES),
                    Product.brand.in_(["Сlaudio Canzian"]),
                )
            )
        )
        products = result.scalars().all()
        changed = 0
        for product in products:
            old_brand = normalize_brand(product.brand)
            old_category = normalize_brand(product.category)
            inferred_brand = derive_purchase_brand(product.name, old_brand, old_category)
            inferred_category = derive_purchase_category(product.name, old_category)
            if inferred_brand:
                product.brand = normalize_brand(inferred_brand)
            if inferred_category:
                product.category = inferred_category
            if product.brand != old_brand or product.category != old_category:
                changed += 1
        await db.commit()
        return changed


async def normalize_purchase_history() -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PurchaseHistory).where(
                or_(
                    PurchaseHistory.category.in_(BRAND_VALUES),
                    PurchaseHistory.brand.in_(["Сlaudio Canzian"]),
                )
            )
        )
        rows = result.scalars().all()
        changed = 0
        for row in rows:
            old_brand = normalize_brand(row.brand)
            old_category = normalize_brand(row.category)
            inferred_brand = derive_purchase_brand(row.product_name, old_brand, old_category)
            inferred_category = derive_purchase_category(row.product_name, old_category)
            if inferred_brand:
                row.brand = normalize_brand(inferred_brand)
            if inferred_category:
                row.category = inferred_category
            if row.brand != old_brand or row.category != old_category:
                changed += 1
        await db.commit()
        return changed


async def normalize_sales_records() -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SalesRecord).where(
                or_(
                    SalesRecord.product_category.in_(BRAND_VALUES),
                    SalesRecord.product_brand.in_(["Сlaudio Canzian"]),
                )
            )
        )
        rows = result.scalars().all()
        changed = 0
        for row in rows:
            old_brand = normalize_brand(row.product_brand)
            old_category = normalize_brand(row.product_category)
            inferred_brand = derive_purchase_brand(row.product_name, old_brand, old_category)
            inferred_category = derive_purchase_category(row.product_name, old_category)
            if inferred_brand:
                row.product_brand = normalize_brand(inferred_brand)
            if inferred_category:
                row.product_category = inferred_category
            if row.product_brand != old_brand or row.product_category != old_category:
                changed += 1
        await db.commit()
        return changed


async def main() -> None:
    products = await normalize_products()
    purchases = await normalize_purchase_history()
    sales = await normalize_sales_records()
    print(f"products_updated={products}")
    print(f"purchase_history_updated={purchases}")
    print(f"sales_records_updated={sales}")


if __name__ == "__main__":
    asyncio.run(main())
