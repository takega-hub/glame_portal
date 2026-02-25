"""
Получение свойства через Owner_Key значения
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


async def get_property_by_owner():
    """Получение свойства через Owner_Key"""
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    
    print("=" * 100)
    print("ПОЛУЧЕНИЕ СВОЙСТВА ЧЕРЕЗ Owner_Key ЗНАЧЕНИЯ")
    print("=" * 100)
    print()
    
    async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
        # 1. Получаем пример характеристики
        char_catalog_url = f"{API_URL.rstrip('/')}/Catalog_ХарактеристикиНоменклатуры"
        response = await client.get(char_catalog_url, params={"$top": 1})
        response.raise_for_status()
        char_data = response.json()
        char_items = char_data.get("value", [])
        
        if not char_items:
            print("✗ Характеристики не найдены")
            return
        
        char_item = char_items[0]
        dop_rekv = char_item.get("ДополнительныеРеквизиты", [])
        
        if not dop_rekv:
            print("✗ Дополнительные реквизиты не найдены")
            return
        
        # 2. Получаем значение и извлекаем Owner_Key
        first_rek = dop_rekv[0]
        value_key = first_rek.get("Значение")
        property_key = first_rek.get("Свойство_Key")
        
        print(f"Свойство_Key: {property_key}")
        print(f"Значение: {value_key}")
        print()
        
        # Получаем значение
        val_url = f"{API_URL.rstrip('/')}/Catalog_ЗначенияСвойствОбъектов(guid'{value_key}')"
        val_response = await client.get(val_url)
        val_response.raise_for_status()
        val_data = val_response.json()
        
        owner_key = val_data.get("Owner_Key")
        value_description = val_data.get("Description", "")
        
        print(f"Значение: {value_description}")
        print(f"Owner_Key (ключ свойства): {owner_key}")
        print()
        
        # 3. Пробуем получить свойство через Owner_Key
        print("=" * 100)
        print("ПОЛУЧЕНИЕ СВОЙСТВА")
        print("=" * 100)
        
        # Пробуем разные коллекции свойств
        properties_collections = [
            "Catalog_СвойстваНоменклатуры",
            "Catalog_Свойства",
            "Catalog_СвойстваОбъектов",
        ]
        
        property_found = False
        for coll_name in properties_collections:
            try:
                prop_url = f"{API_URL.rstrip('/')}/{coll_name}(guid'{owner_key}')"
                prop_response = await client.get(prop_url)
                if prop_response.status_code == 200:
                    prop_data = prop_response.json()
                    print(f"\n✓ Найден способ получения свойства: {prop_url}")
                    print(json.dumps(prop_data, ensure_ascii=False, indent=2, default=str))
                    
                    property_name = prop_data.get("Description", prop_data.get("Code", ""))
                    print(f"\n✓ Название свойства: {property_name}")
                    print(f"✓ Значение: {value_description}")
                    print(f"✓ Результат: {property_name}: {value_description}")
                    property_found = True
                    break
            except Exception as e:
                print(f"  ✗ {coll_name}: {str(e)[:100]}")
        
        if not property_found:
            print("\nПробуем получить свойство через навигацию значения...")
            try:
                owner_nav_url = f"{val_url}/Owner"
                owner_response = await client.get(owner_nav_url)
                if owner_response.status_code == 200:
                    owner_data = owner_response.json()
                    print(f"\n✓ Найден способ получения свойства через навигацию: {owner_nav_url}")
                    print(json.dumps(owner_data, ensure_ascii=False, indent=2, default=str))
                    
                    property_name = owner_data.get("Description", owner_data.get("Code", ""))
                    print(f"\n✓ Название свойства: {property_name}")
                    print(f"✓ Значение: {value_description}")
                    print(f"✓ Результат: {property_name}: {value_description}")
            except Exception as e:
                print(f"  ✗ Ошибка: {str(e)[:100]}")
        
        # 4. Получаем все характеристики товара
        print("\n" + "=" * 100)
        print("ПОЛУЧЕНИЕ ВСЕХ ХАРАКТЕРИСТИК ТОВАРА")
        print("=" * 100)
        
        # Получаем все значения для маппинга
        values_url = f"{API_URL.rstrip('/')}/Catalog_ЗначенияСвойствОбъектов"
        values_response = await client.get(values_url, params={"$top": 500})
        values_response.raise_for_status()
        values_data = values_response.json()
        all_values = values_data.get("value", [])
        
        values_map = {}
        properties_map = {}
        
        for val in all_values:
            val_key = val.get("Ref_Key")
            val_desc = val.get("Description", "")
            owner_key = val.get("Owner_Key")
            
            if val_key and val_desc:
                values_map[val_key] = val_desc
            
            # Пробуем получить свойство через Owner
            if owner_key and owner_key not in properties_map:
                for coll_name in properties_collections:
                    try:
                        prop_url = f"{API_URL.rstrip('/')}/{coll_name}(guid'{owner_key}')"
                        prop_response = await client.get(prop_url)
                        if prop_response.status_code == 200:
                            prop_data = prop_response.json()
                            prop_desc = prop_data.get("Description", prop_data.get("Code", ""))
                            if prop_desc:
                                properties_map[owner_key] = prop_desc
                                break
                    except:
                        pass
        
        print(f"\nЗагружено значений: {len(values_map)}")
        print(f"Загружено свойств: {len(properties_map)}")
        
        # Получаем все характеристики товара
        characteristics_list = []
        for rek in dop_rekv:
            prop_key = rek.get("Свойство_Key")
            val_key = rek.get("Значение")
            
            # Получаем название свойства
            prop_name = properties_map.get(prop_key)
            if not prop_name:
                # Пробуем получить напрямую
                for coll_name in properties_collections:
                    try:
                        prop_url = f"{API_URL.rstrip('/')}/{coll_name}(guid'{prop_key}')"
                        prop_response = await client.get(prop_url)
                        if prop_response.status_code == 200:
                            prop_data = prop_response.json()
                            prop_name = prop_data.get("Description", prop_data.get("Code", ""))
                            if prop_name:
                                properties_map[prop_key] = prop_name
                                break
                    except:
                        pass
            
            # Получаем значение
            val_name = values_map.get(val_key, "")
            if not val_name:
                try:
                    val_url = f"{API_URL.rstrip('/')}/Catalog_ЗначенияСвойствОбъектов(guid'{val_key}')"
                    val_response = await client.get(val_url)
                    if val_response.status_code == 200:
                        val_data = val_response.json()
                        val_name = val_data.get("Description", "")
                        if val_name:
                            values_map[val_key] = val_name
                except:
                    pass
            
            if prop_name and val_name:
                char_display = f"{prop_name}: {val_name}"
                characteristics_list.append({
                    "property": prop_name,
                    "value": val_name,
                    "display": char_display
                })
                print(f"  {char_display}")
        
        # Сохраняем результат
        result = {
            "product": {
                "Ref_Key": char_item.get("Ref_Key"),
                "Description": char_item.get("Description"),
                "Артикул": char_item.get("Артикул"),
            },
            "characteristics": characteristics_list,
        }
        
        with open("characteristics_final.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"\n✓ Результат сохранен в: characteristics_final.json")


if __name__ == "__main__":
    asyncio.run(get_property_by_owner())
