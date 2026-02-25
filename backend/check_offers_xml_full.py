#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Проверка полного содержимого offers.xml
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


async def check_offers_xml():
    """Проверка offers.xml"""
    
    print("=" * 80)
    print("Проверка offers.xml")
    print("=" * 80)
    print()
    
    if not ONEC_XML_OFFERS_URL:
        print("[ERROR] ONEC_XML_OFFERS_URL не настроен")
        return
    
    print(f"URL: {ONEC_XML_OFFERS_URL}")
    print()
    
    # Загружаем XML
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.get(ONEC_XML_OFFERS_URL)
        response.raise_for_status()
        xml_content = response.content
    
    print(f"[OK] XML загружен ({len(xml_content)} байт)")
    print()
    
    # Парсим XML
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
    
    print(f"[INFO] Найдено {len(offer_elems)} предложений")
    print()
    
    # Показываем первые 10 предложений
    print("Первые 10 предложений:")
    print("-" * 80)
    for i, offer_elem in enumerate(offer_elems[:10], 1):
        # ID
        offer_id_elem = offer_elem.find('{urn:1C.ru:commerceml_210}Ид')
        if offer_id_elem is None:
            offer_id_elem = offer_elem.find('Ид')
        offer_id = offer_id_elem.text.strip() if offer_id_elem is not None and offer_id_elem.text else "Нет ID"
        
        # Артикул
        article_elem = offer_elem.find('{urn:1C.ru:commerceml_210}Артикул')
        if article_elem is None:
            article_elem = offer_elem.find('Артикул')
        article = article_elem.text.strip() if article_elem is not None and article_elem.text else "Нет артикула"
        
        # Название
        name_elem = offer_elem.find('{urn:1C.ru:commerceml_210}Наименование')
        if name_elem is None:
            name_elem = offer_elem.find('Наименование')
        name = name_elem.text.strip() if name_elem is not None and name_elem.text else "Нет названия"
        
        # Остатки по складам
        store_stocks = {}
        store_elems = offer_elem.findall('{urn:1C.ru:commerceml_210}Склад')
        if not store_elems:
            store_elems = offer_elem.findall('Склад')
        
        for store_elem in store_elems:
            store_id_attr = store_elem.get('ИдСклада')
            quantity_attr = store_elem.get('КоличествоНаСкладе')
            if store_id_attr and quantity_attr:
                store_stocks[store_id_attr] = float(quantity_attr)
        
        print(f"{i}. Артикул: {article}")
        print(f"   ID: {offer_id[:60]}...")
        print(f"   Название: {name[:60]}...")
        print(f"   Остатки по складам: {len(store_stocks)}")
        if store_stocks:
            total = sum(store_stocks.values())
            print(f"   Итого остатков: {total}")
        print()
    
    if len(offer_elems) > 10:
        print(f"... и ещё {len(offer_elems) - 10} предложений")
    
    print()
    print("=" * 80)
    print("Проверка завершена")
    print("=" * 80)
    
    # Проверяем, есть ли в XML информация о пагинации или ограничениях
    print()
    print("Проверка структуры XML:")
    print("-" * 80)
    
    # Ищем атрибуты, которые могут указывать на пагинацию
    if hasattr(offers_section, 'attrib'):
        print(f"Атрибуты раздела Предложения: {offers_section.attrib}")
    
    # Проверяем корневой элемент
    if hasattr(root, 'attrib'):
        print(f"Атрибуты корневого элемента: {root.attrib}")
    
    # Ищем элементы, которые могут указывать на продолжение
    continuation_elems = root.findall('.//{urn:1C.ru:commerceml_210}Продолжение')
    if not continuation_elems:
        continuation_elems = root.findall('.//Продолжение')
    
    if continuation_elems:
        print(f"[INFO] Найдено {len(continuation_elems)} элементов Продолжение")
        for cont_elem in continuation_elems:
            print(f"  {cont_elem.text}")
    else:
        print("[INFO] Элементы Продолжение не найдены")


if __name__ == "__main__":
    asyncio.run(check_offers_xml())
