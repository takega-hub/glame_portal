"""
Пример выгрузки товара с характеристиками и артикулами
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


async def show_product_with_characteristics():
    """Показать пример товара с характеристиками"""
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    
    print("=" * 100)
    print("ПРИМЕР ВЫГРУЗКИ ТОВАРА С ХАРАКТЕРИСТИКАМИ И АРТИКУЛАМИ")
    print("=" * 100)
    print()
    
    async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
        url = f"{API_URL.rstrip('/')}/Catalog_Номенклатура"
        
        # 1. Находим основную карточку (без Parent_Key или с пустым Parent_Key)
        print("1. Поиск основной карточки товара...")
        
        try:
            # Получаем товары и фильтруем на стороне приложения
            response = await client.get(url, params={"$top": 500})
            response.raise_for_status()
            data = response.json()
            all_products = data.get("value", [])
            
            # Фильтруем основные карточки (без Parent_Key или с пустым Parent_Key)
            main_products = [
                p for p in all_products 
                if (not p.get("Parent_Key") or p.get("Parent_Key") == "00000000-0000-0000-0000-000000000000")
                and not p.get("IsFolder", False)  # Исключаем папки
            ]
            
            if main_products:
                # Берем первую основную карточку
                main_product = main_products[0]
                main_ref_key = main_product.get("Ref_Key")
                main_code = main_product.get("Code", "")
                main_name = main_product.get("Description", "")
                main_article = main_product.get("Артикул", "")
                
                print(f"   ✓ Найдена основная карточка:")
                print(f"     Ref_Key: {main_ref_key}")
                print(f"     Code (внутренний код 1С): {main_code}")
                print(f"     Название: {main_name}")
                print(f"     Артикул основной карточки: {main_article if main_article else '(нет)'}")
                print()
                
                # 2. Ищем характеристики этой карточки (с Parent_Key = main_ref_key)
                print("2. Поиск характеристик этой карточки...")
                characteristics_params = {"$top": 100}
                response = await client.get(url, params=characteristics_params)
                response.raise_for_status()
                data = response.json()
                all_items = data.get("value", [])
                
                characteristics = [
                    item for item in all_items
                    if item.get("Parent_Key") == main_ref_key
                ]
                
                if characteristics:
                    print(f"   ✓ Найдено характеристик: {len(characteristics)}\n")
                    
                    # Показываем структуру основной карточки
                    print("=" * 100)
                    print("ОСНОВНАЯ КАРТОЧКА ТОВАРА")
                    print("=" * 100)
                    print(json.dumps({
                        "Ref_Key": main_product.get("Ref_Key"),
                        "Code": main_product.get("Code"),
                        "Description": main_product.get("Description"),
                        "Артикул": main_product.get("Артикул"),
                        "Parent_Key": main_product.get("Parent_Key"),
                        "IsFolder": main_product.get("IsFolder"),
                    }, ensure_ascii=False, indent=2))
                    print()
                    
                    # Показываем характеристики
                    print("=" * 100)
                    print("ХАРАКТЕРИСТИКИ (с артикулами)")
                    print("=" * 100)
                    for idx, char in enumerate(characteristics[:5], 1):  # Показываем первые 5
                        char_code = char.get("Code", "")
                        char_name = char.get("Description", "")
                        char_article = char.get("Артикул", "")
                        char_parent = char.get("Parent_Key", "")
                        
                        print(f"\nХарактеристика #{idx}:")
                        print(json.dumps({
                            "Ref_Key": char.get("Ref_Key"),
                            "Code": char_code,
                            "Description": char_name,
                            "Артикул": char_article,
                            "Parent_Key": char_parent,
                            "IsFolder": char.get("IsFolder"),
                        }, ensure_ascii=False, indent=2))
                        
                        # Показываем дополнительные поля, которые могут быть характеристиками
                        char_specs = {}
                        for key, value in char.items():
                            if key not in ["Ref_Key", "Code", "Description", "Артикул", "Parent_Key", 
                                         "DataVersion", "DeletionMark", "IsFolder", "Predefined", 
                                         "PredefinedDataName", "ДатаИзменения"]:
                                if value is not None and value != "" and value != "00000000-0000-0000-0000-000000000000":
                                    if not isinstance(value, dict) or (isinstance(value, dict) and len(value) > 2):
                                        char_specs[key] = value
                        
                        if char_specs:
                            print(f"   Дополнительные характеристики:")
                            for spec_key, spec_value in list(char_specs.items())[:10]:  # Первые 10
                                if isinstance(spec_value, dict):
                                    spec_value = f"{{объект: {spec_value.get('Description', 'ссылка')}}}"
                                print(f"     {spec_key}: {spec_value}")
                    
                    # Сохраняем пример в файл
                    example_data = {
                        "main_product": {
                            "Ref_Key": main_product.get("Ref_Key"),
                            "Code": main_product.get("Code"),
                            "Description": main_product.get("Description"),
                            "Артикул": main_product.get("Артикул"),
                            "Parent_Key": main_product.get("Parent_Key"),
                        },
                        "characteristics": [
                            {
                                "Ref_Key": char.get("Ref_Key"),
                                "Code": char.get("Code"),
                                "Description": char.get("Description"),
                                "Артикул": char.get("Артикул"),
                                "Parent_Key": char.get("Parent_Key"),
                            }
                            for char in characteristics[:10]
                        ]
                    }
                    
                    with open("product_with_characteristics_example.json", "w", encoding="utf-8") as f:
                        json.dump(example_data, f, ensure_ascii=False, indent=2, default=str)
                    
                    print(f"\n✓ Пример сохранен в: product_with_characteristics_example.json")
                    
                    # Показываем маппинг
                    print("\n" + "=" * 100)
                    print("МАППИНГ В НАШУ БД")
                    print("=" * 100)
                    print("\nОсновная карточка:")
                    print(f"  external_id = {main_product.get('Ref_Key')} (Ref_Key)")
                    print(f"  external_code = {main_code} (Code - внутренний код 1С)")
                    print(f"  article = {main_article if main_article else '(нет)'} (Артикул)")
                    print(f"  name = {main_name} (Description)")
                    
                    print("\nХарактеристики (каждая как отдельный товар):")
                    for char in characteristics[:3]:
                        char_code = char.get("Code", "")
                        char_article = char.get("Артикул", "")
                        print(f"\n  Характеристика: {char.get('Description', '')}")
                        print(f"    external_id = {char.get('Ref_Key')} (Ref_Key)")
                        print(f"    external_code = {char_code} (Code - внутренний код 1С)")
                        print(f"    article = {char_article if char_article else '(нет)'} (Артикул характеристики)")
                        print(f"    specifications['parent_external_id'] = {char.get('Parent_Key')} (Parent_Key)")
                        print(f"    name = {char.get('Description', '')} (Description)")
                else:
                    print("   ✗ Характеристики не найдены для этой карточки")
                    print(f"   Ищем другой пример...")
                    
                    # Ищем любые товары с Parent_Key
                    items_with_parent = [
                        item for item in all_items
                        if item.get("Parent_Key") and item.get("Parent_Key") != "00000000-0000-0000-0000-000000000000"
                    ]
                    
                    if items_with_parent:
                        # Берем первую характеристику
                        example_char = items_with_parent[0]
                        example_parent_key = example_char.get("Parent_Key")
                        
                        # Ищем основную карточку по Parent_Key
                        main_product_by_key = next(
                            (p for p in all_items if p.get("Ref_Key") == example_parent_key),
                            None
                        )
                        
                        if main_product_by_key:
                            # Находим все характеристики этой карточки
                            characteristics = [
                                item for item in all_items
                                if item.get("Parent_Key") == example_parent_key
                            ]
                            
                            if characteristics:
                                print(f"   ✓ Найдена основная карточка с характеристиками!")
                                print()
                                
                                # Показываем структуру основной карточки
                                print("=" * 100)
                                print("ОСНОВНАЯ КАРТОЧКА ТОВАРА")
                                print("=" * 100)
                                main_display = {
                                    "Ref_Key": main_product_by_key.get("Ref_Key"),
                                    "Code": main_product_by_key.get("Code"),
                                    "Description": main_product_by_key.get("Description"),
                                    "Артикул": main_product_by_key.get("Артикул"),
                                    "Parent_Key": main_product_by_key.get("Parent_Key"),
                                    "IsFolder": main_product_by_key.get("IsFolder"),
                                }
                                print(json.dumps(main_display, ensure_ascii=False, indent=2))
                                print()
                                
                                # Показываем характеристики
                                print("=" * 100)
                                print(f"ХАРАКТЕРИСТИКИ (найдено {len(characteristics)})")
                                print("=" * 100)
                                for idx, char in enumerate(characteristics[:5], 1):  # Показываем первые 5
                                    print(f"\nХарактеристика #{idx}:")
                                    char_display = {
                                        "Ref_Key": char.get("Ref_Key"),
                                        "Code": char.get("Code"),
                                        "Description": char.get("Description"),
                                        "Артикул": char.get("Артикул"),
                                        "Parent_Key": char.get("Parent_Key"),
                                        "IsFolder": char.get("IsFolder"),
                                    }
                                    print(json.dumps(char_display, ensure_ascii=False, indent=2))
                                    
                                    # Показываем дополнительные поля, которые могут быть характеристиками
                                    char_specs = {}
                                    for key, value in char.items():
                                        if key not in ["Ref_Key", "Code", "Description", "Артикул", "Parent_Key", 
                                                     "DataVersion", "DeletionMark", "IsFolder", "Predefined", 
                                                     "PredefinedDataName", "ДатаИзменения"]:
                                            if value is not None and value != "" and value != "00000000-0000-0000-0000-000000000000":
                                                if not isinstance(value, dict) or (isinstance(value, dict) and len(value) > 2):
                                                    char_specs[key] = value
                                    
                                    if char_specs:
                                        print(f"   Дополнительные характеристики:")
                                        for spec_key, spec_value in list(char_specs.items())[:10]:  # Первые 10
                                            if isinstance(spec_value, dict):
                                                spec_value = f"{{объект: {spec_value.get('Description', 'ссылка')}}}"
                                            print(f"     {spec_key}: {spec_value}")
                                
                                # Сохраняем пример в файл
                                example_data = {
                                    "main_product": main_display,
                                    "characteristics": [
                                        {
                                            "Ref_Key": char.get("Ref_Key"),
                                            "Code": char.get("Code"),
                                            "Description": char.get("Description"),
                                            "Артикул": char.get("Артикул"),
                                            "Parent_Key": char.get("Parent_Key"),
                                        }
                                        for char in characteristics[:10]
                                    ]
                                }
                                
                                with open("product_with_characteristics_example.json", "w", encoding="utf-8") as f:
                                    json.dump(example_data, f, ensure_ascii=False, indent=2, default=str)
                                
                                print(f"\n✓ Пример сохранен в: product_with_characteristics_example.json")
                                
                                # Показываем маппинг
                                print("\n" + "=" * 100)
                                print("МАППИНГ В НАШУ БД")
                                print("=" * 100)
                                print("\nОсновная карточка:")
                                print(f"  external_id = {main_product_by_key.get('Ref_Key')} (Ref_Key)")
                                print(f"  external_code = {main_product_by_key.get('Code')} (Code - внутренний код 1С)")
                                print(f"  article = {main_product_by_key.get('Артикул') if main_product_by_key.get('Артикул') else '(нет)'} (Артикул)")
                                print(f"  name = {main_product_by_key.get('Description')} (Description)")
                                
                                print("\nХарактеристики (каждая как отдельный товар):")
                                for char in characteristics[:3]:
                                    char_code = char.get("Code", "")
                                    char_article = char.get("Артикул", "")
                                    print(f"\n  Характеристика: {char.get('Description', '')}")
                                    print(f"    external_id = {char.get('Ref_Key')} (Ref_Key)")
                                    print(f"    external_code = {char_code} (Code - внутренний код 1С)")
                                    print(f"    article = {char_article if char_article else '(нет)'} (Артикул характеристики)")
                                    print(f"    specifications['parent_external_id'] = {char.get('Parent_Key')} (Parent_Key)")
                                    print(f"    name = {char.get('Description', '')} (Description)")
            else:
                print("   ✗ Основные карточки не найдены")
                
        except Exception as e:
            print(f"✗ Ошибка: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(show_product_with_characteristics())
