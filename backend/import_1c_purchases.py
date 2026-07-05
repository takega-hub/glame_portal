"""
Скрипт для импорта покупок из 1С в БД для покупателя 79787566405
Использует прямой HTTP запрос к AccumulationRegister_Продажи
"""
import asyncio
import os
import sys
import httpx
from datetime import datetime, timedelta, timezone
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.connection import AsyncSessionLocal
from app.models.user import User
from app.models.purchase_history import PurchaseHistory
from app.models.product import Product
from sqlalchemy import select


async def import_purchases(phone: str, start_date: str = "2026-03-01", end_date: str = "2026-04-30"):
    """Импорт покупок из 1С в БД"""
    
    async with AsyncSessionLocal() as db:
        # 1. Находим покупателя по телефону
        stmt = select(User).where(User.phone == phone, User.is_customer == True)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f'❌ Покупатель с телефоном {phone} не найден')
            return
        
        print("=" * 80)
        print(f"ИМПОРТ ПОКУПОК ИЗ 1С В БД: {phone}")
        print("=" * 80)
        print()
        print(f"Покупатель: {user.full_name}")
        print(f"1C Customer ID: {user.customer_id_1c}")
        print(f"1C Discount Card ID: {user.discount_card_id_1c}")
        print(f"Период: {start_date} - {end_date}")
        print()
        
        # 2. Получаем покупки из 1С напрямую
        print("Получение покупок из 1С...")
        
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
            print(f"  Запрос батча (skip={skip})...")
            
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
                                
                                if kontragent_key == user.customer_id_1c or kontragent_key == "00000000-0000-0000-0000-000000000000":
                                    period = movement.get("Period", "")
                                    if period:
                                        try:
                                            if isinstance(period, str):
                                                dt = datetime.fromisoformat(period.replace("Z", "+00:00").split(".")[0])
                                                date_str = dt.strftime("%Y-%m-%d")
                                                
                                                if start_date <= date_str <= end_date:
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
        
        print(f"Получено {len(all_purchases)} покупок из 1С")
        print()
        
        if not all_purchases:
            print("❌ Покупок не найдено")
            return
        
        # 3. Дедупликация покупок (по document_id_1c + product_id_1c + date)
        print("Дедупликация покупок...")
        unique_purchases = {}
        for purchase in all_purchases:
            key = (purchase.get("document") or "", purchase.get("product") or "", purchase.get("date"))
            if key not in unique_purchases:
                unique_purchases[key] = purchase
            else:
                # Берём запись с большей суммой
                if purchase.get("amount", 0) > unique_purchases[key].get("amount", 0):
                    unique_purchases[key] = purchase
        
        all_purchases = list(unique_purchases.values())
        print(f"После дедупликации: {len(all_purchases)} покупок")
        print()
        
        # 4. Получаем существующие покупки из БД
        print("Получение существующих покупок из БД...")
        existing_purchases = await db.execute(
            select(PurchaseHistory).where(
                PurchaseHistory.user_id == user.id,
                PurchaseHistory.purchase_date >= datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc),
                PurchaseHistory.purchase_date <= datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            )
        )
        existing_purchases = existing_purchases.scalars().all()
        
        existing_keys = set()
        for p in existing_purchases:
            key = (p.document_id_1c or "", p.product_id_1c or "", p.purchase_date.date().isoformat())
            existing_keys.add(key)
        
        print(f"Существует {len(existing_purchases)} покупок в БД за этот период")
        print()
        
        # 5. Фильтруем новые покупки
        new_purchases = []
        updated_purchases = []
        skipped_purchases = []
        
        for purchase_data in all_purchases:
            document_id_1c = purchase_data.get("document")
            product_id_1c = purchase_data.get("product")
            date_str = purchase_data.get("date")
            
            key = (document_id_1c or "", product_id_1c or "", date_str)
            
            if key in existing_keys:
                # Проверяем, нужно ли обновить
                existing = next((p for p in existing_purchases if p.document_id_1c == document_id_1c and p.product_id_1c == product_id_1c), None)
                if existing:
                    amount = purchase_data.get("amount", 0)
                    quantity = purchase_data.get("quantity", 0)
                    
                    if existing.total_amount != amount or existing.quantity != quantity:
                        updated_purchases.append(purchase_data)
                    else:
                        skipped_purchases.append(purchase_data)
            else:
                new_purchases.append(purchase_data)
        
        print(f"Новых покупок: {len(new_purchases)}")
        print(f"Требуется обновить: {len(updated_purchases)}")
        print(f"Пропущено (уже есть): {len(skipped_purchases)}")
        print()
        
        if not new_purchases and not updated_purchases:
            print("✅ Все покупки уже есть в БД")
            return
        
        # 6. Импорт новых покупок
        if new_purchases:
            print("Импорт новых покупок...")
            
            for i, purchase in enumerate(new_purchases, 1):
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
                        print(f"  Импорт {i}/{len(new_purchases)}...")
                
                except Exception as e:
                    print(f"  Ошибка при импорте покупки {i}: {e}")
            
            await db.commit()
            print(f"✅ Импортировано {len(new_purchases)} новых покупок")
        
        # 7. Обновление существующих покупок
        if updated_purchases:
            print("Обновление существующих покупок...")
            
            for i, purchase in enumerate(updated_purchases, 1):
                try:
                    document_id_1c = purchase.get("document")
                    product_id_1c = purchase.get("product")
                    amount = purchase.get("amount", 0)
                    quantity = purchase.get("quantity", 0)
                    
                    # Конвертируем сумму в копейки
                    amount_kopecks = int(round(amount * 100)) if amount else 0
                    price_kopecks = amount_kopecks // quantity if quantity > 0 else 0
                    
                    # Находим существующую запись
                    existing = await db.execute(
                        select(PurchaseHistory).where(
                            PurchaseHistory.user_id == user.id,
                            PurchaseHistory.document_id_1c == document_id_1c,
                            PurchaseHistory.product_id_1c == product_id_1c
                        )
                    )
                    existing_purchase = existing.scalars().first()
                    
                    if existing_purchase:
                        existing_purchase.total_amount = amount_kopecks
                        existing_purchase.quantity = quantity
                        existing_purchase.price = price_kopecks
                    
                    if i % 100 == 0:
                        print(f"  Обновление {i}/{len(updated_purchases)}...")
                
                except Exception as e:
                    print(f"  Ошибка при обновлении покупки {i}: {e}")
            
            await db.commit()
            print(f"✅ Обновлено {len(updated_purchases)} покупок")
        
        # 8. Пересчёт метрик
        print()
        print("Пересчёт метрик покупателя...")
        
        # Пересчитываем метрики
        purchases_stmt = select(PurchaseHistory).where(PurchaseHistory.user_id == user.id)
        purchases_result = await db.execute(purchases_stmt)
        purchases = purchases_result.scalars().all()
        
        total_purchases = len(purchases)
        total_spent = sum(p.total_amount for p in purchases)
        average_check = total_spent / total_purchases if total_purchases > 0 else 0
        
        last_purchase_date = max((p.purchase_date for p in purchases), default=None)
        
        user.total_purchases = total_purchases
        user.total_spent = total_spent
        user.average_check = int(average_check) if average_check else None
        user.last_purchase_date = last_purchase_date
        
        await db.commit()
        
        print(f"  Всего покупок: {total_purchases}")
        print(f"  Общая сумма: {total_spent / 100:.2f} руб")
        print(f"  Последняя покупка: {last_purchase_date}")
        
        print()
        print("=" * 80)
        print("✅ ИМПОРТ ЗАВЕРШЕН")
        print("=" * 80)


def main():
    phone = "79787566405"
    start_date = "2026-03-01"
    end_date = "2026-04-30"
    
    print()
    asyncio.run(import_purchases(phone, start_date, end_date))


if __name__ == "__main__":
    main()
