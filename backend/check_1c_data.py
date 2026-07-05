"""
Скрипт для проверки данных из 1С OData API
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.connection import AsyncSessionLocal
from app.models.user import User
from app.services.onec_customers_service import OneCCustomersService


async def check_1c_data(phone: str):
    """Проверка данных из 1С OData API"""
    async with AsyncSessionLocal() as db:
        # 1. Находим покупателя по телефону
        stmt = select(User).where(User.phone == phone, User.is_customer == True)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f'❌ Покупатель с телефоном {phone} не найден')
            return
        
        print("=" * 80)
        print(f"ПРОВЕРКА ДАННЫХ ИЗ 1С: {phone}")
        print("=" * 80)
        print()
        print(f"Покупатель: {user.full_name}")
        print(f"1C Customer ID: {user.customer_id_1c}")
        print(f"1C Discount Card ID: {user.discount_card_id_1c}")
        print()
        
        onec_service = OneCCustomersService()
        
        # 2. Получаем покупки по дисконтной карте
        if user.discount_card_id_1c:
            print("Получение покупок по дисконтной карте...")
            
            # Без фильтра по дате
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=3650)  # 10 лет
            
            print(f"Период: {start_date.date()} - {end_date.date()}")
            print()
            
            try:
                purchases = await onec_service.fetch_sales_by_discount_card(
                    discount_card_key=user.discount_card_id_1c,
                    start_date=start_date,
                    end_date=end_date,
                    limit=10000,
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
                        except Exception:
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
                        recorder_type = p.get("Recorder_Type", "")
                        
                        print(f"{i:2}. {period} | {doc[:20] if doc else 'N/A':20} | {amount:10} | {store[:15] if store else 'N/A':15} | {recorder_type[:30] if recorder_type else 'N/A':30}")
                    
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
                    
                    # Проверяем все даты после 2026-02-12
                    last_db_date = datetime(2026, 2, 12, 15, 10, 43, tzinfo=timezone.utc)
                    recent_purchases = [
                        p for p in sorted_purchases
                        if parse_period(p.get("Period")) > last_db_date
                    ]
                    
                    if recent_purchases:
                        print(f"⚠️  Найдено {len(recent_purchases)} покупок ПОСЛЕ 2026-02-12:")
                        print("-" * 80)
                        for i, p in enumerate(recent_purchases[:20], 1):
                            period = p.get("Period", "N/A")
                            doc = p.get("Документ") or p.get("Recorder")
                            product = p.get("Номенклатура_Key")
                            amount = p.get("Сумма", 0)
                            store = p.get("Склад_Key")
                            recorder_type = p.get("Recorder_Type", "")
                            
                            print(f"{i:2}. {period} | {doc[:20] if doc else 'N/A':20} | {amount:10} | {store[:15] if store else 'N/A':15} | {recorder_type[:30] if recorder_type else 'N/A':30}")
                    else:
                        print("✅ Все покупки из 1С до 2026-02-12")
                    
                else:
                    print("❌ Покупок не найдено")
                    
            except Exception as e:
                print(f"❌ Ошибка при получении покупок из 1С: {e}")
                import traceback
                traceback.print_exc()
        
        else:
            print("❌ У пользователя нет discount_card_id_1c")


def main():
    phone = "79787566405"
    
    print()
    asyncio.run(check_1c_data(phone))


if __name__ == "__main__":
    main()
