"""
Скрипт для загрузки базы знаний о бренде из JSON файла
"""
import json
import sys
import os
from pathlib import Path

# Добавляем путь к app в sys.path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.vector_service import vector_service


def load_knowledge_from_file(file_path: str):
    """Загрузка базы знаний из JSON файла"""
    print(f"Загрузка базы знаний из файла: {file_path}")
    
    # Проверяем существование файла
    if not os.path.exists(file_path):
        print(f"Ошибка: Файл {file_path} не найден")
        return False
    
    # Читаем файл
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Ошибка парсинга JSON: {e}")
        return False
    except Exception as e:
        print(f"Ошибка при чтении файла: {e}")
        return False
    
    # Поддерживаем разные форматы
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("items", data.get("knowledge", []))
    else:
        print("Ошибка: Неверный формат файла. Ожидается массив или объект с полем 'items'")
        return False
    
    if not items:
        print("Предупреждение: Файл не содержит элементов для загрузки")
        return False
    
    print(f"Найдено {len(items)} элементов для загрузки")
    
    # Загружаем каждый элемент
    loaded_count = 0
    errors = []
    
    for idx, item_data in enumerate(items, 1):
        try:
            # Поддерживаем как объекты, так и простые строки
            if isinstance(item_data, str):
                text = item_data
                category = None
                source = None
                metadata = None
            else:
                text = item_data.get("text") or item_data.get("content")
                if not text:
                    print(f"Пропуск элемента {idx}: отсутствует поле 'text' или 'content'")
                    continue
                category = item_data.get("category")
                source = item_data.get("source")
                metadata = item_data.get("metadata")
            
            doc_id = vector_service.add_brand_knowledge(
                text=text,
                category=category,
                source=source,
                metadata=metadata
            )
            loaded_count += 1
            print(f"[{idx}/{len(items)}] Загружено: {text[:50]}... (ID: {doc_id})")
            
        except Exception as e:
            error_msg = f"Ошибка при загрузке элемента {idx}: {str(e)}"
            errors.append(error_msg)
            print(f"❌ {error_msg}")
    
    # Итоги
    print("\n" + "="*50)
    print(f"Загрузка завершена!")
    print(f"Успешно загружено: {loaded_count} из {len(items)}")
    if errors:
        print(f"Ошибок: {len(errors)}")
        for error in errors:
            print(f"  - {error}")
    print("="*50)
    
    return loaded_count > 0


def main():
    """Главная функция"""
    if len(sys.argv) < 2:
        print("Использование: python load_brand_knowledge.py <путь_к_json_файлу>")
        print("\nПример:")
        print("  python load_brand_knowledge.py brand_knowledge.json")
        print("\nФормат JSON файла:")
        print("  Вариант 1 (массив объектов):")
        print('  [{"text": "...", "category": "...", "source": "..."}, ...]')
        print("\n  Вариант 2 (объект с полем items):")
        print('  {"items": [{"text": "...", ...}, ...]}')
        print("\n  Вариант 3 (массив строк):")
        print('  ["Текст знания 1", "Текст знания 2", ...]')
        sys.exit(1)
    
    file_path = sys.argv[1]
    success = load_knowledge_from_file(file_path)
    
    if success:
        print("\n✅ База знаний успешно загружена!")
        sys.exit(0)
    else:
        print("\n❌ Ошибка при загрузке базы знаний")
        sys.exit(1)


if __name__ == "__main__":
    main()
