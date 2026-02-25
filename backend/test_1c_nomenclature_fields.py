"""
Скрипт для проверки доступных полей в Catalog_Номенклатура из 1С
Помогает определить, какие характеристики товаров доступны
"""
import asyncio
import sys
import codecs
import os
import json
from typing import List, Dict, Any

if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

# Устанавливаем переменные окружения
if not os.getenv("ONEC_API_URL"):
    os.environ["ONEC_API_URL"] = "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata"
if not os.getenv("ONEC_API_TOKEN"):
    os.environ["ONEC_API_TOKEN"] = "b2RhdGEudXNlcjpvcGV4b2JvZQ=="

from app.services.onec_products_service import OneCProductsService
from app.database.connection import AsyncSessionLocal


async def analyze_nomenclature_fields() -> None:
    """Анализ полей в Catalog_Номенклатура"""
    print("=== Анализ полей Catalog_Номенклатура ===\n")
    
    async with AsyncSessionLocal() as db:
        async with OneCProductsService(db) as service:
            try:
                # Получаем несколько записей для анализа
                print("Загрузка записей из Catalog_Номенклатура...")
                items = await service.fetch_nomenclature_page(top=5, skip=0)
                
                if not items:
                    print("  ✗ Нет записей в каталоге")
                    return
                
                print(f"  ✓ Получено {len(items)} записей\n")
                
                # Анализируем первую запись детально
                first_item = items[0]
                print("=== Структура первой записи ===")
                print(f"Всего полей: {len(first_item)}\n")
                
                # Группируем поля по категориям
                categories = {
                    "Идентификаторы": [],
                    "Основная информация": [],
                    "Характеристики": [],
                    "Цены и финансы": [],
                    "Изображения": [],
                    "Описания": [],
                    "Дополнительные поля": []
                }
                
                # Ключевые слова для категоризации
                id_keywords = ["key", "id", "uuid", "ref", "code", "артикул", "код"]
                main_keywords = ["name", "наименование", "description", "описание", "brand", "бренд", "category", "группа"]
                spec_keywords = ["характеристик", "specification", "свойств", "property", "реквизит", "attribute", "параметр"]
                price_keywords = ["price", "цена", "стоимость", "cost"]
                image_keywords = ["image", "picture", "фото", "изображение", "картинк"]
                desc_keywords = ["description", "описание", "comment", "комментарий"]
                
                for key, value in first_item.items():
                    key_lower = key.lower()
                    categorized = False
                    
                    if any(kw in key_lower for kw in id_keywords):
                        categories["Идентификаторы"].append((key, value))
                        categorized = True
                    elif any(kw in key_lower for kw in main_keywords):
                        categories["Основная информация"].append((key, value))
                        categorized = True
                    elif any(kw in key_lower for kw in spec_keywords):
                        categories["Характеристики"].append((key, value))
                        categorized = True
                    elif any(kw in key_lower for kw in price_keywords):
                        categories["Цены и финансы"].append((key, value))
                        categorized = True
                    elif any(kw in key_lower for kw in image_keywords):
                        categories["Изображения"].append((key, value))
                        categorized = True
                    elif any(kw in key_lower for kw in desc_keywords):
                        categories["Описания"].append((key, value))
                        categorized = True
                    
                    if not categorized:
                        categories["Дополнительные поля"].append((key, value))
                
                # Выводим результаты по категориям
                for category, fields in categories.items():
                    if fields:
                        print(f"\n{category}:")
                        for key, value in fields:
                            value_str = str(value)
                            if len(value_str) > 100:
                                value_str = value_str[:100] + "..."
                            value_type = type(value).__name__
                            if isinstance(value, dict):
                                value_str = f"{{объект с {len(value)} полями}}"
                            elif isinstance(value, list):
                                value_str = f"[массив из {len(value)} элементов]"
                            print(f"  - {key}: {value_type} = {value_str}")
                
                # Ищем вложенные объекты, которые могут содержать характеристики
                print("\n=== Поиск вложенных объектов с характеристиками ===")
                for key, value in first_item.items():
                    if isinstance(value, dict):
                        print(f"\n{key} (объект):")
                        for sub_key, sub_value in value.items():
                            sub_value_str = str(sub_value)
                            if len(sub_value_str) > 80:
                                sub_value_str = sub_value_str[:80] + "..."
                            print(f"  - {sub_key}: {type(sub_value).__name__} = {sub_value_str}")
                
                # Сохраняем полную структуру в JSON для анализа
                print("\n=== Сохранение полной структуры ===")
                output_file = "nomenclature_structure.json"
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(first_item, f, ensure_ascii=False, indent=2, default=str)
                print(f"  ✓ Сохранено в {output_file}")
                
                # Анализируем все записи на предмет уникальных полей
                print("\n=== Анализ всех полей во всех записях ===")
                all_keys = set()
                for item in items:
                    all_keys.update(item.keys())
                
                print(f"Уникальных полей найдено: {len(all_keys)}")
                print("Все поля:", ", ".join(sorted(all_keys)))
                
            except Exception as e:
                print(f"  ✗ Ошибка: {e}")
                import traceback
                traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(analyze_nomenclature_fields())
