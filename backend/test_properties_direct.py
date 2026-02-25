"""
Прямая проверка коллекций свойств
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


async def test_properties_direct():
    """Прямая проверка коллекций свойств"""
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    
    print("=" * 100)
    print("ПРЯМАЯ ПРОВЕРКА КОЛЛЕКЦИЙ СВОЙСТВ")
    print("=" * 100)
    print()
    
    async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
        # Получаем пример характеристики с ДополнительныеРеквизиты
        char_catalog_url = f"{API_URL.rstrip('/')}/Catalog_ХарактеристикиНоменклатуры"
        response = await client.get(char_catalog_url, params={"$top": 5})
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
        
        first_rek = dop_rekv[0]
        property_key = first_rek.get("Свойство_Key")
        value_key = first_rek.get("Значение")
        
        print(f"Пример реквизита:")
        print(f"  Свойство_Key: {property_key}")
        print(f"  Значение: {value_key}")
        print()
        
        # Пробуем разные коллекции свойств
        properties_collections = [
            "Catalog_СвойстваНоменклатуры",
            "Catalog_Свойства",
            "Catalog_СвойстваОбъектов",
            "Catalog_СвойстваОбъектовНоменклатуры",
            "InformationRegister_Свойства",
        ]
        
        print("=" * 100)
        print("ПОИСК КОЛЛЕКЦИИ СВОЙСТВ")
        print("=" * 100)
        
        properties_map = {}
        for coll_name in properties_collections:
            try:
                coll_url = f"{API_URL.rstrip('/')}/{coll_name}"
                coll_response = await client.get(coll_url, params={"$top": 100})
                if coll_response.status_code == 200:
                    coll_data = coll_response.json()
                    props = coll_data.get("value", [])
                    if props:
                        print(f"\n✓ Найдена коллекция: {coll_name} ({len(props)} записей)")
                        
                        # Ищем нужное свойство
                        target_prop = next((p for p in props if p.get("Ref_Key") == property_key), None)
                        if target_prop:
                            print(f"\n✓ Найдено нужное свойство:")
                            print(json.dumps(target_prop, ensure_ascii=False, indent=2, default=str))
                        
                        # Сохраняем все свойства
                        for prop in props:
                            prop_key = prop.get("Ref_Key")
                            if prop_key:
                                properties_map[prop_key] = prop.get("Description", prop.get("Code", ""))
                        
                        print(f"\nПримеры свойств из {coll_name}:")
                        for key, name in list(properties_map.items())[:10]:
                            print(f"  {key[:36]}... → {name}")
                        
                        break
            except Exception as e:
                print(f"  ✗ {coll_name}: {str(e)[:100]}")
        
        # Пробуем получить свойство напрямую через навигацию
        print("\n" + "=" * 100)
        print("ПОЛУЧЕНИЕ СВОЙСТВА ЧЕРЕЗ НАВИГАЦИЮ")
        print("=" * 100)
        
        # Пробуем разные варианты навигации
        nav_urls = [
            f"{API_URL.rstrip('/')}/Catalog_ХарактеристикиНоменклатуры(guid'{char_item.get('Ref_Key')}')/ДополнительныеРеквизиты",
        ]
        
        for nav_url in nav_urls:
            try:
                nav_response = await client.get(nav_url)
                if nav_response.status_code == 200:
                    nav_data = nav_response.json()
                    print(f"\n✓ Навигация работает: {nav_url}")
                    print(json.dumps(nav_data, ensure_ascii=False, indent=2, default=str)[:500])
            except Exception as e:
                print(f"  ✗ {nav_url}: {str(e)[:100]}")
        
        # Пробуем получить свойство по ключу через разные коллекции
        print("\n" + "=" * 100)
        print("ПОЛУЧЕНИЕ СВОЙСТВА ПО КЛЮЧУ")
        print("=" * 100)
        
        for coll_name in properties_collections:
            try:
                prop_url = f"{API_URL.rstrip('/')}/{coll_name}(guid'{property_key}')"
                prop_response = await client.get(prop_url)
                if prop_response.status_code == 200:
                    prop_data = prop_response.json()
                    print(f"\n✓ Найден способ получения свойства: {prop_url}")
                    print(json.dumps(prop_data, ensure_ascii=False, indent=2, default=str))
                    break
            except:
                pass
        
        # Получаем значения
        print("\n" + "=" * 100)
        print("ПОЛУЧЕНИЕ ЗНАЧЕНИЯ")
        print("=" * 100)
        
        values_collections = [
            "Catalog_ЗначенияСвойствОбъектов",
            "Catalog_ЗначенияСвойств",
        ]
        
        for coll_name in values_collections:
            try:
                val_url = f"{API_URL.rstrip('/')}/{coll_name}(guid'{value_key}')"
                val_response = await client.get(val_url)
                if val_response.status_code == 200:
                    val_data = val_response.json()
                    print(f"\n✓ Найден способ получения значения: {val_url}")
                    print(json.dumps(val_data, ensure_ascii=False, indent=2, default=str))
                    break
            except:
                pass


if __name__ == "__main__":
    asyncio.run(test_properties_direct())
