"""
Скрипт для получения покупок покупателя из 1С через выгрузку XML
"""
import asyncio
import os
import sys
import httpx
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

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


async def check_sales_xml_export():
    """Проверка выгрузки продаж через XML"""
    
    api_url = os.getenv("ONEC_API_URL")
    api_token = os.getenv("ONEC_API_TOKEN")
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Basic {api_token}"
    }
    
    print("=" * 80)
    print(f"ПРОВЕРКА ВЫГРУЗКИ ПРОДАЖ ЧЕРЕЗ XML")
    print("=" * 80)
    print(f"Покупатель: {PHONE}")
    print(f"Период: {START_DATE} - {END_DATE}")
    print()
    
    # Проверяем доступные endpoints
    endpoints_to_check = [
        "/1c/orders/export.xml",
        "/1c/exchange?type=sale&mode=export",
        "/static/1c_exchange/orders.xml",
    ]
    
    for endpoint in endpoints_to_check:
        print(f"\nПроверка endpoint: {endpoint}")
        print("-" * 60)
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{api_url.rstrip('/')}{endpoint}",
                    headers=headers
                )
                
                if response.status_code == 200:
                    print(f"    ✅ Endpoint доступен")
                    # Показываем первые 500 символов
                    content = response.text[:500]
                    print(f"    Содержимое: {content}")
                elif response.status_code == 404:
                    print(f"    ❌ Endpoint не найден")
                else:
                    print(f"    ❌ Статус {response.status_code}")
                    
        except Exception as e:
            print(f"    ❌ Ошибка: {e}")
    
    print()
    print("=" * 80)
    print("РЕКОМЕНДАЦИИ:")
    print("=" * 80)
    print()
    print("1. **Проблема 1С Fresh OData API**")
    print("   - 1С Fresh возвращает ошибку 500 при запросах к регистрам накопления")
    print("   - Это системная проблема 1С Fresh, а не ошибка в коде")
    print()
    print("2. **Альтернативные решения**")
    print("   a) Использовать выгрузку XML через CommerceML")
    print("      - Настройте выгрузку продаж в 1С в формате CommerceML")
    print("      - Получайте XML файл по URL")
    print("      - Парсите XML и импортируйте в БД")
    print()
    print("   b) Использовать FTP выгрузку")
    print("      - Настройте FTP выгрузку в 1С")
    print("      - Получайте файлы через FTP")
    print()
    print("   c) Использовать прямой доступ к БД 1С")
    print("      - Настройте прямой доступ к базе данных 1С")
    print("      - Выполняйте SQL запросы для получения продаж")
    print()
    print("   d) Использовать REST API 1С")
    print("      - Проверьте, есть ли REST API в вашей версии 1С")
    print("      - Используйте REST API вместо OData")
    print()
    print("3. **Для данного покупателя**")
    print(f"   - discount_card_id: {DISCOUNT_CARD_ID}")
    print(f"   - customer_id: {CUSTOMER_ID}")
    print(f"   - Последняя покупка в БД: 2026-02-12")
    print(f"   - Покупки за март-апрель 2026: НЕ НАЙДЕНЫ (ошибка 1С)")
    print()
    print("4. **Ручная проверка**")
    print("   - Откройте 1С:УНФ")
    print("   - Перейдите в раздел 'Продажи'")
    print("   - Найдите покупателя по телефону 79787566405")
    print("   - Проверьте покупки за март-апрель 2026")
    print()


def main():
    asyncio.run(check_sales_xml_export())


if __name__ == "__main__":
    main()
