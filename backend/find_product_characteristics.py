"""
Поиск характеристик товаров в 1С
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
    """Поиск характеристик товаров в 1С"""
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    
    print("=" * 100)
    print("ПОИСК ХАРАКТЕРИСТИК ТОВАРОВ В 1С")
    print("=" * 100)
    print()
    
    async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
        url = f"{API_URL.rstrip('/')}/Catalog_Номенклатура"
        
        # 1. Находим основную карточку с кодом НФ
        print("1. Поиск основной карточки с кодом НФ...")
        response = await client.get(url, params={"$top": 500})
        response.raise_for_status()
        data = response.json()
        all_items = data.get("value", [])
        
        # Ищем основную карточку (Parent_Key пустой, Code начинается с НФ)
        main_products = [
            p for p in all_items
            if (not p.get("Parent_Key") or p.get("Parent_Key") == "00000000-0000-0000-0000-000000000000")
            and p.get("Code", "").startswith("НФ-")
            and not p.get("IsFolder", False)
        ]
        
        if not main_products:
            # Если не нашли, ищем любую основную карточку
            main_products = [
                p for p in all_items
                if (not p.get("Parent_Key") or p.get("Parent_Key") == "00000000-0000-0000-0000-000000000000")
                and not p.get("IsFolder", False)
            ]
        
        if main_products:
            main_product = main_products[0]
            main_ref_key = main_product.get("Ref_Key")
            main_code = main_product.get("Code", "")
            main_name = main_product.get("Description", "")
            
            print(f"   ✓ Найдена основная карточка:")
            print(f"     Ref_Key: {main_ref_key}")
            print(f"     Code: {main_code}")
            print(f"     Название: {main_name}")
            print()
            
            # 2. Ищем характеристики этой карточки
            print("2. Поиск характеристик этой карточки...")
            characteristics = [
                item for item in all_items
                if item.get("Parent_Key") == main_ref_key
            ]
            
            if characteristics:
                print(f"   ✓ Найдено характеристик: {len(characteristics)}\n")
                
                # Берем первую характеристику для детального анализа
                char = characteristics[0]
                char_ref_key = char.get("Ref_Key")
                char_code = char.get("Code", "")
                char_name = char.get("Description", "")
                char_article = char.get("Артикул", "")
                
                print("=" * 100)
                print("ПРИМЕР ХАРАКТЕРИСТИКИ")
                print("=" * 100)
                print(json.dumps({
                    "Ref_Key": char_ref_key,
                    "Code": char_code,
                    "Description": char_name,
                    "Артикул": char_article,
                    "Parent_Key": char.get("Parent_Key"),
                }, ensure_ascii=False, indent=2))
                print()
                
                # 3. Ищем поля, которые могут быть характеристиками (Цвет, Материал, Вставка и т.д.)
                print("=" * 100)
                print("ПОЛЯ ХАРАКТЕРИСТИКИ (поиск полей типа 'Цвет (Украшения)', 'Материал (Украшения)' и т.д.)")
                print("=" * 100)
                
                # Собираем все поля характеристики
                char_fields = {}
                for key, value in char.items():
                    if value is not None and value != "" and value != "00000000-0000-0000-0000-000000000000":
                        # Пропускаем служебные поля
                        if key not in ["Ref_Key", "Code", "Description", "Артикул", "Parent_Key", 
                                     "DataVersion", "DeletionMark", "IsFolder", "Predefined", 
                                     "PredefinedDataName", "ДатаИзменения"]:
                            # Пропускаем объекты-ссылки (только Key/Description)
                            if isinstance(value, dict):
                                if not set(value.keys()).issubset({"Key", "Description", "key", "description", "ref_key"}):
                                    char_fields[key] = value
                            else:
                                char_fields[key] = value
                
                # Ищем поля, которые могут содержать характеристики в формате "Категория (Тип): Значение"
                print("\nВсе поля характеристики:")
                for key, value in sorted(char_fields.items()):
                    if isinstance(value, dict):
                        value_str = f"{{объект: {value.get('Description', 'ссылка')}}}"
                    else:
                        value_str = str(value)
                        if len(value_str) > 100:
                            value_str = value_str[:97] + "..."
                    print(f"  {key}: {value_str}")
                
                # 4. Проверяем навигационные ссылки для получения характеристик
                print("\n" + "=" * 100)
                print("ПРОВЕРКА НАВИГАЦИОННЫХ ССЫЛОК")
                print("=" * 100)
                
                # Пробуем получить характеристики через навигацию
                nav_urls = [
                    f"{url}(guid'{char_ref_key}')/ХарактеристикиНоменклатуры",
                    f"{url}(guid'{char_ref_key}')/Характеристики",
                    f"{url}(guid'{char_ref_key}')/Свойства",
                    f"{url}(guid'{char_ref_key}')/ДополнительныеРеквизиты",
                ]
                
                for nav_url in nav_urls:
                    try:
                        nav_response = await client.get(nav_url)
                        if nav_response.status_code == 200:
                            nav_data = nav_response.json()
                            print(f"\n✓ Найдена навигация: {nav_url}")
                            print(json.dumps(nav_data, ensure_ascii=False, indent=2, default=str)[:500])
                            break
                    except:
                        pass
                
                # 5. Проверяем коллекцию Catalog_ХарактеристикиНоменклатуры
                print("\n" + "=" * 100)
                print("ПРОВЕРКА КОЛЛЕКЦИИ Catalog_ХарактеристикиНоменклатуры")
                print("=" * 100)
                
                char_catalog_url = f"{API_URL.rstrip('/')}/Catalog_ХарактеристикиНоменклатуры"
                try:
                    char_response = await client.get(char_catalog_url, params={"$top": 10, "$filter": f"Owner eq guid'{char_ref_key}'"})
                    if char_response.status_code == 200:
                        char_data = char_response.json()
                        char_items = char_data.get("value", [])
                        if char_items:
                            print(f"✓ Найдено записей в Catalog_ХарактеристикиНоменклатуры: {len(char_items)}")
                            print("\nПример записи:")
                            print(json.dumps(char_items[0], ensure_ascii=False, indent=2, default=str)[:500])
                        else:
                            print("Результат пуст (возможно, нужен другой фильтр)")
                    else:
                        print(f"HTTP {char_response.status_code}")
                except Exception as e:
                    print(f"Ошибка: {e}")
                
                # 6. Ищем поля с категориями и группами
                print("\n" + "=" * 100)
                print("ПОИСК ПОЛЕЙ С КАТЕГОРИЯМИ И ГРУППАМИ")
                print("=" * 100)
                
                # Ищем поля, содержащие "Категория", "Группа", "Украшения"
                category_fields = {}
                for key, value in char.items():
                    key_lower = key.lower()
                    if any(keyword in key_lower for keyword in ["категория", "группа", "украшения", "category", "group"]):
                        if value is not None and value != "":
                            category_fields[key] = value
                
                if category_fields:
                    print("\nНайденные поля с категориями/группами:")
                    for key, value in category_fields.items():
                        if isinstance(value, dict):
                            print(f"  {key}: {value.get('Description', value)}")
                        else:
                            print(f"  {key}: {value}")
                else:
                    print("Поля с категориями/группами не найдены в основных полях")
                
                # Сохраняем пример
                example_data = {
                    "main_product": {
                        "Ref_Key": main_product.get("Ref_Key"),
                        "Code": main_product.get("Code"),
                        "Description": main_product.get("Description"),
                        "Артикул": main_product.get("Артикул"),
                    },
                    "characteristic": {
                        "Ref_Key": char.get("Ref_Key"),
                        "Code": char.get("Code"),
                        "Description": char.get("Description"),
                        "Артикул": char.get("Артикул"),
                        "Parent_Key": char.get("Parent_Key"),
                    },
                    "all_fields": char_fields,
                    "category_fields": category_fields,
                }
                
                with open("product_characteristics_analysis.json", "w", encoding="utf-8") as f:
                    json.dump(example_data, f, ensure_ascii=False, indent=2, default=str)
                
                print(f"\n✓ Данные сохранены в: product_characteristics_analysis.json")
                
            else:
                print("   ✗ Характеристики не найдены для этой карточки")
                print("   Ищем товары с Parent_Key...")
                
                items_with_parent = [
                    item for item in all_items
                    if item.get("Parent_Key") and item.get("Parent_Key") != "00000000-0000-0000-0000-000000000000"
                ]
                
                if items_with_parent:
                    print(f"   Найдено товаров с Parent_Key: {len(items_with_parent)}")
                    
                    # Берем первую характеристику для детального анализа
                    example = items_with_parent[0]
                    parent_key = example.get("Parent_Key")
                    
                    # Находим родителя
                    parent = next((p for p in all_items if p.get("Ref_Key") == parent_key), None)
                    if parent:
                        print(f"\n   Пример:")
                        print(f"     Родитель: {parent.get('Code')} - {parent.get('Description')}")
                        print(f"     Характеристика: {example.get('Code')} - {example.get('Description')}")
                        print(f"     Артикул характеристики: {example.get('Артикул')}")
                        
                        # Детальный анализ характеристики
                        print("\n" + "=" * 100)
                        print("ДЕТАЛЬНЫЙ АНАЛИЗ ХАРАКТЕРИСТИКИ")
                        print("=" * 100)
                        
                        # Собираем все поля характеристики
                        char_fields = {}
                        for key, value in example.items():
                            if value is not None and value != "" and value != "00000000-0000-0000-0000-000000000000":
                                # Пропускаем служебные поля
                                if key not in ["Ref_Key", "Code", "Description", "Артикул", "Parent_Key", 
                                             "DataVersion", "DeletionMark", "IsFolder", "Predefined", 
                                             "PredefinedDataName", "ДатаИзменения"]:
                                    # Пропускаем объекты-ссылки (только Key/Description)
                                    if isinstance(value, dict):
                                        if not set(value.keys()).issubset({"Key", "Description", "key", "description", "ref_key"}):
                                            char_fields[key] = value
                                    else:
                                        char_fields[key] = value
                        
                        print("\nВсе поля характеристики (кроме служебных):")
                        for key, value in sorted(char_fields.items()):
                            if isinstance(value, dict):
                                value_str = f"{{объект: {value.get('Description', 'ссылка')}}}"
                            else:
                                value_str = str(value)
                                if len(value_str) > 100:
                                    value_str = value_str[:97] + "..."
                            print(f"  {key}: {value_str}")
                        
                        # Ищем поля, которые могут содержать характеристики в формате "Категория (Тип): Значение"
                        print("\n" + "=" * 100)
                        print("ПОИСК ХАРАКТЕРИСТИК В ФОРМАТЕ 'Категория (Тип): Значение'")
                        print("=" * 100)
                        
                        # Ищем поля, содержащие ключевые слова
                        characteristic_keywords = ["цвет", "материал", "вставка", "покрытие", "замок", "размер", 
                                                 "color", "material", "insert", "coating", "clasp", "size"]
                        
                        found_characteristics = {}
                        for key, value in char_fields.items():
                            key_lower = key.lower()
                            value_str = str(value).lower() if value else ""
                            
                            # Проверяем, содержит ли поле ключевые слова
                            if any(keyword in key_lower or keyword in value_str for keyword in characteristic_keywords):
                                found_characteristics[key] = value
                        
                        if found_characteristics:
                            print("\nНайденные поля, которые могут быть характеристиками:")
                            for key, value in found_characteristics.items():
                                if isinstance(value, dict):
                                    print(f"  {key}: {value.get('Description', value)}")
                                else:
                                    print(f"  {key}: {value}")
                        
                        # Проверяем коллекцию Catalog_ХарактеристикиНоменклатуры
                        print("\n" + "=" * 100)
                        print("ПРОВЕРКА КОЛЛЕКЦИИ Catalog_ХарактеристикиНоменклатуры")
                        print("=" * 100)
                        
                        char_catalog_url = f"{API_URL.rstrip('/')}/Catalog_ХарактеристикиНоменклатуры"
                        try:
                            # Пробуем получить характеристики через Owner
                            char_response = await client.get(char_catalog_url, params={"$top": 20})
                            if char_response.status_code == 200:
                                char_data = char_response.json()
                                char_items = char_data.get("value", [])
                                if char_items:
                                    print(f"✓ Найдено записей в Catalog_ХарактеристикиНоменклатуры: {len(char_items)}")
                                    
                                    # Ищем записи, связанные с нашей характеристикой
                                    related_chars = [
                                        item for item in char_items
                                        if item.get("Owner") == example.get("Ref_Key")
                                    ]
                                    
                                    if related_chars:
                                        print(f"\n✓ Найдено связанных характеристик: {len(related_chars)}")
                                        print("\nПример связанной характеристики:")
                                        print(json.dumps(related_chars[0], ensure_ascii=False, indent=2, default=str))
                                    else:
                                        print("\nПример записи из Catalog_ХарактеристикиНоменклатуры:")
                                        print(json.dumps(char_items[0], ensure_ascii=False, indent=2, default=str)[:800])
                                else:
                                    print("Результат пуст")
                            else:
                                print(f"HTTP {char_response.status_code}")
                        except Exception as e:
                            print(f"Ошибка: {e}")
                        
                        # Сохраняем пример
                        example_data = {
                            "main_product": {
                                "Ref_Key": parent.get("Ref_Key"),
                                "Code": parent.get("Code"),
                                "Description": parent.get("Description"),
                                "Артикул": parent.get("Артикул"),
                            },
                            "characteristic": {
                                "Ref_Key": example.get("Ref_Key"),
                                "Code": example.get("Code"),
                                "Description": example.get("Description"),
                                "Артикул": example.get("Артикул"),
                                "Parent_Key": example.get("Parent_Key"),
                            },
                            "all_fields": char_fields,
                            "found_characteristics": found_characteristics,
                        }
                        
                        with open("product_characteristics_analysis.json", "w", encoding="utf-8") as f:
                            json.dump(example_data, f, ensure_ascii=False, indent=2, default=str)
                        
                        print(f"\n✓ Данные сохранены в: product_characteristics_analysis.json")
        else:
            print("   ✗ Основные карточки не найдены")


if __name__ == "__main__":
    asyncio.run(find_characteristics())
