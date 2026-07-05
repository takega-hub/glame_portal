"""
Скрипт для проверки расхождения сумм между 1С и БД
"""
import asyncio
import os
import sys
import httpx
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.connection import AsyncSessionLocal
from app.models.user import User
from app.models.purchase_history import PurchaseHistory
from sqlalchemy import select


async def check_amounts(phone: str):
    """Проверка сумм между 1С и БД"""
    
    async with AsyncSessionLocal() as db:
        # 1. Находим покупателя по телефону
        stmt = select(User).where(User.phone == phone, User.is_customer == True)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f'❌ Покупатель с телефоном {phone} не найден')
            return
        
        print("=" * 80)
        print(f"ПРОВЕРКА СУММ: {phone}")
        print("=" * 80)
        print()
        print(f"Покупатель: {user.full_name}")
        print()
        
        # 2. Получаем данные из БД
        print("Данные из БД:")
        print("-" * 60)
        print(f"  total_spent: {user.total_spent} коп ({user.total_spent / 100:.2f} руб)")
        print(f"  total_purchases: {user.total_purchases}")
        print(f"  last_purchase_date: {user.last_purchase_date}")
        print()
        
        # 3. Получаем все покупки из БД
        purchases_stmt = select(PurchaseHistory).where(PurchaseHistory.user_id == user.id)
        purchases_result = await db.execute(purchases_stmt)
        purchases = purchases_result.scalars().all()
        
        total_spent_db = sum(p.total_amount for p in purchases)
        total_quantity_db = sum(p.quantity for p in purchases)
        
        print(f"Расчёт из PurchaseHistory:")
        print(f"  Сумма: {total_spent_db} коп ({total_spent_db / 100:.2f} руб)")
        print(f"  Количество покупок: {len(purchases)}")
        print(f"  Количество товаров: {total_quantity_db}")
        print()
        
        # 4. Получаем данные из 1С
        print("Получение данных из 1С...")
        
        api_url = os.getenv("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata")
        api_token = os.getenv("ONEC_API_TOKEN", "your_1c_api_token_here")
        
        headers = {
            "Accept": "application/json",
            "Authorization": f"Basic {api_token}"
        }
        
        url = f"{api_url.rstrip('/')}/AccumulationRegister_Продажи"
        
        all_purchases = []
        batch_size = 100
        skip = 0
        
        while True:
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
                            break
                        
                        # Парсим RecordSet
                        for record in records:
                            record_set = record.get("RecordSet", [])
                            if not isinstance(record_set, list):
                                continue
                            
                            for movement in record_set:
                                kontragent_key = movement.get("Контрагент_Key", "")
                                
                                if kontragent_key == user.customer_id_1c or kontragent_key == "00000000-0000-0000-0000-000000000000":
                                    period = movement.get("Period", "")
                                    if period:
                                        all_purchases.append({
                                            "period": period,
                                            "document": movement.get("Документ"),
                                            "product": movement.get("Номенклатура_Key"),
                                            "amount": movement.get("Сумма", 0),
                                            "quantity": movement.get("Количество", 0),
                                        })
                        
                        skip += batch_size
                        
                        if len(all_purchases) >= 10000:
                            break
                        
                        if len(records) < batch_size:
                            break
                    
                    else:
                        break
                        
            except Exception as e:
                break
        
        # Дедупликация
        unique_purchases = {}
        for purchase in all_purchases:
            key = (purchase.get("document") or "", purchase.get("product") or "", purchase.get("period")[:10])
            if key not in unique_purchases:
                unique_purchases[key] = purchase
            else:
                if purchase.get("amount", 0) > unique_purchases[key].get("amount", 0):
                    unique_purchases[key] = purchase
        
        all_purchases = list(unique_purchases.values())
        
        total_spent_1c = sum(p.get("amount", 0) for p in all_purchases)
        total_quantity_1c = sum(p.get("quantity", 0) for p in all_purchases)
        
        print(f"Данные из 1С:")
        print(f"  Сумма: {total_spent_1c:.2f} руб")
        print(f"  Количество покупок: {len(all_purchases)}")
        print(f"  Количество товаров: {total_quantity_1c}")
        print()
        
        # 5. Сравнение
        print("=" * 80)
        print("СРАВНЕНИЕ:")
        print("=" * 80)
        print()
        print(f"{'Показатель':<30} {'1С':<20} {'БД':<20} {'Разница':<20}")
        print("-" * 90)
        print(f"{'Сумма (руб)':<30} {total_spent_1c:<20.2f} {total_spent_db / 100:<20.2f} {abs(total_spent_1c - total_spent_db / 100):<20.2f}")
        print(f"{'Количество покупок':<30} {len(all_purchases):<20} {len(purchases):<20} {abs(len(all_purchases) - len(purchases)):<20}")
        print(f"{'Количество товаров':<30} {total_quantity_1c:<20} {total_quantity_db:<20} {abs(total_quantity_1c - total_quantity_db):<20}")
        print()
        
        # 6. Проверка по периодам
        print("=" * 80)
        print("РАЗБИВКА ПО ПЕРИОДАМ:")
        print("=" * 80)
        print()
        
        periods = [
            ("2025-11-08", "Ввод начальных остатков 1 от 08.11.2025"),
            ("2025-11-12", "Отчет о розничных продажах 17 от 12.11.2025"),
            ("2025-11-15", "Отчет о розничных продажах 23 от 15.11.2025"),
            ("2026-01-16", "Отчет о розничных продажах 51 от 16.01.2026"),
            ("2026-02-12", "Отчет о розничных продажах 132 от 12.02.2026"),
            ("2026-03-10", "Отчет о розничных продажах 203 от 10.03.2026"),
            ("2026-04-30", "Отчет о розничных продажах 312 от 30.04.2026"),
        ]
        
        print(f"{'Период':<30} {'1С (руб)':<15} {'БД (руб)':<15} {'Разница (руб)':<15}")
        print("-" * 90)
        
        for period_date, period_name in periods:
            # Сумма из 1С
            amount_1c = sum(
                p.get("amount", 0) for p in all_purchases
                if p.get("period", "").startswith(period_date)
            )
            
            # Сумма из БД
            start_dt = datetime.strptime(period_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end_dt = start_dt + timedelta(days=1)
            
            purchases_in_period = [
                p for p in purchases
                if start_dt <= p.purchase_date < end_dt
            ]
            amount_db = sum(p.total_amount for p in purchases_in_period) / 100
            
            diff = abs(amount_1c - amount_db)
            
            print(f"{period_name:<30} {amount_1c:<15.2f} {amount_db:<15.2f} {diff:<15.2f}")
        
        print()
        print("=" * 80)
        print("АНАЛИЗ:")
        print("=" * 80)
        print()
        
        if abs(total_spent_1c - total_spent_db / 100) > 1000:  # Более 1000 руб разница
            print("⚠️  ОБНАРУЖЕНО ЗНАЧИТЕЛЬНОЕ РАСХОЖДЕНИЕ СУММ!")
            print()
            print("Возможные причины:")
            print("1. В БД есть покупки, которых нет в 1С")
            print("2. В 1С есть покупки, которые не попали в БД")
            print("3. Разница в конвертации сумм (рубли/копейки)")
            print("4. Дубликаты покупок в БД")
            print()
            
            # Проверяем дубликаты
            duplicate_keys = {}
            for p in purchases:
                key = (p.document_id_1c or "", p.product_id_1c or "", p.purchase_date.date().isoformat())
                if key not in duplicate_keys:
                    duplicate_keys[key] = []
                duplicate_keys[key].append(p)
            
            duplicates = {k: v for k, v in duplicate_keys.items() if len(v) > 1}
            if duplicates:
                print(f"⚠️  Найдено {len(duplicates)} дубликатов покупок в БД")
                for key, dup_list in list(duplicates.items())[:5]:
                    print(f"  - {key}: {len(dup_list)} записей")
        else:
            print("✅ Суммы совпадают (разница менее 1000 руб)")


def main():
    phone = "79787566405"
    
    print()
    asyncio.run(check_amounts(phone))


if __name__ == "__main__":
    main()
