"""
Тест фильтрации JSONB через SQLAlchemy
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, select, func, or_, and_, String, cast, text
from sqlalchemy.orm import sessionmaker
from app.models.product import Product

# Добавляем путь к app
sys.path.insert(0, os.path.dirname(__file__))

# Загружаем .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")

if not DATABASE_URL:
    print("[ERROR] DATABASE_URL not found")
    sys.exit(1)

def test_filter():
    """Тест фильтрации"""
    try:
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        print("=" * 80)
        print("ТЕСТ ФИЛЬТРАЦИИ JSONB ЧЕРЕЗ SQLALCHEMY")
        print("=" * 80)
        print()
        
        # Тест 1: Простой фильтр по покрытию
        print("1. Простой фильтр по покрытию (без исключения вариантов):")
        print("-" * 80)
        query1 = select(Product).where(
            Product.is_active == True,
            Product.specifications.isnot(None),
            func.lower(cast(Product.specifications["Покрытие"], String)) == func.lower("Родий")
        ).limit(5)
        
        print(f"SQL: {query1}")
        print()
        result1 = session.execute(query1)
        products1 = result1.scalars().all()
        print(f"Найдено: {len(products1)} товаров")
        for p in products1:
            print(f"  {p.name} - article={p.article}")
        print()
        
        # Тест 2: Фильтр с исключением вариантов
        print("2. Фильтр по покрытию С исключением вариантов:")
        print("-" * 80)
        variant_exclusion = or_(
            Product.specifications.is_(None),
            and_(
                Product.specifications.isnot(None),
                or_(
                    cast(Product.specifications["parent_external_id"], String).is_(None),
                    cast(Product.specifications["parent_external_id"], String) == ""
                )
            )
        )
        
        pokrytie_filter = "Родий"
        pokrytie_condition = and_(
            Product.specifications.isnot(None),
            func.lower(cast(Product.specifications["Покрытие"], String)) == func.lower(pokrytie_filter)
        )
        
        query2 = select(Product).where(
            Product.is_active == True,
            variant_exclusion,
            pokrytie_condition
        ).limit(5)
        
        print(f"SQL: {query2}")
        print()
        result2 = session.execute(query2)
        products2 = result2.scalars().all()
        print(f"Найдено: {len(products2)} товаров")
        for p in products2:
            print(f"  {p.name} - article={p.article}")
        print()
        
        # Тест 3: Использование text() для прямого SQL
        print("3. Фильтр с использованием text() для прямого SQL:")
        print("-" * 80)
        query3 = select(Product).where(
            Product.is_active == True,
            variant_exclusion,
            Product.specifications.isnot(None),
            func.lower(text("specifications->>'Покрытие'")) == func.lower("Родий")
        ).limit(5)
        
        print(f"SQL: {query3}")
        print()
        result3 = session.execute(query3)
        products3 = result3.scalars().all()
        print(f"Найдено: {len(products3)} товаров")
        for p in products3:
            print(f"  {p.name} - article={p.article}")
        print()
        
        session.close()
        
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_filter()
