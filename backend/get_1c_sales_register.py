"""
Скрипт для получения покупок покупателя из 1С через AccumulationRegister_Продажи
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
CUSTOMER_ID = "e824f1c0-bb10-11f0-836e-fa163e4cc04e"
PHONE = "79787566405"

# Период для проверки
START_DATE = "2026-03-01"
END_DATE = "2026-04-30"


async def fetch_sales_from_register():
    """Получение продаж через AccumulationRegister_Продажи"""
    
    api_url = os.getenv("ONEC_API_URL")
    api_token = os.getenv("ONEC_API_TOKEN")
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Basic {api_token}"
    }
    
    print("=" * 80)
    print(f"ПОЛУЧЕНИЕ ПОКУПОК ИЗ 1С (AccumulationRegister_Продажи)")
    print("=" * 80)
    print(f"Покупатель: {PHONE}")
    print(f"Customer ID: {CUSTOMER_ID}")
    print(f"Период: {START_DATE} - {END_DATE}")
    print()
    
    url = f"{api_url.rstrip('/')}/AccumulationRegister_Продажи"
    
    # Пробуем разные подходы
    approaches = [
        {
            "name": "Без фильтра (первые 100 записей)",
            "params": {"$top": 100},
        },
        {
            "name": "С фильтром по Контрагент_Key",
            "params": {
                "$filter": f"Контрагент_Key eq guid'{CUSTOMER_ID}'",
                "$top": 100,
            },
        },
        {
            "name": "С фильтром по Контрагент_Key и пагинацией",
            "params": {
                "$filter": f"Контрагент_Key eq guid'{CUSTOMER_ID}'",
                "$top": 50,
                "$skip": 0,
            },
        },
    ]
    
    all_purchases = []
    
    for approach in approaches:
        print(f"\nПодход: {approach['name']}")
        print("-" * 60)
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(url, headers=headers, params=approach["params"])
                
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
                            print(f"    📅 Покупок за указанный период не найдено")
                            
                            # Показываем последние записи
                            if records:
                                print(f"    Последние записи:")
                                for r in records[:5]:
                                    period = r.get("Period", "N/A")
                                    doc = r.get("Документ") or r.get("Recorder")
                                    print(f"      - {period} | {doc}")
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
            quantity = p.get("Количество", 0)
            
            print(f"{i:2}. {period} | {doc[:20] if doc else 'N/A':20} | {amount:10} | {quantity} шт | {store[:15] if store else 'N/A':15}")
        
        # Суммируем
        total_amount = sum(p.get("Сумма", 0) for p in all_purchases)
        total_quantity = sum(p.get("Количество", 0) for p in all_purchases)
        
        print()
        print(f"Всего покупок: {len(all_purchases)}")
        print(f"Всего товаров: {total_quantity} шт")
        print(f"Общая сумма: {total_amount:.2f} руб")
        
    else:
        print("\n❌ Покупок за указанный период не найдено")
        print()
        print("Возможные причины:")
        print("1. Покупки были сделаны до марта 2026 или после апреля 2026")
        print("2. Покупки привязаны к другому покупателю/карте")
        print("3. В регистре нет данных за указанный период")
        print()
        print("Рекомендации:")
        print("1. Проверьте данные в 1С через интерфейс")
        print("2. Расширьте период поиска")
        print("3. Проверьте, что customer_id правильный")


def main():
    asyncio.run(fetch_sales_from_register())


if __name__ == "__main__":
    main()
