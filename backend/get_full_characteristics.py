"""
Получение полных характеристик товара из Catalog_ХарактеристикиНоменклатуры
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


async def get_full_characteristics():
    """Получение полных характеристик товара"""
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    
    print("=" * 100)
    print("ПОЛУЧЕНИЕ ПОЛНЫХ ХАРАКТЕРИСТИК ТОВАРА")
    print("=" * 100)
    print()
    
    async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
        # 1. Находим товар с характеристиками
        print("1. Поиск товара с характеристиками...")
        nom_url = f"{API_URL.rstrip('/')}/Catalog_Номенклатура"
        response = await client.get(nom_url, params={"$top": 500})
        response.raise_for_status()
        data = response.json()
        all_items = data.get("value", [])
        
        # Находим характеристику (с Parent_Key и артикулом)
        characteristics = [
            item for item in all_items
            if item.get("Parent_Key") and item.get("Parent_Key") != "00000000-0000-0000-0000-000000000000"
            and item.get("Артикул")
        ]
        
        if not characteristics:
            print("   ✗ Характеристики не найдены")
            return
        
        char = characteristics[0]
        char_ref_key = char.get("Ref_Key")
        char_code = char.get("Code", "")
        char_name = char.get("Description", "")
        char_article = char.get("Артикул", "")
        
        print(f"   ✓ Найдена характеристика:")
        print(f"     Ref_Key: {char_ref_key}")
        print(f"     Code: {char_code}")
        print(f"     Название: {char_name}")
        print(f"     Артикул: {char_article}")
        print()
        
        # 2. Получаем характеристики из Catalog_ХарактеристикиНоменклатуры
        print("2. Получение характеристик из Catalog_ХарактеристикиНоменклатуры...")
        char_catalog_url = f"{API_URL.rstrip('/')}/Catalog_ХарактеристикиНоменклатуры"
        
        # Получаем все характеристики
        response = await client.get(char_catalog_url, params={"$top": 100})
        response.raise_for_status()
        char_data = response.json()
        all_char_items = char_data.get("value", [])
        
        # Ищем характеристики, связанные с нашим товаром
        related_chars = [
            item for item in all_char_items
            if item.get("Owner") == char_ref_key
        ]
        
        if not related_chars:
            # Если не нашли по Owner, пробуем найти по описанию или артикулу
            print("   Не найдено по Owner, ищем по другим признакам...")
            # Берем первую запись для анализа
            if all_char_items:
                related_chars = [all_char_items[0]]
        
        if related_chars:
            char_item = related_chars[0]
            print(f"   ✓ Найдена запись характеристик\n")
            
            print("=" * 100)
            print("ПОЛНАЯ СТРУКТУРА ХАРАКТЕРИСТИКИ")
            print("=" * 100)
            print(json.dumps(char_item, ensure_ascii=False, indent=2, default=str))
            print()
            
            # 3. Анализируем ДополнительныеРеквизиты
            print("=" * 100)
            print("АНАЛИЗ ДОПОЛНИТЕЛЬНЫХ РЕКВИЗИТОВ")
            print("=" * 100)
            
            dop_rekv = char_item.get("ДополнительныеРеквизиты", [])
            if dop_rekv:
                print(f"\nНайдено дополнительных реквизитов: {len(dop_rekv)}\n")
                
                # Получаем информацию о свойствах
                print("Дополнительные реквизиты:")
                for idx, rek in enumerate(dop_rekv[:10], 1):
                    property_key = rek.get("Свойство_Key")
                    value_key = rek.get("Значение")
                    
                    print(f"\n  Реквизит #{idx}:")
                    print(f"    Свойство_Key: {property_key}")
                    print(f"    Значение: {value_key}")
                    print(f"    LineNumber: {rek.get('LineNumber')}")
                    
                    # Пробуем получить информацию о свойстве
                    if property_key:
                        # Проверяем, есть ли коллекция свойств
                        properties_urls = [
                            f"{API_URL.rstrip('/')}/Catalog_СвойстваНоменклатуры",
                            f"{API_URL.rstrip('/')}/Catalog_Свойства",
                            f"{API_URL.rstrip('/')}/InformationRegister_Свойства",
                        ]
                        
                        for prop_url in properties_urls:
                            try:
                                prop_response = await client.get(prop_url, params={"$top": 100})
                                if prop_response.status_code == 200:
                                    prop_data = prop_response.json()
                                    props = prop_data.get("value", [])
                                    
                                    # Ищем свойство по ключу
                                    prop = next((p for p in props if p.get("Ref_Key") == property_key), None)
                                    if prop:
                                        print(f"    ✓ Найдено свойство: {prop.get('Description', prop.get('Code', 'N/A'))}")
                                        break
                            except:
                                pass
                    
                    # Пробуем получить информацию о значении
                    if value_key:
                        # Проверяем, есть ли коллекция значений
                        values_urls = [
                            f"{API_URL.rstrip('/')}/Catalog_ЗначенияСвойствНоменклатуры",
                            f"{API_URL.rstrip('/')}/Catalog_ЗначенияСвойств",
                            f"{API_URL.rstrip('/')}/InformationRegister_ЗначенияСвойств",
                        ]
                        
                        for val_url in values_urls:
                            try:
                                val_response = await client.get(val_url, params={"$top": 100})
                                if val_response.status_code == 200:
                                    val_data = val_response.json()
                                    vals = val_data.get("value", [])
                                    
                                    # Ищем значение по ключу
                                    val = next((v for v in vals if v.get("Ref_Key") == value_key), None)
                                    if val:
                                        print(f"    ✓ Найдено значение: {val.get('Description', val.get('Code', 'N/A'))}")
                                        break
                            except:
                                pass
            else:
                print("Дополнительные реквизиты не найдены или пусты")
            
            # 4. Сохраняем полные данные
            with open("full_characteristics_example.json", "w", encoding="utf-8") as f:
                json.dump({
                    "product": {
                        "Ref_Key": char_ref_key,
                        "Code": char_code,
                        "Description": char_name,
                        "Артикул": char_article,
                    },
                    "characteristics_record": char_item,
                    "additional_requisites": dop_rekv,
                }, f, ensure_ascii=False, indent=2, default=str)
            
            print(f"\n✓ Полные данные сохранены в: full_characteristics_example.json")
            
            # 5. Пробуем найти коллекции свойств и значений
            print("\n" + "=" * 100)
            print("ПОИСК КОЛЛЕКЦИЙ СВОЙСТВ И ЗНАЧЕНИЙ")
            print("=" * 100)
            
            possible_collections = [
                "Catalog_СвойстваНоменклатуры",
                "Catalog_Свойства",
                "Catalog_ЗначенияСвойствНоменклатуры",
                "Catalog_ЗначенияСвойств",
                "Catalog_ГруппыСвойств",
                "InformationRegister_Свойства",
            ]
            
            for coll_name in possible_collections:
                try:
                    coll_url = f"{API_URL.rstrip('/')}/{coll_name}"
                    coll_response = await client.get(coll_url, params={"$top": 5})
                    if coll_response.status_code == 200:
                        coll_data = coll_response.json()
                        coll_items = coll_data.get("value", [])
                        if coll_items:
                            print(f"\n✓ Найдена коллекция: {coll_name}")
                            print(f"  Пример записи:")
                            print(json.dumps(coll_items[0], ensure_ascii=False, indent=2, default=str)[:400])
                except:
                    pass


if __name__ == "__main__":
    asyncio.run(get_full_characteristics())
