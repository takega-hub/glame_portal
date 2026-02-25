"""
Поиск коллекции свойств номенклатуры
"""
import asyncio
import sys
import codecs
import os
import httpx
import json

if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

API_URL = os.getenv("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata")
API_TOKEN = os.getenv("ONEC_API_TOKEN", "b2RhdGEudXNlcjpvcGV4b2JvZQ==")


async def find_properties():
    """Поиск коллекции свойств"""
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    
    print("=" * 100)
    print("ПОИСК КОЛЛЕКЦИИ СВОЙСТВ")
    print("=" * 100)
    print()
    
    async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
        # Получаем service document для списка всех коллекций
        print("1. Получение списка всех коллекций...")
        try:
            response = await client.get(API_URL.rstrip('/'))
            response.raise_for_status()
            
            # Парсим XML
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.text)
            
            namespaces = {
                'app': 'http://www.w3.org/2007/app',
                'atom': 'http://www.w3.org/2005/Atom'
            }
            
            collections = root.findall('.//app:collection', namespaces)
            print(f"   Найдено коллекций: {len(collections)}\n")
            
            # Ищем коллекции, связанные со свойствами
            property_related = []
            keywords = ['свойств', 'property', 'характеристик', 'characteristic', 'реквизит', 'requisite']
            
            for coll in collections:
                href = coll.get('href', '')
                title_elem = coll.find('atom:title', namespaces)
                title = title_elem.text if title_elem is not None else ''
                
                combined = (href + ' ' + title).lower()
                if any(keyword in combined for keyword in keywords):
                    property_related.append((href, title))
            
            if property_related:
                print("2. Найдены коллекции, связанные со свойствами:")
                print("-" * 100)
                for href, title in property_related:
                    print(f"   {href} - {title}")
                print()
                
                # Проверяем каждую коллекцию
                print("3. Проверка коллекций...")
                for href, title in property_related[:10]:  # Первые 10
                    try:
                        coll_url = f"{API_URL.rstrip('/')}{href}"
                        coll_response = await client.get(coll_url, params={"$top": 3})
                        if coll_response.status_code == 200:
                            coll_data = coll_response.json()
                            items = coll_data.get("value", [])
                            if items:
                                print(f"\n✓ {href}:")
                                print(f"   Найдено записей: {len(items)}")
                                print(f"   Пример записи:")
                                example = items[0]
                                for key in sorted(example.keys())[:15]:
                                    value = example[key]
                                    if isinstance(value, dict):
                                        value_str = f"{{объект: {value.get('Description', 'ссылка')}}}"
                                    else:
                                        value_str = str(value)
                                        if len(value_str) > 50:
                                            value_str = value_str[:47] + "..."
                                    print(f"     {key}: {value_str}")
                    except Exception as e:
                        print(f"   ✗ {href}: Ошибка - {str(e)[:50]}")
        except Exception as e:
            print(f"✗ Ошибка: {e}")
            import traceback
            traceback.print_exc()
        
        # Также пробуем получить свойства через навигацию
        print("\n" + "=" * 100)
        print("ПОИСК СВОЙСТВ ЧЕРЕЗ НАВИГАЦИЮ")
        print("=" * 100)
        
        # Берем пример из ДополнительныеРеквизиты
        char_catalog_url = f"{API_URL.rstrip('/')}/Catalog_ХарактеристикиНоменклатуры"
        response = await client.get(char_catalog_url, params={"$top": 1})
        response.raise_for_status()
        char_data = response.json()
        char_items = char_data.get("value", [])
        
        if char_items:
            char_item = char_items[0]
            dop_rekv = char_item.get("ДополнительныеРеквизиты", [])
            
            if dop_rekv:
                first_rek = dop_rekv[0]
                property_key = first_rek.get("Свойство_Key")
                
                if property_key:
                    print(f"\nПробуем получить свойство по ключу: {property_key}")
                    
                    # Пробуем разные варианты получения свойства
                    property_urls = [
                        f"{API_URL.rstrip('/')}/Catalog_СвойстваНоменклатуры(guid'{property_key}')",
                        f"{API_URL.rstrip('/')}/Catalog_Свойства(guid'{property_key}')",
                        f"{API_URL.rstrip('/')}/Catalog_СвойстваОбъектов(guid'{property_key}')",
                    ]
                    
                    for prop_url in property_urls:
                        try:
                            prop_response = await client.get(prop_url)
                            if prop_response.status_code == 200:
                                prop_data = prop_response.json()
                                print(f"\n✓ Найден способ получения свойства: {prop_url}")
                                print(json.dumps(prop_data, ensure_ascii=False, indent=2, default=str)[:500])
                                break
                        except:
                            pass


if __name__ == "__main__":
    asyncio.run(find_properties())
