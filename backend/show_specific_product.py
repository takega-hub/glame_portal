"""
Показать конкретный товар из 1С по коду
"""
import asyncio
import sys
import codecs
import os
import json
import httpx

if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

API_URL = os.getenv("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata")
API_TOKEN = os.getenv("ONEC_API_TOKEN", "b2RhdGEudXNlcjpvcGV4b2JvZQ==")


async def find_product_by_code(product_code: str):
    """Найти товар по коду"""
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    
    url = f"{API_URL.rstrip('/')}/Catalog_Номенклатура"
    # Получаем все товары и ищем вручную (фильтр может не работать с кириллицей)
    params = {
        "$top": 1000
    }
    
    try:
        async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
            print(f"Поиск товара с кодом: {product_code}")
            print(f"URL: {url}")
            print()
            
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            all_items = data.get("value", [])
            
            # Ищем товар по коду
            found_item = None
            for item in all_items:
                if item.get("Code") == product_code:
                    found_item = item
                    break
            
            if not found_item:
                print(f"✗ Товар с кодом '{product_code}' не найден в первых 1000 записях")
                print("\nИщем товары с похожим кодом...")
                similar = [item for item in all_items if product_code.lower() in str(item.get("Code", "")).lower()]
                if similar:
                    print(f"Найдено похожих товаров: {len(similar)}")
                    for item in similar[:5]:
                        print(f"  - Code: {item.get('Code')}, Description: {item.get('Description')}")
                
                # Ищем товары с заполненным артикулом для примера
                print("\n" + "=" * 80)
                print("ПРИМЕРЫ ТОВАРОВ С ЗАПОЛНЕННЫМ АРТИКУЛОМ:")
                print("=" * 80)
                items_with_article = [item for item in all_items if item.get("Артикул")]
                if items_with_article:
                    print(f"\nНайдено товаров с артикулом: {len(items_with_article)}\n")
                    for item in items_with_article[:3]:
                        print(f"Code: {item.get('Code')}")
                        print(f"Description: {item.get('Description')}")
                        print(f"Артикул: {item.get('Артикул')}")
                        print()
                else:
                    print("\nТоваров с заполненным полем 'Артикул' не найдено")
                    print("Возможно, артикул хранится в 'ДополнительныеРеквизиты'")
                    # Показываем товары с заполненными ДополнительныеРеквизиты
                    items_with_dop = [item for item in all_items if item.get("ДополнительныеРеквизиты")]
                    if items_with_dop:
                        print(f"\nНайдено товаров с ДополнительныеРеквизиты: {len(items_with_dop)}")
                        for item in items_with_dop[:2]:
                            print(f"\nCode: {item.get('Code')}, Description: {item.get('Description')}")
                            print("ДополнительныеРеквизиты:")
                            dop = item.get("ДополнительныеРеквизиты")
                            if isinstance(dop, list):
                                for rek in dop:
                                    print(f"  {rek}")
                            else:
                                print(f"  {dop}")
                return
            
            item = found_item
            
            print("=" * 80)
            print("НАЙДЕННЫЙ ТОВАР")
            print("=" * 80)
            print()
            
            # Основная информация
            print("ОСНОВНАЯ ИНФОРМАЦИЯ:")
            print("-" * 80)
            print(f"Code (внутренний код 1С): {item.get('Code')}")
            print(f"Ref_Key (UUID в 1С): {item.get('Ref_Key')}")
            print(f"Description (название): {item.get('Description')}")
            print(f"НаименованиеПолное: {item.get('НаименованиеПолное')}")
            print()
            
            # Поиск артикула
            print("ПОИСК АРТИКУЛА:")
            print("-" * 80)
            
            # Прямое поле Артикул
            article = item.get("Артикул")
            if article:
                print(f"✓ Артикул (прямое поле): {article}")
            else:
                print("✗ Артикул (прямое поле): NULL")
            
            # Дополнительные реквизиты
            dop_rekv = item.get("ДополнительныеРеквизиты")
            if dop_rekv:
                print(f"\nДополнительныеРеквизиты (тип: {type(dop_rekv).__name__}):")
                if isinstance(dop_rekv, list):
                    print(f"  Это массив из {len(dop_rekv)} элементов")
                    for idx, rek in enumerate(dop_rekv):
                        print(f"  Элемент {idx}:")
                        if isinstance(rek, dict):
                            for k, v in rek.items():
                                print(f"    {k}: {v}")
                        else:
                            print(f"    {rek}")
                elif isinstance(dop_rekv, dict):
                    print("  Это объект:")
                    for k, v in dop_rekv.items():
                        print(f"    {k}: {v}")
                else:
                    print(f"  Значение: {dop_rekv}")
            else:
                print("✗ ДополнительныеРеквизиты: NULL или пусто")
            
            # Все поля, которые могут быть артикулом
            print("\nВСЕ ПОЛЯ, СОДЕРЖАЩИЕ 'КОД' ИЛИ 'АРТИКУЛ':")
            print("-" * 80)
            for key, value in item.items():
                key_lower = key.lower()
                if any(word in key_lower for word in ["артикул", "код", "code", "article"]):
                    if value is not None and value != "":
                        print(f"  {key}: {value}")
            
            # Показываем все заполненные поля
            print("\n" + "=" * 80)
            print("ВСЕ ЗАПОЛНЕННЫЕ ПОЛЯ (не NULL):")
            print("=" * 80)
            
            filled_fields = {k: v for k, v in item.items() if v is not None and v != ""}
            print(f"\nВсего заполненных полей: {len(filled_fields)} из {len(item)}\n")
            
            for key in sorted(filled_fields.keys()):
                value = filled_fields[key]
                value_type = type(value).__name__
                
                if isinstance(value, dict):
                    if "Description" in value:
                        value_str = f"{{объект: {value.get('Description')}}}"
                    else:
                        value_str = f"{{объект с {len(value)} полями}}"
                elif isinstance(value, list):
                    value_str = f"[массив из {len(value)} элементов]"
                elif isinstance(value, str):
                    if len(value) > 100:
                        value_str = value[:97] + "..."
                    else:
                        value_str = value
                else:
                    value_str = str(value)
                
                print(f"{key:<50} {value_type:<15} {value_str}")
            
            # Сохраняем в JSON
            output_file = f"product_{product_code}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(item, f, ensure_ascii=False, indent=2, default=str)
            print(f"\n✓ Полные данные сохранены в: {output_file}")
            
    except Exception as e:
        print(f"\n✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Ищем товар, который упомянул пользователь
    product_code = "НФ-00002362"
    if len(sys.argv) > 1:
        product_code = sys.argv[1]
    
    asyncio.run(find_product_by_code(product_code))
