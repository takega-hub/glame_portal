"""
Проверка артикулов товаров в БД
"""
import asyncio
import sys
import os
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models.product import Product

# Настройки подключения к БД
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost/dbname")

async def check_articles():
    """Проверка артикулов товаров"""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        # Проверяем товары с external_code, но без article
        result = await db.execute(
            select(Product).where(
                Product.external_code.isnot(None),
                Product.article.is_(None)
            ).limit(10)
        )
        products_without_article = result.scalars().all()
        
        print("=" * 80)
        print("ТОВАРЫ БЕЗ АРТИКУЛА (есть только external_code)")
        print("=" * 80)
        for p in products_without_article:
            print(f"ID: {p.id}")
            print(f"  Название: {p.name}")
            print(f"  external_code (Code): {p.external_code}")
            print(f"  article (Артикул): {p.article}")
            print(f"  external_id (Ref_Key): {p.external_id}")
            if p.specifications and p.specifications.get("parent_external_id"):
                print(f"  Характеристика! Parent: {p.specifications.get('parent_external_id')}")
            print()
        
        # Проверяем товары с article
        result = await db.execute(
            select(Product).where(
                Product.article.isnot(None)
            ).limit(10)
        )
        products_with_article = result.scalars().all()
        
        print("=" * 80)
        print("ТОВАРЫ С АРТИКУЛОМ")
        print("=" * 80)
        for p in products_with_article:
            print(f"ID: {p.id}")
            print(f"  Название: {p.name}")
            print(f"  article (Артикул): {p.article}")
            print(f"  external_code (Code): {p.external_code}")
            print(f"  external_id (Ref_Key): {p.external_id}")
            if p.specifications and p.specifications.get("parent_external_id"):
                print(f"  Характеристика! Parent: {p.specifications.get('parent_external_id')}")
            print()
        
        # Статистика
        total_count = await db.execute(select(func.count(Product.id)))
        total = total_count.scalar()
        
        with_article_count = await db.execute(
            select(func.count(Product.id)).where(Product.article.isnot(None))
        )
        with_article = with_article_count.scalar()
        
        with_external_code_count = await db.execute(
            select(func.count(Product.id)).where(Product.external_code.isnot(None))
        )
        with_external_code = with_external_code_count.scalar()
        
        characteristics_count = await db.execute(
            text("SELECT COUNT(*) FROM products WHERE specifications->>'parent_external_id' IS NOT NULL")
        )
        characteristics = characteristics_count.scalar()
        
        print("=" * 80)
        print("СТАТИСТИКА")
        print("=" * 80)
        print(f"Всего товаров: {total}")
        print(f"С артикулом (article): {with_article}")
        print(f"С кодом 1С (external_code): {with_external_code}")
        print(f"Характеристик (с Parent_Key): {characteristics}")
        print(f"Без артикула: {total - with_article}")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_articles())
