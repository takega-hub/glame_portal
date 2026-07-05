"""
Скрипт для синхронизации ТОЛЬКО покупок данного покупателя
Фильтрует по контрагенту (customer_id_1c)
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
from app.models.product import Product
from sqlalchemy import select


async def sync_customer_correct(phone: str):
    """Синхронизация ТОЛЬКО покупок данного покупателя по контрагенту"""
    
    async with AsyncSessionLocal() as db:
        # 1. Находим покупателя по телефону
        stmt = select(User).where(User.phone == phone, User.is_customer == True)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f'❌ Покупатель с телефоном {phone} не найден')
            return
        
        print("=" * 80)
        print(f"СИНХРОНИЗАЦИЯ ПОКУПОК ПОКУПАТЕЛЯ: {phone}")
        print("=" * 80)
        print()
        print(f"Покупатель: {user.full_name}")
        print(f"1C Customer ID: {user.customer_id_1c}")
        print(f"1C Discount Card ID: {user.discount_card_id_1c}")
        print()
        
        # 2. Получаем покупки из 1С по контрагенту
        print("Получение покупок из 1С по контрагенту...")
        
        api_url = os.getenv("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata")
        api_token = os.getenv("ONEC_API_TOKEN", "your_1c_api_token_here")
        
        headers = {
            "Accept": "application/json",
            "Authorization": f"Basic {api_token}"
        }
        
        # Используем регистр продаж
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
                                
                                # Фильтруем ТОЛЬКО по контрагенту этого покупателя
                                if kontragent_key == user.customer_id_1c:
                                    period = movement.get("Period", "")
                                    if period:
                                        try:
                                            if isinstance(period, str):
                                                dt = datetime.fromisoformat(period.replace("Z", "+00:00").split(".")[0])
                                                date_str = dt.strftime("%Y-%m-%d")
                                                
                                                all_purchases_1c.append({
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
                        
                        if len(all_purchases_1c) >= 10000:
                            break
                        
                        if len(records) < batch_size:
                            break
                    
                    else:
                        print(f"  Статус {response.status_code}")
                        break
                        
            except Exception as e:
                print(f"  Ошибка: {e}")
                break
        
        # Дедупликация
        unique_purchases_1c = {}
        for purchase in all_purchases_1c:
            key = (purchase.get("document") or "", purchase.get("product") or "", purchase.get("date"))
            if key not in unique_purchases_1c:
                unique_purchases_1c[key] = purchase
        
        all_purchases_1c = list(unique_purchases_1c.values())
        total_spent_1c = sum(p.get("amount", 0) for p in all_purchases_1c)
        
        print(f"Всего покупок в 1С (по контрагенту): {len(all_purchases_1c)}")
        print(f"Сумма в 1С: {total_spent_1c:.2f} руб")
        print()
        
        # 3. Удаляем все покупки из БД
        print("Удаление всех покупок из БД...")
        
        purchases_stmt = select(PurchaseHistory).where(PurchaseHistory.user_id == user.id)
        purchases_result = await db.execute(purchases_stmt)
        purchases = purchases_result.scalars().all()
        
        print(f"Удалено {len(purchases)} покупок из БД")
        
        for p in purchases:
            await db.delete(p)
        
        await db.commit()
        print("✅ Все покупки удалены")
        print()
        
        # 4. Импортируем покупки из 1С
        print("Импорт покупок из 1С...")
        
        imported_count = 0
        for i, purchase in enumerate(all_purchases_1c, 1):
            try:
                document_id_1c = purchase.get("document")
                product_id_1c = purchase.get("product")
                period = purchase.get("period")
                amount = purchase.get("amount", 0)
                quantity = purchase.get("quantity", 0)
                store_id_1c = purchase.get("store")
                
                # Парсим дату
                purchase_date = datetime.fromisoformat(period.replace("Z", "+00:00"))
                if purchase_date.tzinfo is None:
                    purchase_date = purchase_date.replace(tzinfo=timezone.utc)
                else:
                    purchase_date = purchase_date.astimezone(timezone.utc)
                
                # Конвертируем сумму в копейки
                amount_kopecks = int(round(amount * 100)) if amount else 0
                price_kopecks = amount_kopecks // quantity if quantity > 0 else 0
                
                # Ищем товар в БД
                product_id = None
                if product_id_1c:
                    product_stmt = select(Product).where(Product.external_id == product_id_1c)
                    product_result = await db.execute(product_stmt)
                    product = product_result.scalars().first()
                    if product:
                        product_id = product.id
                
                # Создаем запись покупки
                new_purchase = PurchaseHistory(
                    user_id=user.id,
                    document_id_1c=document_id_1c,
                    store_id_1c=store_id_1c,
                    product_id=product_id,
                    product_id_1c=product_id_1c,
                    purchase_date=purchase_date,
                    quantity=quantity,
                    price=price_kopecks,
                    total_amount=amount_kopecks,
                )
                
                db.add(new_purchase)
                
                if i % 100 == 0:
                    print(f"  Импорт {i}/{len(all_purchases_1c)}...")
                
                imported_count += 1
                
            except Exception as e:
                print(f"  Ошибка при импорте покупки {i}: {e}")
        
        await db.commit()
        print(f"✅ Импортировано {imported_count} покупок")
        print()
        
        # 5. Пересчёт метрик
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
        print("✅ СИНХРОНИЗАЦИЯ ЗАВЕРШЕНА")
        print("=" * 80)
        print()
        print(f"В 1С: {total_spent_1c:.2f} руб")
        print(f"В БД: {total_spent:.2f} руб")
        print(f"Разница: {abs(total_spent_1c - total_spent):.2f} руб")


def main():
    phone = "79787891424"
    
    print()
    asyncio.run(sync_customer_correct(phone))


if __name__ == "__main__":
    main()
