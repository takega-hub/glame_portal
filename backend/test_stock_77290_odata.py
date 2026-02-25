#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Тест для проверки остатков по артикулу 77290 через OData API 1С
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

# Загружаем переменные окружения
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

ONEC_API_URL = os.getenv("ONEC_API_URL")
ONEC_API_TOKEN = os.getenv("ONEC_API_TOKEN")


async def test_stock_77290_odata():
    """Тест остатков через OData API"""
    
    print("=" * 80)
    print("Тест остатков по артикулу 77290 через OData API")
    print("=" * 80)
    print()
    
    if not ONEC_API_URL:
        print("[ERROR] ONEC_API_URL не настроен")
        return
    
    headers = {"Accept": "application/json"}
    if ONEC_API_TOKEN:
        if ONEC_API_TOKEN.startswith("Basic "):
            headers["Authorization"] = ONEC_API_TOKEN
        else:
            headers["Authorization"] = f"Basic {ONEC_API_TOKEN}"
    
    async with httpx.AsyncClient(timeout=30.0, headers=headers, verify=True) as client:
        # 1. Находим товар по артикулу
        print("1. Поиск товара по артикулу 77290:")
        print("-" * 80)
        
        products_url = f"{ONEC_API_URL.rstrip('/')}/Catalog_Номенклатура"
        params = {
            "$filter": "Code eq '77290' or Code eq '77290-S'",
            "$top": 10
        }
        
        try:
            response = await client.get(products_url, params=params)
            if response.status_code == 200:
                data = response.json()
                products = data.get("value", [])
                print(f"[OK] Найдено товаров: {len(products)}")
                
                for product in products:
                    print(f"   Ref_Key: {product.get('Ref_Key')}")
                    print(f"   Code: {product.get('Code')}")
                    print(f"   Description: {product.get('Description')}")
                    print()
                
                if not products:
                    print("[WARNING] Товар с артикулом 77290 не найден")
                    print("   Пробуем поиск по части артикула...")
                    params = {
                        "$filter": "startswith(Code, '77290')",
                        "$top": 20
                    }
                    response = await client.get(products_url, params=params)
                    if response.status_code == 200:
                        data = response.json()
                        products = data.get("value", [])
                        print(f"[OK] Найдено товаров с артикулом, начинающимся с 77290: {len(products)}")
                        for product in products:
                            print(f"   Code: {product.get('Code')}, Description: {product.get('Description')}")
            else:
                print(f"[ERROR] Ошибка получения товаров: {response.status_code}")
                print(f"   {response.text[:200]}")
        except Exception as e:
            print(f"[ERROR] Ошибка: {e}")
            import traceback
            traceback.print_exc()
        
        print()
        
        # 2. Пробуем получить остатки через регистр
        print("2. Попытка получить остатки через регистр:")
        print("-" * 80)
        
        stock_endpoints = [
            "/AccumulationRegister_ОстаткиТоваровНаСкладах",
            "/AccumulationRegister_ОстаткиТоваровНаСкладах_RecordType",
            "/InformationRegister_ОстаткиТоваровНаСкладах",
        ]
        
        for endpoint in stock_endpoints:
            try:
                url = f"{ONEC_API_URL.rstrip('/')}{endpoint}"
                response = await client.get(url, params={"$top": 5})
                if response.status_code == 200:
                    data = response.json()
                    records = data.get("value", [])
                    print(f"[OK] {endpoint}: найдено записей: {len(records)}")
                    if records:
                        print(f"   Пример первой записи:")
                        record = records[0]
                        for key, value in list(record.items())[:10]:
                            print(f"     {key}: {value}")
                        print()
                else:
                    print(f"❌ {endpoint}: {response.status_code}")
            except Exception as e:
                print(f"❌ {endpoint}: {str(e)}")
        
        print()
        print("=" * 80)
        print("Тест завершён")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_stock_77290_odata())
