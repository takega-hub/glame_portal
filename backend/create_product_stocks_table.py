#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для создания таблицы product_stocks
Создает таблицу для хранения остатков товаров по складам
"""
import sys
import os

# Устанавливаем кодировку для Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Добавляем путь к app
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Импортируем Base напрямую, чтобы избежать создания async engine
from sqlalchemy.orm import declarative_base
Base = declarative_base()

# Импортируем модель ProductStock напрямую, без импорта connection
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

class ProductStock(Base):
    __tablename__ = "product_stocks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    store_id = Column(String(255), nullable=False, index=True)  # Склад_Key из 1С

    quantity = Column(Float, nullable=False, default=0.0)
    reserved_quantity = Column(Float, nullable=False, default=0.0)
    available_quantity = Column(Float, nullable=False, default=0.0)

    last_synced_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_product_stocks_product_store", "product_id", "store_id", unique=True),
    )

def create_product_stocks_table():
    """Создает таблицу product_stocks"""
    
    # Получаем DATABASE_URL
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[ERROR] DATABASE_URL not found in environment variables")
        sys.exit(1)
    
    # Конвертируем async URL в sync URL для create_engine
    if database_url.startswith("postgresql+asyncpg://"):
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://")
    
    print(f"[INFO] Connecting to database...")
    print(f"[INFO] Database URL: {database_url.split('@')[1] if '@' in database_url else 'hidden'}")
    
    try:
        # Создаем синхронный engine
        engine = create_engine(database_url, echo=False)
        
        # Проверяем, существует ли таблица
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'product_stocks'
                );
            """))
            table_exists = result.scalar()
            
            if table_exists:
                print("[WARNING] Table 'product_stocks' already exists")
                # В неинтерактивном режиме просто пропускаем создание
                if not sys.stdin.isatty():
                    print("[INFO] Running in non-interactive mode. Keeping existing table.")
                    return
                response = input("Do you want to drop and recreate it? (yes/no): ")
                if response.lower() == 'yes':
                    print("[INFO] Dropping existing table...")
                    conn.execute(text("DROP TABLE IF EXISTS product_stocks CASCADE;"))
                    conn.commit()
                else:
                    print("[INFO] Keeping existing table. Exiting.")
                    return
        
        # Создаем таблицу через SQLAlchemy
        print("[INFO] Creating table 'product_stocks'...")
        Base.metadata.create_all(engine, tables=[ProductStock.__table__])
        
        print("[OK] Table 'product_stocks' created successfully")
        
        # Проверяем созданные индексы
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'product_stocks'
                ORDER BY indexname;
            """))
            indexes = [row[0] for row in result]
            print(f"[INFO] Created indexes: {', '.join(indexes)}")
        
        # Проверяем структуру таблицы
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'product_stocks'
                ORDER BY ordinal_position;
            """))
            print("\n[INFO] Table structure:")
            for row in result:
                print(f"  - {row[0]}: {row[1]} (nullable: {row[2]}, default: {row[3]})")
        
    except Exception as e:
        print(f"[ERROR] Failed to create table: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    create_product_stocks_table()
