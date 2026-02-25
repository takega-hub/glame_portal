"""
Скрипт для показа полей товаров из 1С Catalog_Номенклатура
Показывает реальную структуру данных без подключения к БД
"""
import asyncio
import sys
import codecs
import os
import json
import httpx
from typing import Dict, Any

if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

# Устанавливаем переменные окружения
if not os.getenv("ONEC_API_URL"):
    os.environ["ONEC_API_URL"] = "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata"
if not os.getenv("ONEC_API_TOKEN"):
    os.environ["ONEC_API_TOKEN"] = "b2RhdGEudXNlcjpvcGV4b2JvZQ=="

API_URL = os.getenv("ONEC_API_URL")
API_TOKEN = os.getenv("ONEC_API_TOKEN")


async def fetch_product_sample() -> None:
    """Получение образца товара из 1С"""
    print("=" * 80)
    print("АНАЛИЗ ПОЛЕЙ ТОВАРОВ ИЗ 1С (Catalog_Номенклатура)")
    print("=" * 80)
    print()
    
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    
    url = f"{API_URL.rstrip('/')}/Catalog_Номенклатура"
    params = {"$top": 3}  # Получаем 3 товара для примера
    
    try:
        async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
            print(f"Запрос к: {url}")
            print(f"Параметры: {params}")
            print()
            
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            items = data.get("value", [])
            
            if not items:
                print("✗ Нет товаров в каталоге")
                return
            
            print(f"✓ Получено товаров: {len(items)}\n")
            print("=" * 80)
            
            # Показываем первый товар детально
            first_item = items[0]
            print("\nПЕРВЫЙ ТОВАР (полная структура):")
            print("=" * 80)
            
            # Сортируем поля для удобства
            sorted_keys = sorted(first_item.keys())
            
            print(f"\nВсего полей: {len(sorted_keys)}\n")
            
            # Создаем таблицу с полями
            print(f"{'Поле':<40} {'Тип':<15} {'Значение (первые 60 символов)':<60}")
            print("-" * 120)
            
            for key in sorted_keys:
                value = first_item[key]
                value_type = type(value).__name__
                
                # Форматируем значение для отображения
                if value is None:
                    value_str = "NULL"
                elif isinstance(value, dict):
                    if "Description" in value or "description" in value:
                        value_str = f"{{объект: {value.get('Description') or value.get('description') or 'ссылка'}}}"
                    else:
                        value_str = f"{{объект с {len(value)} полями}}"
                elif isinstance(value, list):
                    value_str = f"[массив из {len(value)} элементов]"
                elif isinstance(value, str):
                    if len(value) > 60:
                        value_str = value[:57] + "..."
                    else:
                        value_str = value
                else:
                    value_str = str(value)
                    if len(value_str) > 60:
                        value_str = value_str[:57] + "..."
                
                print(f"{key:<40} {value_type:<15} {value_str:<60}")
            
            # Показываем все товары кратко
            print("\n" + "=" * 80)
            print("\nВСЕ ТОВАРЫ (краткая информация):")
            print("=" * 80)
            
            for idx, item in enumerate(items, 1):
                print(f"\n--- Товар {idx} ---")
                
                # Основные поля
                code = item.get("Code") or item.get("code") or "нет"
                description = item.get("Description") or item.get("description") or item.get("Наименование") or "нет"
                
                print(f"Code (внутренний код 1С): {code}")
                print(f"Description (название): {description}")
                
                # Ищем возможные поля артикула
                possible_article_fields = [
                    "Артикул", "артикул", "Article", "article",
                    "АртикулПроизводителя", "КодПроизводителя",
                    "ВнешнийКод", "ExternalCode", "external_code"
                ]
                
                print("\nВозможные поля артикула:")
                for field in possible_article_fields:
                    if field in item:
                        value = item[field]
                        if isinstance(value, dict):
                            value = value.get("Description") or value.get("description") or str(value)
                        print(f"  - {field}: {value}")
                
                # Показываем все ключи
                print(f"\nВсе поля ({len(item.keys())}): {', '.join(sorted(item.keys()))}")
            
            # Сохраняем в JSON
            output_file = "1c_products_sample.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2, default=str)
            print(f"\n✓ Полные данные сохранены в: {output_file}")
            
            # Анализ всех уникальных полей
            print("\n" + "=" * 80)
            print("\nАНАЛИЗ ВСЕХ УНИКАЛЬНЫХ ПОЛЕЙ:")
            print("=" * 80)
            
            all_keys = set()
            for item in items:
                all_keys.update(item.keys())
            
            print(f"\nВсего уникальных полей: {len(all_keys)}")
            print("\nСписок всех полей (по алфавиту):")
            for key in sorted(all_keys):
                print(f"  - {key}")
            
    except Exception as e:
        print(f"\n✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(fetch_product_sample())
