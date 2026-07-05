"""
Скрипт для проверки покупок в БД, которых нет в 1С
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


async def check_extra_purchases(phone: str):
    """Проверка покупок в БД, которых нет в 1С"""
    
    async with AsyncSessionLocal() as db:
        # 1. Находим покупателя по телефону
        stmt = select(User).where(User.phone == phone, User.is_customer == True)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f'❌ Покупатель с телефоном {phone} не найден')
            return
        
        print("=" * 80)
        print(f"ПРОВЕРКА ДОПОЛНИТЕЛЬНЫХ ПОКУПОК: {phone}")
        print("=" * 80)
        print()
        
        # 2. Получаем все покупки из БД
        print("Получение покупок из БД...")
        purchases_stmt = select(PurchaseHistory).where(PurchaseHistory.user_id == user.id)
        purchases_result = await db.execute(purchases_stmt)
        purchases = purchases_result.scalars().all()
        
        print(f"Всего покупок в БД: {len(purchases)}")
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
        print(f"Всего покупок в 1С: {len(all_purchases_1c)}")
        print()
        
        # 4. Находим покупки в БД, которых нет в 1С
        print("Поиск покупок в БД, которых нет в 1С...")
        print("-" * 60)
        
        extra_purchases = []
        for p in purchases:
            key = (p.document_id_1c or "", p.product_id_1c or "", p.purchase_date.date().isoformat())
            if key not in unique_purchases_1c:
                extra_purchases.append(p)
        
        print(f"Найдено {len(extra_purchases)} покупок в БД, которых нет в 1С")
        print()
        
        if extra_purchases:
            print("Детали:")
            print()
            print(f"{'Дата':<25} {'Документ':<30} {'Товар':<30} {'Сумма':<15}")
            print("-" * 100)
            
            total_extra = 0
            for p in extra_purchases:
                date_str = p.purchase_date.strftime("%Y-%m-%d %H:%M:%S") if p.purchase_date else "N/A"
                doc = p.document_id_1c or "N/A"
                product = p.product_id_1c or "N/A"
                amount = p.total_amount / 100
                
                print(f"{date_str:<25} {doc[:28]:<30} {product[:28]:<30} {amount:<15.2f}")
                total_extra += amount
            
            print("-" * 100)
            print(f"{'ИТОГО':<70} {total_extra:<15.2f}")
            print()
            
            # Группировка по дате
            print("Группировка по дате:")
            print("-" * 60)
            
            from collections import defaultdict
            by_date = defaultdict(list)
            for p in extra_purchases:
                if p.purchase_date:
                    date_key = p.purchase_date.date().isoformat()
                    by_date[date_key].append(p)
            
            for date_key in sorted(by_date.keys()):
                purchases_list = by_date[date_key]
                total = sum(p.total_amount for p in purchases_list) / 100
                print(f"  {date_key}: {len(purchases_list)} покупок, сумма {total:.2f} руб")
        
        print()
        print("=" * 80)
        print("АНАЛИЗ:")
        print("=" * 80)
        print()
        
        if len(extra_purchases) == 1 and total_extra == 232360.00:
            print("✅ Разница объясняется 'Вводом начальных остатков'")
            print("   Это не покупка, а начальный баланс бонусной карты")
        else:
            print("⚠️  Найдены дополнительные покупки, которых нет в 1С")
            print("   Возможно, это:")
            print("   - Покупки, сделанные до подключения 1С")
            print("   - Покупки, которые не были выгружены в 1С")
            print("   - Ошибки синхронизации")


def main():
    phone = "79787566405"
    
    print()
    asyncio.run(check_extra_purchases(phone))


if __name__ == "__main__":
    main()
