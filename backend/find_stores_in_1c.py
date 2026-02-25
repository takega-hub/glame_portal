"""
Поиск складов в доступных коллекциях 1С
"""
import asyncio
import sys
import codecs
import os
import httpx
import xml.etree.ElementTree as ET

if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

API_URL = os.getenv("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata")
API_TOKEN = os.getenv("ONEC_API_TOKEN", "b2RhdGEudXNlcjpvcGV4b2JvZQ==")


async def find_stores():
    """Поиск складов в доступных коллекциях"""
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    
    print("=" * 80)
    print("ПОИСК СКЛАДОВ В 1С")
    print("=" * 80)
    print()
    
    async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
        # 1. Получаем service document для списка всех коллекций
        print("1. Получение списка всех коллекций...")
        try:
            response = await client.get(API_URL.rstrip('/'))
            response.raise_for_status()
            
            # Парсим XML
            root = ET.fromstring(response.text)
            
            # Ищем все collection с упоминанием складов
            namespaces = {
                'app': 'http://www.w3.org/2007/app',
                'atom': 'http://www.w3.org/2005/Atom'
            }
            
            collections = root.findall('.//app:collection', namespaces)
            print(f"   Найдено коллекций: {len(collections)}\n")
            
            # Ищем коллекции, связанные со складами
            store_related = []
            keywords = ['склад', 'store', 'магазин', 'shop', 'warehouse']
            
            for coll in collections:
                href = coll.get('href', '')
                title_elem = coll.find('atom:title', namespaces)
                title = title_elem.text if title_elem is not None else ''
                
                # Проверяем, содержит ли название или href ключевые слова
                combined = (href + ' ' + title).lower()
                if any(keyword in combined for keyword in keywords):
                    store_related.append((href, title))
            
            if store_related:
                print("2. Найдены коллекции, связанные со складами:")
                print("-" * 80)
                for href, title in store_related:
                    print(f"   {href} - {title}")
                print()
            
            # 2. Проверяем, есть ли информация о складах в продажах
            print("3. Проверка данных о складах в продажах...")
            sales_url = f"{API_URL.rstrip('/')}/AccumulationRegister_Продажи_RecordType"
            try:
                sales_response = await client.get(sales_url, params={"$top": 5})
                if sales_response.status_code == 200:
                    sales_data = sales_response.json()
                    items = sales_data.get("value", [])
                    if items:
                        # Ищем уникальные Склад_Key
                        store_keys = set()
                        for item in items:
                            store_key = item.get("Склад_Key")
                            if store_key:
                                store_keys.add(store_key)
                        
                        if store_keys:
                            print(f"   ✓ Найдено уникальных Склад_Key в продажах: {len(store_keys)}")
                            print(f"   Примеры: {list(store_keys)[:3]}")
                            
                            # Пробуем получить информацию о складе через навигацию
                            if store_keys:
                                sample_key = list(store_keys)[0]
                                print(f"\n4. Попытка получить информацию о складе через навигацию...")
                                nav_urls = [
                                    f"{API_URL.rstrip('/')}/Catalog_Номенклатура(guid'{sample_key}')",
                                    f"{API_URL.rstrip('/')}/Catalog_Склады(guid'{sample_key}')",
                                ]
                                
                                for nav_url in nav_urls:
                                    try:
                                        nav_response = await client.get(nav_url)
                                        if nav_response.status_code == 200:
                                            nav_data = nav_response.json()
                                            print(f"   ✓ Найден способ получения склада: {nav_url}")
                                            print(f"     Данные: {nav_data.get('Description', nav_data.get('Code', 'N/A'))}")
                                            break
                                    except:
                                        pass
            except Exception as e:
                print(f"   ✗ Ошибка: {e}")
            
        except Exception as e:
            print(f"✗ Ошибка: {e}")
            import traceback
            traceback.print_exc()
        
        # 3. Пробуем найти склады через другие известные коллекции
        print("\n5. Поиск в других коллекциях...")
        other_endpoints = [
            "/Catalog_Организации",
            "/Catalog_Подразделения",
            "/Catalog_МестаХранения",
        ]
        
        for endpoint in other_endpoints:
            try:
                url = f"{API_URL.rstrip('/')}{endpoint}"
                response = await client.get(url, params={"$top": 1})
                if response.status_code == 200:
                    data = response.json()
                    if data.get("value"):
                        print(f"   ✓ Найден доступный endpoint: {endpoint}")
            except:
                pass


if __name__ == "__main__":
    asyncio.run(find_stores())
