"""
Скрипт для получения покупок покупателя из 1С OData API
Использует прямые HTTP запросы для обхода проблемы с AUTOORDER
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

# Период для проверки
START_DATE = "2026-03-01"
END_DATE = "2026-04-30"


async def fetch_sales_from_1c():
    """Получение продаж из 1С через OData API"""
    
    api_url = os.getenv("ONEC_API_URL")
    api_token = os.getenv("ONEC_API_TOKEN")
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Basic {api_token}"
    }
    
    print("=" * 80)
    print(f"ПОЛУЧЕНИЕ ПОКУПОК ИЗ 1С")
    print("=" * 80)
    print(f"Период: {START_DATE} - {END_DATE}")
    print()
    
    # Регистры накопления для проверки
    registries = [
        ("AccumulationRegister_ПродажиПоДисконтнымКартам_RecordType", "Продажи по дисконтным картам"),
        ("AccumulationRegister_Продажи_RecordType", "Продажи (общие)"),
    ]
    
    all_purchases = []
    
    for registry, registry_name in registries:
        print(f"\nПроверка регистра: {registry_name}")
        print("-" * 60)
        
        # Формируем URL с пагинацией
        base_url = f"{api_url.rstrip('/')}/{registry}"
        
        # Пробуем разные подходы
        approaches = [
            ("Без сортировки, small batch", {"$top": 100}),
            ("Без сортировки, medium batch", {"$top": 500}),
            ("Без сортировки, large batch", {"$top": 1000}),
        ]
        
        for approach_name, params in approaches:
            print(f"\n  Подход: {approach_name}")
            
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    # Добавляем фильтр по дисконтной карте
                    params["$filter"] = f"ДисконтнаяКарта_Key eq guid'{DISCOUNT_CARD_ID}'"
                    
                    # Получаем данные
                    response = await client.get(base_url, headers=headers, params=params)
                    
                    if response.status_code == 200:
                        data = response.json()
                        records = data.get("value", [])
                        
                        if records:
                            print(f"    ✅ Получено {len(records)} записей")
                            
                            # Фильтруем по дате
                            filtered = []
                            for r in records:
                                period = r.get("Period", "")
                                if period:
                                    try:
                                        # Парсим дату
                                        if isinstance(period, str):
                                            dt = datetime.fromisoformat(period.replace("Z", "+00:00").split(".")[0])
                                            date_str = dt.strftime("%Y-%m-%d")
                                            if START_DATE <= date_str <= END_DATE:
                                                filtered.append(r)
                                    except Exception as e:
                                        pass
                            
                            if filtered:
                                print(f"    📅 Найдено {len(filtered)} покупок за {START_DATE}-{END_DATE}")
                                all_purchases.extend(filtered)
                        else:
                            print(f"    ❌ Записей не найдено")
                    elif response.status_code == 500:
                        error_text = response.text[:200]
                        print(f"    ❌ Ошибка 500: {error_text}")
                    else:
                        print(f"    ❌ Статус {response.status_code}: {response.text[:100]}")
                        
            except Exception as e:
                print(f"    ❌ Ошибка: {e}")
    
    # Вывод результатов
    print("\n" + "=" * 80)
    print("РЕЗУЛЬТАТЫ:")
    print("=" * 80)
    
    if all_purchases:
        print(f"\n✅ Найдено {len(all_purchases)} покупок за март-апрель 2026:")
        print()
        
        # Сортируем по дате
        def parse_period(p):
            if not p:
                return datetime.min.replace(tzinfo=timezone.utc)
            try:
                if isinstance(p, str):
                    return datetime.fromisoformat(p.replace("Z", "+00:00").split(".")[0])
                return p
            except:
                return datetime.min.replace(tzinfo=timezone.utc)
        
        sorted_purchases = sorted(all_purchases, key=lambda r: parse_period(r.get("Period")), reverse=True)
        
        for i, p in enumerate(sorted_purchases[:20], 1):
            period = p.get("Period", "N/A")
            doc = p.get("Документ") or p.get("Recorder")
            product = p.get("Номенклатура_Key")
            amount = p.get("Сумма", 0)
            store = p.get("Склад_Key")
            recorder_type = p.get("Recorder_Type", "")
            
            print(f"{i:2}. {period} | {doc[:20] if doc else 'N/A':20} | {amount:10} | {store[:15] if store else 'N/A':15} | {recorder_type[:30] if recorder_type else 'N/A':30}")
        
        # Суммируем
        total_amount = sum(p.get("Сумма", 0) for p in all_purchases)
        print()
        print(f"Всего покупок: {len(all_purchases)}")
        print(f"Общая сумма: {total_amount:.2f} руб")
        
    else:
        print("\n❌ Покупок за указанный период не найдено")
        print()
        print("Возможные причины:")
        print("1. Покупки были сделаны до марта 2026 или после апреля 2026")
        print("2. Покупки привязаны к другому покупателю/карте")
        print("3. 1С Fresh не возвращает данные через OData API")
        print()
        print("Рекомендации:")
        print("1. Проверьте данные в 1С через интерфейс")
        print("2. Используйте выгрузку продаж через XML/CommerceML")
        print("3. Проверьте, что discount_card_id правильный")


def main():
    asyncio.run(fetch_sales_from_1c())


if __name__ == "__main__":
    main()
