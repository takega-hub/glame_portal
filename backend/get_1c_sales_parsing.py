"""
Скрипт для получения покупок покупателя из 1С через AccumulationRegister_Продажи
Ищет покупателя по телефону, затем получает покупки по его customer_id_1c
"""
import asyncio
import os
import sys
import httpx
from datetime import datetime, timezone
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.connection import AsyncSessionLocal
from app.models.user import User

# Настройка переменных окружения
os.environ.setdefault("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata")
os.environ.setdefault("ONEC_API_TOKEN", "your_1c_api_token_here")

# Данные покупателя (только PHONE - скрипт сам найдёт customer_id_1c)
PHONE = "79787566405"

# Период для проверки
START_DATE = "2025-03-01"
END_DATE = "2026-04-30"


async def fetch_sales_from_register():
    """Получение продаж через AccumulationRegister_Продажи с парсингом RecordSet"""
    
    async with AsyncSessionLocal() as db:
        # 1. Находим покупателя по телефону
        stmt = select(User).where(User.phone == PHONE, User.is_customer == True)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f'❌ Покупатель с телефоном {PHONE} не найден')
            return
        
        print("=" * 80)
        print(f"ПОЛУЧЕНИЕ ПОКУПОК ИЗ 1С (AccumulationRegister_Продажи)")
        print("=" * 80)
        print(f"Покупатель: {user.full_name}")
        print(f"1C Customer ID: {user.customer_id_1c}")
        print(f"Период: {START_DATE} - {END_DATE}")
        print()
        
        api_url = os.getenv("ONEC_API_URL")
        api_token = os.getenv("ONEC_API_TOKEN")
        
        headers = {
            "Accept": "application/json",
            "Authorization": f"Basic {api_token}"
        }
        
        url = f"{api_url.rstrip('/')}/AccumulationRegister_Продажи"
        
        all_purchases = []
        batch_size = 100
        skip = 0
        
        while True:
            print(f"Запрос батча (skip={skip})...")
            
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    params = {
                        "$top": batch_size,
                        "$skip": skip,
                    }
                    response = await client.get(url, headers=headers, params=params)
                    
                    if response.status_code == 200:
                        data = response.json()
                        records = data.get("value", [])
                        
                        if not records:
                            print(f"  ✅ Батч пуст, завершаем")
                            break
                        
                        # Парсим RecordSet
                        for record in records:
                            record_set = record.get("RecordSet", [])
                            if not isinstance(record_set, list):
                                continue
                            
                            for movement in record_set:
                                kontragent_key = movement.get("Контрагент_Key", "")
                                
                                # Фильтруем ТОЛЬКО по контрагенту этого покупателя
                                if kontragent_key == user.customer_id_1c:
                                    period = movement.get("Period", "")
                                    if period:
                                        try:
                                            if isinstance(period, str):
                                                dt = datetime.fromisoformat(period.replace("Z", "+00:00").split(".")[0])
                                                date_str = dt.strftime("%Y-%m-%d")
                                                
                                                all_purchases.append({
                                                    "period": period,
                                                    "date": date_str,
                                                    "document": movement.get("Документ"),
                                                    "product": movement.get("Номенклатура_Key"),
                                                    "amount": movement.get("Сумма", 0),
                                                    "quantity": movement.get("Количество", 0),
                                                    "store": movement.get("Склад_Key"),
                                                })
                                        except Exception as e:
                                            pass
                        
                        skip += batch_size
                        
                        if len(all_purchases) >= 10000:
                            print(f"  Достигнут лимит 10000 покупок, завершаем")
                            break
                        
                        if len(records) < batch_size:
                            break
                    
                    else:
                        print(f"  ❌ Статус {response.status_code}")
                        break
                        
            except Exception as e:
                print(f"  ❌ Ошибка: {e}")
                break
        
        # Дедупликация
        unique_purchases = {}
        for purchase in all_purchases:
            key = (purchase.get("document") or "", purchase.get("product") or "", purchase.get("date"))
            if key not in unique_purchases:
                unique_purchases[key] = purchase
        
        all_purchases = list(unique_purchases.values())
        total_spent = sum(p.get("amount", 0) for p in all_purchases)
        
        print(f"Получено {len(all_purchases)} покупок из 1С")
        print(f"Сумма: {total_spent:.2f} руб")
        print()
        
        if not all_purchases:
            print("❌ Покупок не найдено")
            return
        
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
        
        sorted_purchases = sorted(all_purchases, key=lambda r: parse_period(r.get("period")), reverse=True)
        
        print("Последние 20 покупок:")
        print("-" * 80)
        for i, p in enumerate(sorted_purchases[:20], 1):
            period = p.get("period", "N/A")
            doc = p.get("document") or "N/A"
            product = p.get("product") or "N/A"
            amount = p.get("amount", 0)
            store = p.get("store") or "N/A"
            
            print(f"{i:2}. {period} | {str(doc)[:20]:<20} | {str(product)[:20]:<20} | {amount:<10} | {str(store)[:15]:<15}")
        
        print()
        print("=" * 80)
        print("ИТОГО:")
        print("=" * 80)
        print(f"Всего покупок: {len(all_purchases)}")
        print(f"Общая сумма: {total_spent:.2f} руб")


def main():
    print()
    asyncio.run(fetch_sales_from_register())


if __name__ == "__main__":
    main()
