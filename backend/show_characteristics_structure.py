"""
Показать структуру характеристик номенклатуры из 1С
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


async def show_characteristics():
    """Показать структуру характеристик"""
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    
    try:
        async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
            print("=" * 100)
            print("СТРУКТУРА ХАРАКТЕРИСТИК НОМЕНКЛАТУРЫ ИЗ 1С")
            print("=" * 100)
            print()
            
            # 1. Получаем характеристики
            char_url = f"{API_URL.rstrip('/')}/Catalog_ХарактеристикиНоменклатуры"
            print("1. Загрузка характеристик...")
            char_response = await client.get(char_url, params={"$top": 10})
            char_response.raise_for_status()
            char_data = char_response.json()
            characteristics = char_data.get("value", [])
            
            if characteristics:
                print(f"   ✓ Получено характеристик: {len(characteristics)}\n")
                
                # Показываем первую характеристику
                first_char = characteristics[0]
                print("ПЕРВАЯ ХАРАКТЕРИСТИКА (полная структура):")
                print("-" * 100)
                for key in sorted(first_char.keys()):
                    value = first_char[key]
                    if isinstance(value, dict):
                        value_str = f"{{объект: {value.get('Description', 'ссылка')}}}"
                    elif isinstance(value, list):
                        value_str = f"[массив: {len(value)} элементов]"
                    else:
                        value_str = str(value)
                        if len(value_str) > 70:
                            value_str = value_str[:67] + "..."
                    print(f"  {key:<50} = {value_str}")
                
                # Получаем основную номенклатуру для этой характеристики
                owner_key = first_char.get("Owner")
                if owner_key:
                    print(f"\n2. Получение основной номенклатуры (Owner: {owner_key})...")
                    nom_url = f"{API_URL.rstrip('/')}/Catalog_Номенклатура(guid'{owner_key}')"
                    try:
                        nom_response = await client.get(nom_url)
                        nom_response.raise_for_status()
                        nom_data = nom_response.json()
                        print(f"   ✓ Основная номенклатура:")
                        print(f"     Code: {nom_data.get('Code')}")
                        print(f"     Артикул: {nom_data.get('Артикул')}")
                        print(f"     Description: {nom_data.get('Description')}")
                    except Exception as e:
                        print(f"   ✗ Ошибка получения номенклатуры: {e}")
                
                # Ищем характеристики с артикулами S/G
                print("\n3. Поиск характеристик с артикулами, содержащими S или G...")
                all_chars_response = await client.get(char_url, params={"$top": 500})
                all_chars_response.raise_for_status()
                all_chars_data = all_chars_response.json()
                all_chars = all_chars_data.get("value", [])
                
                chars_with_s_g = []
                for char in all_chars:
                    code = char.get("Code", "")
                    desc = char.get("Description", "")
                    if "S" in code or "G" in code or "S" in desc or "G" in desc:
                        chars_with_s_g.append(char)
                
                if chars_with_s_g:
                    print(f"   ✓ Найдено характеристик с S/G: {len(chars_with_s_g)}")
                    print("\n   Примеры характеристик:")
                    for char in chars_with_s_g[:5]:
                        print(f"   - Code: {char.get('Code')}, Description: {char.get('Description')}")
                        print(f"     Owner: {char.get('Owner')}")
                
                # Сохраняем пример
                output_file = "characteristics_sample.json"
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(characteristics[:5], f, ensure_ascii=False, indent=2, default=str)
                print(f"\n✓ Примеры характеристик сохранены в: {output_file}")
            
            # 2. Получаем товар и его характеристики
            print("\n" + "=" * 100)
            print("СВЯЗЬ ТОВАРА И ХАРАКТЕРИСТИК")
            print("=" * 100)
            print()
            
            # Находим товар с Parent_Key (это может быть характеристика)
            nom_url = f"{API_URL.rstrip('/')}/Catalog_Номенклатура"
            nom_response = await client.get(nom_url, params={"$top": 1000})
            nom_response.raise_for_status()
            nom_data = nom_response.json()
            nom_items = nom_data.get("value", [])
            
            # Ищем товары с Parent_Key (это характеристики, привязанные к основной карточке)
            items_with_parent = [item for item in nom_items if item.get("Parent_Key") and item.get("Parent_Key") != "00000000-0000-0000-0000-000000000000" and not item.get("IsFolder")]
            
            if items_with_parent:
                print(f"Найдено товаров с Parent_Key (возможно характеристики): {len(items_with_parent)}\n")
                
                # Группируем по Parent_Key
                by_parent = {}
                for item in items_with_parent[:20]:  # Первые 20 для примера
                    parent_key = item.get("Parent_Key")
                    if parent_key not in by_parent:
                        by_parent[parent_key] = []
                    by_parent[parent_key].append(item)
                
                print("Примеры групп товаров (основная карточка + характеристики):")
                print("-" * 100)
                
                for parent_key, children in list(by_parent.items())[:3]:
                    # Получаем основную карточку
                    try:
                        parent_url = f"{API_URL.rstrip('/')}/Catalog_Номенклатура(guid'{parent_key}')"
                        parent_response = await client.get(parent_url)
                        parent_response.raise_for_status()
                        parent_item = parent_response.json()
                        
                        print(f"\nОсновная карточка:")
                        print(f"  Code: {parent_item.get('Code')}")
                        print(f"  Артикул: {parent_item.get('Артикул')}")
                        print(f"  Description: {parent_item.get('Description')}")
                        print(f"\n  Характеристики ({len(children)} шт.):")
                        for child in children:
                            print(f"    - Code: {child.get('Code')}, Артикул: {child.get('Артикул')}, Description: {child.get('Description')}")
                    except:
                        print(f"  Parent_Key: {parent_key} (не удалось получить)")
                        for child in children:
                            print(f"    - Code: {child.get('Code')}, Артикул: {child.get('Артикул')}")
            
    except Exception as e:
        print(f"✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(show_characteristics())
