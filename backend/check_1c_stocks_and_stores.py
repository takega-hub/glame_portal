"""
Скрипт для проверки данных по остаткам и складам из 1С
Проверяет, какие регистры и каталоги доступны для получения остатков по складам
"""
import asyncio
import httpx
import os
import json
import sys
from dotenv import load_dotenv
from pathlib import Path

# Исправление кодировки для Windows
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Загружаем переменные окружения
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

ONEC_API_URL = os.getenv("ONEC_API_URL")
ONEC_API_TOKEN = os.getenv("ONEC_API_TOKEN")

async def check_1c_endpoints():
    """Проверяет доступные эндпоинты в 1С для остатков и складов"""
    
    if not ONEC_API_URL:
        print("[ERROR] ONEC_API_URL не настроен")
        return
    
    headers = {"Accept": "application/json"}
    if ONEC_API_TOKEN:
        if ONEC_API_TOKEN.startswith("Basic "):
            headers["Authorization"] = ONEC_API_TOKEN
        else:
            headers["Authorization"] = f"Basic {ONEC_API_TOKEN}"
    
    client = httpx.AsyncClient(timeout=30.0, headers=headers, verify=True)
    
    print("=" * 80)
    print("Проверка данных по остаткам и складам из 1С")
    print("=" * 80)
    print()
    
    # 1. Проверяем каталог складов
    print("1. Проверка каталога складов:")
    print("-" * 80)
    stores_endpoints = [
        "/Catalog_Склады",
        "/Catalog_Stores",
        "/InformationRegister_Склады",
    ]
    
    for endpoint in stores_endpoints:
        try:
            url = f"{ONEC_API_URL.rstrip('/')}{endpoint}"
            response = await client.get(url, params={"$top": 5})
            if response.status_code == 200:
                data = response.json()
                stores = data.get("value", [])
                print(f"[OK] {endpoint}: найдено {len(stores)} складов")
                if stores:
                    print(f"   Пример данных первого склада:")
                    store = stores[0]
                    for key, value in list(store.items())[:10]:
                        print(f"     {key}: {value}")
                    print()
            else:
                print(f"❌ {endpoint}: {response.status_code}")
        except Exception as e:
            print(f"❌ {endpoint}: {str(e)}")
    
    print()
    
    # 2. Проверяем регистры остатков
    print("2. Проверка регистров остатков:")
    print("-" * 80)
    stock_endpoints = [
        "/AccumulationRegister_ОстаткиТоваровНаСкладах",
        "/AccumulationRegister_ОстаткиТоваровНаСкладах_RecordType",
        "/AccumulationRegister_ОстаткиТоваровНаСкладах_Остатки",
        "/AccumulationRegister_ОстаткиТоваров",
        "/AccumulationRegister_ОстаткиТоваров_RecordType",
        "/AccumulationRegister_ОстаткиТоваров_Остатки",
        "/InformationRegister_ОстаткиТоваровНаСкладах",
        "/InformationRegister_ОстаткиТоваров",
    ]
    
    for endpoint in stock_endpoints:
        try:
            url = f"{ONEC_API_URL.rstrip('/')}{endpoint}"
            response = await client.get(url, params={"$top": 3})
            if response.status_code == 200:
                data = response.json()
                records = data.get("value", [])
                print(f"[OK] {endpoint}: найдено записей: {len(records)}")
                if records:
                    print(f"   Пример данных первой записи:")
                    record = records[0]
                    for key, value in list(record.items())[:15]:
                        if isinstance(value, dict):
                            print(f"     {key}: {{...}}")
                        else:
                            print(f"     {key}: {value}")
                    print()
            else:
                print(f"❌ {endpoint}: {response.status_code}")
        except Exception as e:
            print(f"❌ {endpoint}: {str(e)}")
    
    print()
    
    # 3. Проверяем метаданные для понимания структуры
    print("3. Проверка метаданных регистра остатков:")
    print("-" * 80)
    try:
        # Пробуем получить метаданные через $metadata
        url = f"{ONEC_API_URL.rstrip('/')}/$metadata"
        response = await client.get(url)
        if response.status_code == 200:
            print("[OK] Метаданные доступны")
            # Ищем упоминания остатков в метаданных
            content = response.text
            if "Остатки" in content or "Остаток" in content:
                print("   Найдены упоминания остатков в метаданных")
            if "Склад" in content:
                print("   Найдены упоминания складов в метаданных")
        else:
            print(f"[ERROR] Метаданные недоступны: {response.status_code}")
    except Exception as e:
        print(f"[ERROR] Ошибка получения метаданных: {str(e)}")
    
    print()
    
    # 4. Проверяем, есть ли в продажах информация о складах
    print("4. Проверка данных о складах в продажах:")
    print("-" * 80)
    try:
        url = f"{ONEC_API_URL.rstrip('/')}/AccumulationRegister_Продажи_RecordType"
        response = await client.get(url, params={"$top": 3, "$select": "Period,Склад_Key,Номенклатура_Key,Количество"})
        if response.status_code == 200:
            data = response.json()
            records = data.get("value", [])
            print(f"[OK] Найдено записей продаж: {len(records)}")
            if records:
                print(f"   Пример данных первой записи:")
                record = records[0]
                for key, value in record.items():
                    print(f"     {key}: {value}")
                
                # Проверяем, есть ли поле Склад_Key
                if "Склад_Key" in record or "Склад" in record:
                    print("\n   [OK] В продажах есть информация о складах!")
                else:
                    print("\n   [WARNING] В продажах нет явного поля склада")
        else:
            print(f"[ERROR] Ошибка получения продаж: {response.status_code}")
    except Exception as e:
        print(f"[ERROR] Ошибка: {str(e)}")
    
    print()
    
    # 5. Проверяем структуру offers.xml (если используется CommerceML)
    print("5. Информация о CommerceML (offers.xml):")
    print("-" * 80)
    print("   CommerceML XML обычно содержит остатки в формате:")
    print("   <Предложение>")
    print("     <Ид>...</Ид>")
    print("     <Количество>...</Количество>")
    print("     <Склад>")
    print("       <Ид>...</Ид>")
    print("       <Количество>...</Количество>")
    print("     </Склад>")
    print("   </Предложение>")
    print("   [WARNING] Нужно проверить, есть ли в offers.xml разбивка по складам")
    
    await client.aclose()
    
    print()
    print("=" * 80)
    print("Рекомендации:")
    print("=" * 80)
    print("1. Если найден регистр остатков с разбивкой по складам - использовать его")
    print("2. Если в offers.xml есть разбивка по складам - парсить её")
    print("3. Если остатки только общие - можно распределять пропорционально продажам")
    print("4. Склады можно получить из каталога или из продаж (поле Склад_Key)")

if __name__ == "__main__":
    asyncio.run(check_1c_endpoints())
