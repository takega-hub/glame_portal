#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Простой тест для проверки остатков по артикулу 77290 из offers.xml
Проверяет парсинг XML и сопоставление товаров
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

from dotenv import load_dotenv
import httpx
import xml.etree.ElementTree as ET

# Загружаем переменные окружения
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

ONEC_XML_OFFERS_URL = os.getenv("ONEC_XML_OFFERS_URL")


async def test_parse_offers_xml():
    """Тест парсинга offers.xml для артикула 77290"""
    
    print("=" * 80)
    print("Тест парсинга остатков из offers.xml для артикула 77290")
    print("=" * 80)
    print()
    
    if not ONEC_XML_OFFERS_URL:
        print("[ERROR] ONEC_XML_OFFERS_URL не настроен")
        return
    
    # Загружаем XML
    print("1. Загрузка offers.xml:")
    print("-" * 80)
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.get(ONEC_XML_OFFERS_URL)
        response.raise_for_status()
        xml_content = response.content
    
    print(f"[OK] XML загружен ({len(xml_content)} байт)")
    print()
    
    # Парсим XML
    print("2. Парсинг XML:")
    print("-" * 80)
    root = ET.fromstring(xml_content)
    
    # Ищем предложения
    offers_section = root.find('.//{urn:1C.ru:commerceml_210}Предложения')
    if offers_section is None:
        offers_section = root.find('.//Предложения')
    
    if not offers_section:
        print("[ERROR] Раздел Предложения не найден")
        return
    
    offer_elems = offers_section.findall('{urn:1C.ru:commerceml_210}Предложение')
    if not offer_elems:
        offer_elems = offers_section.findall('Предложение')
    
    print(f"[OK] Найдено {len(offer_elems)} предложений")
    print()
    
    # Сначала показываем все предложения для отладки
    print("3. Все предложения в XML (первые 10):")
    print("-" * 80)
    for i, offer_elem in enumerate(offer_elems[:10], 1):
        article_elem = offer_elem.find('{urn:1C.ru:commerceml_210}Артикул')
        if article_elem is None:
            article_elem = offer_elem.find('Артикул')
        article = article_elem.text.strip() if article_elem is not None and article_elem.text else "Нет артикула"
        
        offer_id_elem = offer_elem.find('{urn:1C.ru:commerceml_210}Ид')
        if offer_id_elem is None:
            offer_id_elem = offer_elem.find('Ид')
        offer_id = offer_id_elem.text.strip() if offer_id_elem is not None and offer_id_elem.text else "Нет ID"
        
        print(f"   {i}. Артикул: {article}, ID: {offer_id[:50]}...")
    print()
    
    # Ищем предложения с артикулом, содержащим 77290
    print("4. Поиск предложений с артикулом 77290:")
    print("-" * 80)
    
    found_offers = []
    for offer_elem in offer_elems:
        # Проверяем артикул
        article_elem = offer_elem.find('{urn:1C.ru:commerceml_210}Артикул')
        if article_elem is None:
            article_elem = offer_elem.find('Артикул')
        
        article = article_elem.text.strip() if article_elem is not None and article_elem.text else None
        
        # Ищем артикулы, содержащие 77290
        if article and "77290" in article:
            # Получаем ID предложения
            offer_id_elem = offer_elem.find('{urn:1C.ru:commerceml_210}Ид')
            if offer_id_elem is None:
                offer_id_elem = offer_elem.find('Ид')
            
            offer_id = offer_id_elem.text.strip() if offer_id_elem is not None and offer_id_elem.text else None
            
            # Получаем product_id (часть до #)
            product_id = offer_id.split('#')[0] if offer_id and '#' in offer_id else offer_id
            
            # Получаем название
            name_elem = offer_elem.find('{urn:1C.ru:commerceml_210}Наименование')
            if name_elem is None:
                name_elem = offer_elem.find('Наименование')
            
            name = name_elem.text.strip() if name_elem is not None and name_elem.text else None
            
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
            quantity_elem = offer_elem.find('{urn:1C.ru:commerceml_210}Количество')
            if quantity_elem is None:
                quantity_elem = offer_elem.find('Количество')
            
            total_quantity = float(quantity_elem.text.strip()) if quantity_elem is not None and quantity_elem.text else 0.0
            
            found_offers.append({
                'offer_id': offer_id,
                'product_id': product_id,
                'article': article,
                'name': name,
                'store_stocks': store_stocks,
                'total_quantity': total_quantity
            })
    
    if not found_offers:
        print("[WARNING] Предложения с артикулом 77290 не найдены")
    else:
        print(f"[OK] Найдено {len(found_offers)} предложений:")
        print()
        
        # Маппинг складов (из предыдущих данных)
        store_mapping = {
            "8cebda58-a2ab-11f0-96fc-fa163e4cc04e": "MEGANOM",
            "e1a2eace-fdc8-11ef-8c0c-fa163e4cc04e": "Основной склад",
            "6c3a8322-a2ab-11f0-96fc-fa163e4cc04e": "CENTRUM",
            "3daee4e4-a2ab-11f0-96fc-fa163e4cc04e": "YALTA"
        }
        
        for i, offer in enumerate(found_offers, 1):
            print(f"{i}. Предложение:")
            print(f"   Offer ID: {offer['offer_id']}")
            print(f"   Product ID: {offer['product_id']}")
            print(f"   Артикул: {offer['article']}")
            print(f"   Название: {offer['name']}")
            print(f"   Общее количество: {offer['total_quantity']}")
            
            if offer['store_stocks']:
                print(f"   Остатки по складам:")
                total_xml = 0.0
                for store_id, quantity in sorted(offer['store_stocks'].items()):
                    store_name = store_mapping.get(store_id, f"Неизвестный ({store_id})")
                    print(f"     {store_name}: {quantity}")
                    total_xml += float(quantity)
                print(f"   ИТОГО по складам: {total_xml}")
            else:
                print(f"   [WARNING] Разбивка по складам отсутствует")
            
            print()
    
    print("=" * 80)
    print("Тест завершён")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_parse_offers_xml())
