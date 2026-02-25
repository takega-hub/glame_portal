"""
Поиск коллекции характеристик номенклатуры в 1С
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


async def find_characteristics():
    """Поиск характеристик номенклатуры"""
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    
    # Возможные коллекции для характеристик
    possible_endpoints = [
        "/Catalog_ХарактеристикиНоменклатуры",
        "/Catalog_НоменклатураХарактеристики",
        "/InformationRegister_ХарактеристикиНоменклатуры",
        "/Catalog_Номенклатура"
    ]
    
    print("=" * 80)
    print("ПОИСК КОЛЛЕКЦИИ ХАРАКТЕРИСТИК НОМЕНКЛАТУРЫ")
    print("=" * 80)
    print()
    
    # Сначала получаем товар с характеристиками
    url = f"{API_URL.rstrip('/')}/Catalog_Номенклатура"
    params = {"$top": 100, "$filter": "ИспользоватьХарактеристики eq true"}
    
    try:
        async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
            print("1. Поиск товаров с характеристиками...")
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            items = data.get("value", [])
            
            if items:
                print(f"   ✓ Найдено товаров с характеристиками: {len(items)}")
                first_item = items[0]
                print(f"   Пример: Code={first_item.get('Code')}, Description={first_item.get('Description')}")
                
                # Проверяем навигационные ссылки
                print("\n2. Проверка навигационных ссылок на характеристики...")
                nav_keys = [k for k in first_item.keys() if "@navigationLinkUrl" in k or "navigation" in k.lower()]
                if nav_keys:
                    print(f"   Найдено навигационных ссылок: {len(nav_keys)}")
                    for key in nav_keys[:5]:
                        print(f"   - {key}")
                
                # Ищем товар с артикулом, который может быть характеристикой
                print("\n3. Поиск товаров с артикулами, содержащими S или G...")
                all_items_response = await client.get(url, params={"$top": 1000})
                all_items_response.raise_for_status()
                all_data = all_items_response.json()
                all_items = all_data.get("value", [])
                
                # Ищем товары с артикулами, содержащими S или G
                items_with_s_g = []
                for item in all_items:
                    article = item.get("Артикул", "")
                    if article and (article.endswith("S") or article.endswith("G") or "/" in article or "S" in article or "G" in article):
                        items_with_s_g.append(item)
                
                if items_with_s_g:
                    print(f"   ✓ Найдено товаров с артикулами S/G: {len(items_with_s_g)}")
                    print("\n   Примеры:")
                    for item in items_with_s_g[:5]:
                        code = item.get("Code", "")
                        article = item.get("Артикул", "")
                        desc = item.get("Description", "")
                        parent_key = item.get("Parent_Key", "")
                        print(f"   - Code: {code}, Артикул: {article}, Название: {desc[:50]}")
                        print(f"     Parent_Key: {parent_key}")
                
                # Пробуем получить характеристики через навигационную ссылку
                print("\n4. Попытка получить характеристики через навигацию...")
                if first_item.get("Ref_Key"):
                    ref_key = first_item.get("Ref_Key")
                    # Пробуем разные варианты получения характеристик
                    nav_urls = [
                        f"{url}(guid'{ref_key}')/ХарактеристикиНоменклатуры",
                        f"{url}(guid'{ref_key}')/Характеристики",
                        f"{url}(guid'{ref_key}')/Свойства",
                    ]
                    
                    for nav_url in nav_urls:
                        try:
                            nav_response = await client.get(nav_url)
                            if nav_response.status_code == 200:
                                nav_data = nav_response.json()
                                print(f"   ✓ Найдена навигация: {nav_url}")
                                print(f"     Данные: {json.dumps(nav_data, ensure_ascii=False, indent=2)[:500]}")
                                break
                        except:
                            pass
                
                # Сохраняем пример товара с характеристиками
                output_file = "product_with_characteristics.json"
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(first_item, f, ensure_ascii=False, indent=2, default=str)
                print(f"\n✓ Пример товара сохранен в: {output_file}")
                
            else:
                print("   ✗ Товаров с характеристиками не найдено")
            
            # Пробуем найти отдельную коллекцию характеристик
            print("\n5. Поиск отдельной коллекции характеристик...")
            for endpoint in possible_endpoints:
                try:
                    test_url = f"{API_URL.rstrip('/')}{endpoint}"
                    test_response = await client.get(test_url, params={"$top": 1})
                    if test_response.status_code == 200:
                        test_data = test_response.json()
                        if "value" in test_data and len(test_data["value"]) > 0:
                            print(f"   ✓ Найдена коллекция: {endpoint}")
                            print(f"     Пример записи: {json.dumps(test_data['value'][0], ensure_ascii=False, indent=2, default=str)[:300]}")
                except Exception as e:
                    pass
            
    except Exception as e:
        print(f"✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(find_characteristics())
