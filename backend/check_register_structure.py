"""
Скрипт для проверки структуры данных из 1С AccumulationRegister_Продажи
"""
import asyncio
import os
import sys
import httpx
from datetime import datetime, timezone

# Настройка переменных окружения
os.environ.setdefault("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata")
os.environ.setdefault("ONEC_API_TOKEN", "your_1c_api_token_here")


async def check_register_structure():
    """Проверка структуры данных регистра"""
    
    api_url = os.getenv("ONEC_API_URL")
    api_token = os.getenv("ONEC_API_TOKEN")
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Basic {api_token}"
    }
    
    print("=" * 80)
    print(f"ПРОВЕРКА СТРУКТУРЫ ДАННЫХ 1С")
    print("=" * 80)
    print()
    
    url = f"{api_url.rstrip('/')}/AccumulationRegister_Продажи"
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Получаем первые 10 записей
            params = {"$top": 10}
            response = await client.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get("value", [])
                
                if records:
                    print(f"✅ Получено {len(records)} записей")
                    print()
                    
                    # Показываем полную структуру первой записи
                    print("Структура первой записи:")
                    print("-" * 60)
                    first_record = records[0]
                    
                    for key, value in first_record.items():
                        if isinstance(value, str) and len(value) > 50:
                            value = value[:50] + "..."
                        print(f"  {key}: {value}")
                    
                    print()
                    print("=" * 80)
                    print("ВСЕ ДОСТУПНЫЕ ПОЛЯ:")
                    print("=" * 80)
                    
                    # Собираем все уникальные поля
                    all_fields = set()
                    for record in records:
                        all_fields.update(record.keys())
                    
                    for field in sorted(all_fields):
                        print(f"  - {field}")
                    
                    print()
                    print("=" * 80)
                    print("ПРИМЕРЫ ДАННЫХ:")
                    print("=" * 80)
                    
                    for i, record in enumerate(records[:5], 1):
                        print(f"\nЗапись {i}:")
                        for key, value in record.items():
                            if isinstance(value, str) and len(value) > 50:
                                value = value[:50] + "..."
                            print(f"  {key}: {value}")
                    
                else:
                    print("❌ Записей не найдено")
            else:
                print(f"❌ Статус {response.status_code}: {response.text[:200]}")
                    
    except Exception as e:
        print(f"❌ Ошибка: {e}")


def main():
    asyncio.run(check_register_structure())


if __name__ == "__main__":
    main()
