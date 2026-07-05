"""
Скрипт для тестирования синхронизации покупок покупателя 79787566405
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.connection import AsyncSessionLocal
from app.models.user import User
from app.services.onec_customers_service import OneCCustomersService
from sqlalchemy import select


async def test_sync(phone: str):
    """Тестирование синхронизации покупок"""
    async with AsyncSessionLocal() as db:
        # 1. Находим покупателя по телефону
        stmt = select(User).where(User.phone == phone, User.is_customer == True)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f'❌ Покупатель с телефоном {phone} не найден')
            return
        
        print("=" * 80)
        print(f"ТЕСТИРОВАНИЕ СИНХРОНИЗАЦИИ: {phone}")
        print("=" * 80)
        print()
        print(f"Покупатель: {user.full_name}")
        print(f"1C Customer ID: {user.customer_id_1c}")
        print(f"1C Discount Card ID: {user.discount_card_id_1c}")
        print()
        
        onec_service = OneCCustomersService()
        
        # 2. Получаем покупки по контрагенту
        if user.customer_id_1c:
            print("Получение покупок по контрагенту...")
            
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=365)  # 1 год
            
            print(f"Период: {start_date.date()} - {end_date.date()}")
            print()
            
            try:
                purchases = await onec_service.get_customer_purchases(
                    customer_key=user.customer_id_1c,
                    start_date=start_date,
                    end_date=end_date,
                    limit=1000,  # Уменьшили лимит
                )
                
                print(f"Получено {len(purchases)} покупок из 1С")
                print()
                
                if purchases:
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
                    
                    sorted_purchases = sorted(purchases, key=lambda r: parse_period(r.get("Period")), reverse=True)
                    
                    print("Последние 20 покупок из 1С:")
                    print("-" * 80)
                    for i, p in enumerate(sorted_purchases[:20], 1):
                        period = p.get("Period", "N/A")
                        doc = p.get("Документ") or p.get("Recorder")
                        product = p.get("Номенклатура_Key")
                        amount = p.get("Сумма", 0)
                        store = p.get("Склад_Key")
                        
                        print(f"{i:2}. {period} | {doc[:20] if doc else 'N/A':20} | {amount:10} | {store[:15] if store else 'N/A':15}")
                    
                    print()
                    
                    # Проверяем покупки за март и апрель 2026
                    target_dates = [
                        ("2026-03-10", "10 марта 2026"),
                        ("2026-04-30", "30 апреля 2026"),
                    ]
                    
                    print("Проверка покупок за март и апрель 2026:")
                    print("-" * 80)
                    
                    for target_date, date_name in target_dates:
                        matching = [
                            p for p in sorted_purchases
                            if p.get("Period", "").startswith(target_date)
                        ]
                        
                        if matching:
                            print(f"✅ {date_name}: найдено {len(matching)} покупок")
                            for m in matching[:3]:
                                period = m.get("Period", "N/A")
                                doc = m.get("Документ") or m.get("Recorder")
                                amount = m.get("Сумма", 0)
                                print(f"   - {period} | {doc[:20] if doc else 'N/A':20} | {amount}")
                        else:
                            print(f"❌ {date_name}: не найдено")
                    
                    print()
                    
                    # Проверяем, есть ли покупки после последней в БД
                    if user.last_purchase_date:
                        last_db_date = user.last_purchase_date.date()
                        recent_purchases = [
                            p for p in sorted_purchases
                            if parse_period(p.get("Period")).date() > last_db_date
                        ]
                        
                        if recent_purchases:
                            print(f"⚠️  Найдено {len(recent_purchases)} покупок ПОСЛЕ {last_db_date}:")
                            print("-" * 80)
                            for i, p in enumerate(recent_purchases[:10], 1):
                                period = p.get("Period", "N/A")
                                doc = p.get("Документ") or p.get("Recorder")
                                product = p.get("Номенклатура_Key")
                                amount = p.get("Сумма", 0)
                                
                                print(f"{i:2}. {period} | {doc[:20] if doc else 'N/A':20} | {amount:10}")
                        else:
                            print("✅ Все покупки из 1С до последней в БД")
                    
                else:
                    print("❌ Покупок не найдено")
                    
            except Exception as e:
                print(f"❌ Ошибка при получении покупок из 1С: {e}")
                import traceback
                traceback.print_exc()
        
        else:
            print("❌ У пользователя нет customer_id_1c")


def main():
    phone = "79787566405"
    
    print()
    asyncio.run(test_sync(phone))


if __name__ == "__main__":
    main()
