"""
Скрипт для удаления лишних покупок из БД
Оставляет только покупки из 1С
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


async def remove_extra_purchases(phone: str):
    """Удаление лишних покупок из БД"""
    
    async with AsyncSessionLocal() as db:
        # 1. Находим покупателя по телефону
        stmt = select(User).where(User.phone == phone, User.is_customer == True)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f'❌ Покупатель с телефоном {phone} не найден')
            return
        
        print("=" * 80)
        print(f"УДАЛЕНИЕ ЛИШНИХ ПОКУПОК ИЗ БД: {phone}")
        print("=" * 80)
        print()
        print(f"Покупатель: {user.full_name}")
        print()
        
        # 2. Получаем все покупки из БД
        print("Получение покупок из БД...")
        purchases_stmt = select(PurchaseHistory).where(PurchaseHistory.user_id == user.id)
        purchases_result = await db.execute(purchases_stmt)
        purchases = purchases_result.scalars().all()
        
        total_spent_db = sum(p.total_amount for p in purchases) / 100
        
        print(f"Всего покупок в БД: {len(purchases)}")
        print(f"Сумма в БД: {total_spent_db:.2f} руб")
        print()
        
        # 3. Получаем все покупки из 1С
        print("Получение покупок из 1С...")
        
        api_url = os.getenv("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata")
        api_token = os.getenv("ONEC_API_TOKEN", "your_1c_api_token_here")
        
        headers = {
            "Accept": "application/json",
            "Authorization": f"Basic {api_token}"
        }
        
        url = f"{api_url.rstrip('/')}/AccumulationRegister_Продажи"
        
        all_purchases_1c = []
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
                                        all_purchases_1c.append({
                                            "period": period,
                                            "document": movement.get("Документ"),
                                            "product": movement.get("Номенклатура_Key"),
                                            "amount": movement.get("Сумма", 0),
                                        })
                        
                        skip += batch_size
                        
                        if len(all_purchases_1c) >= 20000:
                            break
                        
                        if len(records) < batch_size:
                            break
                    
                    else:
                        break
                        
            except Exception as e:
                break
        
        # Дедупликация
        unique_purchases_1c = {}
        for purchase in all_purchases_1c:
            key = (purchase.get("document") or "", purchase.get("product") or "", purchase.get("period")[:10])
            if key not in unique_purchases_1c:
                unique_purchases_1c[key] = purchase
        
        all_purchases_1c = list(unique_purchases_1c.values())
        total_spent_1c = sum(p.get("amount", 0) for p in all_purchases_1c)
        
        print(f"Всего покупок в 1С: {len(all_purchases_1c)}")
        print(f"Сумма в 1С: {total_spent_1c:.2f} руб")
        print()
        
        # 4. Находим покупки в БД, которых нет в 1С
        print("Поиск покупок в БД, которых нет в 1С...")
        print("-" * 60)
        
        purchases_to_delete = []
        for p in purchases:
            key = (p.document_id_1c or "", p.product_id_1c or "", p.purchase_date.date().isoformat())
            if key not in unique_purchases_1c:
                purchases_to_delete.append(p)
        
        print(f"Найдено {len(purchases_to_delete)} покупок для удаления")
        print()
        
        if not purchases_to_delete:
            print("✅ Все покупки из БД есть в 1С")
            return
        
        # 5. Показываем, что будет удалено
        print("Будет удалено:")
        print()
        print(f"{'Дата':<25} {'Документ':<30} {'Товар':<30} {'Сумма':<15}")
        print("-" * 100)
        
        total_to_delete = 0
        for p in purchases_to_delete:
            date_str = p.purchase_date.strftime("%Y-%m-%d %H:%M:%S") if p.purchase_date else "N/A"
            doc = p.document_id_1c or "N/A"
            product = p.product_id_1c or "N/A"
            amount = p.total_amount / 100
            
            print(f"{date_str:<25} {doc[:28]:<30} {product[:28]:<30} {amount:<15.2f}")
            total_to_delete += amount
        
        print("-" * 100)
        print(f"{'ИТОГО':<70} {total_to_delete:<15.2f}")
        print()
        
        # 6. Удаляем покупки
        print("Удаление покупок...")
        
        deleted_count = 0
        for p in purchases_to_delete:
            try:
                await db.delete(p)
                deleted_count += 1
                
                if deleted_count % 100 == 0:
                    print(f"  Удалено {deleted_count}/{len(purchases_to_delete)}...")
            except Exception as e:
                print(f"  Ошибка при удалении покупки {p.id}: {e}")
        
        await db.commit()
        print(f"✅ Удалено {deleted_count} покупок")
        print()
        
        # 7. Пересчёт метрик
        print("Пересчёт метрик покупателя...")
        
        # Пересчитываем метрики
        purchases_stmt = select(PurchaseHistory).where(PurchaseHistory.user_id == user.id)
        purchases_result = await db.execute(purchases_stmt)
        purchases = purchases_result.scalars().all()
        
        total_purchases = len(purchases)
        total_spent = sum(p.total_amount for p in purchases) / 100
        average_check = total_spent / total_purchases if total_purchases > 0 else 0
        
        last_purchase_date = max((p.purchase_date for p in purchases), default=None)
        
        user.total_purchases = total_purchases
        user.total_spent = int(total_spent * 100)
        user.average_check = int(average_check) if average_check else None
        user.last_purchase_date = last_purchase_date
        
        await db.commit()
        
        print(f"  Всего покупок: {total_purchases}")
        print(f"  Общая сумма: {total_spent:.2f} руб")
        print(f"  Последняя покупка: {last_purchase_date}")
        
        print()
        print("=" * 80)
        print("✅ УДАЛЕНИЕ ЗАВЕРШЕНО")
        print("=" * 80)
        print()
        print(f"До удаления: {total_spent_db:.2f} руб")
        print(f"После удаления: {total_spent:.2f} руб")
        print(f"Разница: {total_to_delete:.2f} руб")
        print(f"В 1С: {total_spent_1c:.2f} руб")


def main():
    phone = "79787566405"
    
    print()
    asyncio.run(remove_extra_purchases(phone))


if __name__ == "__main__":
    main()
