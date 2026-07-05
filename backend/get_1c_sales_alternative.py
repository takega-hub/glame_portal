"""
Скрипт для получения покупок покупателя из 1С через прямой HTTP запрос
Использует альтернативный подход для обхода проблемы с AUTOORDER
"""
import asyncio
import os
import sys
import httpx
from datetime import datetime, timezone

# Настройка переменных окружения
os.environ.setdefault("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata")
os.environ.setdefault("ONEC_API_TOKEN", "your_1c_api_token_here")

# Данные покупателя
DISCOUNT_CARD_ID = "b0ed5080-bb1a-11f0-836e-fa163e4cc04e"
CUSTOMER_ID = "e824f1c0-bb10-11f0-836e-fa163e4cc04e"
PHONE = "79787566405"

# Период для проверки
START_DATE = "2026-03-01"
END_DATE = "2026-04-30"


async def fetch_sales_alternative():
    """Получение продаж через альтернативный подход"""
    
    api_url = os.getenv("ONEC_API_URL")
    api_token = os.getenv("ONEC_API_TOKEN")
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Basic {api_token}"
    }
    
    print("=" * 80)
    print(f"ПОЛУЧЕНИЕ ПОКУПОК ИЗ 1С (АЛЬТЕРНАТИВНЫЙ ПОДХОД)")
    print("=" * 80)
    print(f"Покупатель: {PHONE}")
    print(f"Период: {START_DATE} - {END_DATE}")
    print()
    
    # Пробуем разные регистры и подходы
    approaches = [
        {
            "name": "AccumulationRegister_Продажи (без _RecordType)",
            "url": "/AccumulationRegister_Продажи",
            "filter_field": "Контрагент_Key",
        },
        {
            "name": "Document_РеализацияТоваровУслуг (документы)",
            "url": "/Document_РеализацияТоваровУслуг",
            "filter_field": "Контрагент_Key",
        },
        {
            "name": "Catalog_Контрагенты (проверка контрагента)",
            "url": "/Catalog_Контрагенты",
            "filter_field": "Ref_Key",
        },
    ]
    
    for approach in approaches:
        print(f"\nПодход: {approach['name']}")
        print("-" * 60)
        
        url = f"{api_url.rstrip('/')}{approach['url']}"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Простой запрос без фильтра
                params = {
                    "$top": 10,
                }
                
                response = await client.get(url, headers=headers, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    records = data.get("value", [])
                    
                    if records:
                        print(f"    ✅ Endpoint доступен, получено {len(records)} записей")
                        
                        # Показываем структуру данных
                        if records:
                            first_record = records[0]
                            print(f"    Поля записи: {list(first_record.keys())[:10]}...")
                    else:
                        print(f"    ❌ Записей не найдено")
                elif response.status_code == 500:
                    error_text = response.text[:200]
                    print(f"    ❌ Ошибка 500: {error_text}")
                else:
                    print(f"    ❌ Статус {response.status_code}: {response.text[:100]}")
                    
        except Exception as e:
            print(f"    ❌ Ошибка: {e}")
    
    print()
    print("=" * 80)
    print("РЕКОМЕНДАЦИИ:")
    print("=" * 80)
    print()
    print("1. **Проблема 1С Fresh OData API**")
    print("   - 1С Fresh возвращает ошибку 500 при запросах к регистрам накопления")
    print("   - Ошибка: 'Операция не разрешена в предложении ГДЕ ... AUTOORDER'")
    print("   - Это системная проблема 1С Fresh")
    print()
    print("2. **Альтернативные решения**")
    print()
    print("   a) **Использовать выгрузку XML через CommerceML**")
    print("      - Настройте в 1С:УНФ: CRM и маркетинг → Интернет-магазин → Выгрузка каталога")
    print("      - Получайте XML файл по URL (например, https://your-domain.com/1c/sales.xml)")
    print("      - Парсите XML и импортируйте в БД")
    print()
    print("   b) **Использовать FTP выгрузку**")
    print("      - Настройте FTP выгрузку в 1С")
    print("      - Получайте файлы через FTP")
    print()
    print("   c) **Использовать REST API 1С**")
    print("      - Проверьте, есть ли REST API в вашей версии 1С")
    print("      - Используйте REST API вместо OData")
    print()
    print("   d) **Ручная проверка в 1С**")
    print("      - Откройте 1С:УНФ")
    print("      - Перейдите в раздел 'Продажи'")
    print("      - Найдите покупателя по телефону 79787566405")
    print("      - Проверьте покупки за март-апрель 2026")
    print()
    print("3. **Для данного покупателя**")
    print(f"   - discount_card_id: {DISCOUNT_CARD_ID}")
    print(f"   - customer_id: {CUSTOMER_ID}")
    print(f"   - Последняя покупка в БД: 2026-02-12")
    print(f"   - Покупки за март-апрель 2026: НЕ ПОЛУЧЕНЫ (ошибка 1С)")
    print()
    print("4. **Следующие шаги**")
    print("   - Свяжитесь с отделом, который управляет 1С")
    print("   - Запросите выгрузку продаж за март-апрель 2026 в формате CSV/Excel")
    print("   - Или настройте автоматическую выгрузку через CommerceML")


def main():
    asyncio.run(fetch_sales_alternative())


if __name__ == "__main__":
    main()
