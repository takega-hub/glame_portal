#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Тест для проверки остатков по артикулу 77290
Проверяет:
1. Загрузку остатков из offers.xml
2. Сохранение остатков в БД
3. Отображение остатков в аналитике
"""
import asyncio
import sys
import os
from pathlib import Path

# Исправление кодировки для Windows
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Добавляем путь к app
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, func, Column, String, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func as sql_func
from sqlalchemy.orm import declarative_base
from datetime import date

# Загружаем переменные окружения
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

DATABASE_URL = os.getenv("DATABASE_URL")
ONEC_XML_OFFERS_URL = os.getenv("ONEC_XML_OFFERS_URL")

# Создаем базовый класс для моделей
Base = declarative_base()

# Определяем модели локально
class Product(Base):
    __tablename__ = "products"
    id = Column(UUID(as_uuid=True), primary_key=True)
    external_id = Column(String(255))
    article = Column(String(100))
    name = Column(String(500))

class ProductStock(Base):
    __tablename__ = "product_stocks"
    id = Column(UUID(as_uuid=True), primary_key=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"))
    store_id = Column(String(255))
    available_quantity = Column(Float)
    last_synced_at = Column(DateTime(timezone=True))

class Store(Base):
    __tablename__ = "stores"
    id = Column(UUID(as_uuid=True), primary_key=True)
    external_id = Column(String(255))
    name = Column(String(255))

class InventoryAnalytics(Base):
    __tablename__ = "inventory_analytics"
    id = Column(UUID(as_uuid=True), primary_key=True)
    product_article = Column(String(100))
    store_id = Column(String(255))
    current_stock = Column(Float)
    analysis_date = Column(DateTime)


async def test_stock_77290():
    """Тест остатков по артикулу 77290"""
    
    print("=" * 80)
    print("Тест остатков по артикулу 77290")
    print("=" * 80)
    print()
    
    if not DATABASE_URL:
        print("[ERROR] DATABASE_URL не настроен")
        return
    
    if not ONEC_XML_OFFERS_URL:
        print("[ERROR] ONEC_XML_OFFERS_URL не настроен")
        return
    
    # Создаем async engine
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            # 1. Проверяем товар в БД
            print("1. Проверка товара в БД:")
            print("-" * 80)
            product_result = await db.execute(
                select(Product).where(Product.article == "77290")
            )
            product = product_result.scalar_one_or_none()
            
            if not product:
                print("[ERROR] Товар с артикулом 77290 не найден в БД")
                print("   Попробуйте сначала синхронизировать товары из 1С")
                return
            
            print(f"[OK] Товар найден:")
            print(f"   ID: {product.id}")
            print(f"   Название: {product.name}")
            print(f"   Артикул: {product.article}")
            print(f"   External ID (1С): {product.external_id}")
            print()
            
            # 2. Проверяем текущие остатки в БД
            print("2. Текущие остатки в БД:")
            print("-" * 80)
            stock_result = await db.execute(
                select(ProductStock, Store.name.label('store_name'))
                .outerjoin(Store, ProductStock.store_id == Store.external_id)
                .where(ProductStock.product_id == product.id)
            )
            stocks = stock_result.all()
            
            if stocks:
                print(f"[OK] Найдено {len(stocks)} записей остатков:")
                total_stock = 0.0
                for stock, store_name in stocks:
                    print(f"   Склад ID: {stock.store_id}")
                    print(f"   Название склада: {store_name or 'Не найдено'}")
                    print(f"   Количество: {stock.available_quantity}")
                    print(f"   Обновлено: {stock.last_synced_at}")
                    total_stock += stock.available_quantity
                    print()
                print(f"   ИТОГО остатков в БД: {total_stock}")
            else:
                print("[WARNING] Остатки в БД не найдены")
            print()
            
            # 3. Загружаем и парсим offers.xml напрямую
            print("3. Загрузка остатков из offers.xml:")
            print("-" * 80)
            import httpx
            import xml.etree.ElementTree as ET
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.get(ONEC_XML_OFFERS_URL)
                response.raise_for_status()
                xml_content = response.content
            
            # Парсим XML
            root = ET.fromstring(xml_content)
            
            # Ищем предложения с артикулом 77290
            offers_section = root.find('.//{urn:1C.ru:commerceml_210}Предложения')
            if offers_section is None:
                offers_section = root.find('.//Предложения')
            
            found_offers = []
            if offers_section:
                offer_elems = offers_section.findall('{urn:1C.ru:commerceml_210}Предложение')
                if not offer_elems:
                    offer_elems = offers_section.findall('Предложение')
                
                for offer_elem in offer_elems:
                    # Проверяем артикул
                    article_elem = offer_elem.find('{urn:1C.ru:commerceml_210}Артикул')
                    if article_elem is None:
                        article_elem = offer_elem.find('Артикул')
                    
                    if article_elem is not None and article_elem.text and article_elem.text.strip() == "77290":
                        # Нашли предложение с нужным артикулом
                        offer_id_elem = offer_elem.find('{urn:1C.ru:commerceml_210}Ид')
                        if offer_id_elem is None:
                            offer_id_elem = offer_elem.find('Ид')
                        
                        offer_id = offer_id_elem.text.strip() if offer_id_elem is not None and offer_id_elem.text else None
                        
                        # Парсим остатки по складам
                        store_stocks = {}
                        store_elems = offer_elem.findall('{urn:1C.ru:commerceml_210}Склад')
                        if not store_elems:
                            store_elems = offer_elem.findall('Склад')
                        
                        for store_elem in store_elems:
                            store_id_attr = store_elem.get('ИдСклада')
                            quantity_attr = store_elem.get('КоличествоНаСкладе')
                            if store_id_attr and quantity_attr:
                                try:
                                    store_stocks[store_id_attr] = float(quantity_attr)
                                except (ValueError, TypeError):
                                    pass
                        
                        # Общее количество
                        total_quantity = 0.0
                        stocks_elem = offer_elem.find('{urn:1C.ru:commerceml_210}Остатки')
                        if stocks_elem is None:
                            stocks_elem = offer_elem.find('Остатки')
                        
                        if stocks_elem:
                            stock_elems = stocks_elem.findall('{urn:1C.ru:commerceml_210}Остаток')
                            if not stock_elems:
                                stock_elems = stocks_elem.findall('Остаток')
                            
                            for stock_elem in stock_elems:
                                quantity_elem = stock_elem.find('{urn:1C.ru:commerceml_210}Количество')
                                if quantity_elem is None:
                                    quantity_elem = stock_elem.find('Количество')
                                
                                if quantity_elem is not None and quantity_elem.text:
                                    try:
                                        total_quantity += float(quantity_elem.text.strip())
                                    except (ValueError, TypeError):
                                        pass
                        
                        found_offers.append({
                            'offer_id': offer_id,
                            'store_stocks': store_stocks,
                            'total_quantity': total_quantity
                        })
            
            if not found_offers:
                print(f"[WARNING] Предложение для товара 77290 не найдено в offers.xml")
            else:
                print(f"[OK] Найдено {len(found_offers)} предложений:")
                for offer in found_offers:
                    print(f"   Offer ID: {offer['offer_id']}")
                    print(f"   Общее количество: {offer['total_quantity']}")
                    
                    if offer['store_stocks']:
                        print(f"   Остатки по складам:")
                        total_xml = 0.0
                        for store_id_1c, quantity in offer['store_stocks'].items():
                            # Пытаемся найти название склада
                            store_result = await db.execute(
                                select(Store).where(Store.external_id == store_id_1c)
                            )
                            store = store_result.scalar_one_or_none()
                            store_name = store.name if store else "Неизвестный склад"
                            
                            print(f"     Склад ID: {store_id_1c}")
                            print(f"     Название: {store_name}")
                            print(f"     Количество: {quantity}")
                            total_xml += float(quantity)
                            print()
                        print(f"   ИТОГО остатков в XML: {total_xml}")
                    else:
                        print(f"   [WARNING] Разбивка по складам отсутствует в XML")
                    print()
            
            # 4. Сравнение данных
            print("4. Сравнение данных:")
            print("-" * 80)
            if found_offers and stocks:
                offer = found_offers[0]
                xml_stocks = offer.get('store_stocks', {})
                db_stocks = {str(stock.store_id): stock.available_quantity for stock, _ in stocks}
                
                print("Сравнение остатков по складам:")
                all_stores = set(list(xml_stocks.keys()) + list(db_stocks.keys()))
                
                for store_id in sorted(all_stores):
                    xml_qty = xml_stocks.get(store_id, 0)
                    db_qty = db_stocks.get(store_id, 0)
                    
                    # Находим название склада
                    store_result = await db.execute(
                        select(Store).where(Store.external_id == store_id)
                    )
                    store = store_result.scalar_one_or_none()
                    store_name = store.name if store else "Неизвестный склад"
                    
                    status = "✓" if abs(xml_qty - db_qty) < 0.01 else "✗"
                    print(f"   {status} {store_name} ({store_id}):")
                    print(f"      XML: {xml_qty}")
                    print(f"      БД:  {db_qty}")
                    if abs(xml_qty - db_qty) >= 0.01:
                        print(f"      РАЗНИЦА: {abs(xml_qty - db_qty)}")
                    print()
            else:
                if not found_offers:
                    print("[WARNING] Невозможно сравнить - предложение не найдено в XML")
                if not stocks:
                    print("[WARNING] Невозможно сравнить - остатки не найдены в БД")
            
            # 5. Проверяем остатки в аналитике
            print("5. Проверка остатков в аналитике:")
            print("-" * 80)
            analytics_result = await db.execute(
                select(InventoryAnalytics, Store.name.label('store_name'))
                .outerjoin(Store, InventoryAnalytics.store_id == Store.external_id)
                .where(
                    (InventoryAnalytics.product_article == "77290")
                    & (InventoryAnalytics.analysis_date == date.today())
                )
            )
            analytics = analytics_result.all()
            
            if analytics:
                print(f"[OK] Найдено {len(analytics)} записей аналитики:")
                for analytics_row, store_name in analytics:
                    print(f"   Склад ID: {analytics_row.store_id}")
                    print(f"   Название склада: {store_name or 'Не найдено'}")
                    print(f"   Текущий остаток: {analytics_row.current_stock}")
                    print(f"   Дата анализа: {analytics_row.analysis_date}")
                    print()
            else:
                print("[WARNING] Аналитика для этого товара не найдена")
                print("   Нужно запустить пересчёт аналитики")
            
        except Exception as e:
            print(f"[ERROR] Ошибка: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await db.close()
    
    await engine.dispose()
    
    print("=" * 80)
    print("Тест завершён")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_stock_77290())
