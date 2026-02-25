"""
Получение характеристик с названиями свойств и значений
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


async def get_characteristics_with_names():
    """Получение характеристик с названиями"""
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    
    print("=" * 100)
    print("ПОЛУЧЕНИЕ ХАРАКТЕРИСТИК С НАЗВАНИЯМИ")
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
        
        print(f"   ✓ Найдена характеристика: {char.get('Description')} (Артикул: {char.get('Артикул')})")
        print()
        
        # 2. Получаем характеристики из Catalog_ХарактеристикиНоменклатуры
        print("2. Получение характеристик из Catalog_ХарактеристикиНоменклатуры...")
        char_catalog_url = f"{API_URL.rstrip('/')}/Catalog_ХарактеристикиНоменклатуры"
        
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
            # Если не нашли, берем первую для примера
            if all_char_items:
                related_chars = [all_char_items[0]]
                print(f"   Не найдено по Owner, используем пример из коллекции")
        
        if not related_chars:
            print("   ✗ Характеристики не найдены")
            return
        
        char_item = related_chars[0]
        print(f"   ✓ Найдена запись характеристик\n")
        
        # 3. Получаем коллекции свойств и значений
        print("3. Поиск коллекций свойств и значений...")
        
        # Пробуем найти коллекцию свойств
        properties_collections = [
            "Catalog_СвойстваНоменклатуры",
            "Catalog_Свойства",
            "Catalog_СвойстваОбъектов",
        ]
        
        properties_map = {}
        for coll_name in properties_collections:
            try:
                coll_url = f"{API_URL.rstrip('/')}/{coll_name}"
                coll_response = await client.get(coll_url, params={"$top": 200})
                if coll_response.status_code == 200:
                    coll_data = coll_response.json()
                    props = coll_data.get("value", [])
                    if props:
                        print(f"   ✓ Найдена коллекция свойств: {coll_name} ({len(props)} записей)")
                        for prop in props:
                            prop_key = prop.get("Ref_Key")
                            if prop_key:
                                properties_map[prop_key] = prop.get("Description", prop.get("Code", ""))
                        break
            except:
                pass
        
        # Пробуем найти коллекцию значений
        values_collections = [
            "Catalog_ЗначенияСвойствОбъектов",
            "Catalog_ЗначенияСвойств",
            "Catalog_ЗначенияСвойствНоменклатуры",
        ]
        
        values_map = {}
        for coll_name in values_collections:
            try:
                coll_url = f"{API_URL.rstrip('/')}/{coll_name}"
                coll_response = await client.get(coll_url, params={"$top": 200})
                if coll_response.status_code == 200:
                    coll_data = coll_response.json()
                    vals = coll_data.get("value", [])
                    if vals:
                        print(f"   ✓ Найдена коллекция значений: {coll_name} ({len(vals)} записей)")
                        for val in vals:
                            val_key = val.get("Ref_Key")
                            if val_key:
                                values_map[val_key] = val.get("Description", val.get("Code", ""))
                        break
            except:
                pass
        
        # 4. Анализируем ДополнительныеРеквизиты
        print("\n" + "=" * 100)
        print("ХАРАКТЕРИСТИКИ С НАЗВАНИЯМИ")
        print("=" * 100)
        
        dop_rekv = char_item.get("ДополнительныеРеквизиты", [])
        if dop_rekv:
            print(f"\nНайдено характеристик: {len(dop_rekv)}\n")
            
            characteristics_list = []
            for rek in dop_rekv:
                property_key = rek.get("Свойство_Key")
                value_key = rek.get("Значение")
                
                property_name = properties_map.get(property_key, f"Свойство ({property_key[:8]}...)")
                value_name = values_map.get(value_key, f"Значение ({value_key[:8]}...)")
                
                # Формат: "Категория (Тип): Значение"
                char_display = f"{property_name}: {value_name}"
                characteristics_list.append({
                    "property_key": property_key,
                    "property_name": property_name,
                    "value_key": value_key,
                    "value_name": value_name,
                    "display": char_display
                })
                
                print(f"  {char_display}")
            
            # Сохраняем результат
            result = {
                "product": {
                    "Ref_Key": char_ref_key,
                    "Code": char.get("Code"),
                    "Description": char.get("Description"),
                    "Артикул": char.get("Артикул"),
                },
                "characteristics": characteristics_list,
                "properties_map_sample": dict(list(properties_map.items())[:10]),
                "values_map_sample": dict(list(values_map.items())[:10]),
            }
            
            with open("characteristics_with_names.json", "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)
            
            print(f"\n✓ Результат сохранен в: characteristics_with_names.json")
            
            # Показываем примеры свойств и значений
            if properties_map:
                print("\n" + "=" * 100)
                print("ПРИМЕРЫ СВОЙСТВ")
                print("=" * 100)
                for key, name in list(properties_map.items())[:10]:
                    print(f"  {key[:36]}... → {name}")
            
            if values_map:
                print("\n" + "=" * 100)
                print("ПРИМЕРЫ ЗНАЧЕНИЙ")
                print("=" * 100)
                for key, name in list(values_map.items())[:10]:
                    print(f"  {key[:36]}... → {name}")
        else:
            print("Дополнительные реквизиты не найдены или пусты")


if __name__ == "__main__":
    asyncio.run(get_characteristics_with_names())
