"""
Скрипт для принудительной синхронизации покупок покупателя через API
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.connection import AsyncSessionLocal
from app.models.user import User


async def sync_customer_purchases(phone: str, days: int = 3650):
    """Принудительная синхронизация покупок покупателя через API"""
    async with AsyncSessionLocal() as db:
        # 1. Находим покупателя по телефону
        stmt = select(User).where(User.phone == phone, User.is_customer == True)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f'❌ Покупатель с телефоном {phone} не найден')
            return
        
        print("=" * 80)
        print(f"СИНХРОНИЗАЦИЯ ПОКУПОК: {phone}")
        print("=" * 80)
        print()
        print(f"Покупатель: {user.full_name}")
        print(f"1C Customer ID: {user.customer_id_1c}")
        print(f"1C Discount Card ID: {user.discount_card_id_1c}")
        print(f"Период синхронизации: {days} дней")
        print()
        
        # 2. Вызываем API для синхронизации
        print("Вызов API синхронизации...")
        print()
        
        # Используем HTTP запрос к API
        import httpx
        
        base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
        endpoint = f"{base_url}/api/admin/customers/{user.id}?sync=true"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(endpoint, timeout=120.0)
                
                if response.status_code == 200:
                    data = response.json()
                    print("✅ API вернул успешный ответ")
                    print()
                    print("Данные покупателя после синхронизации:")
                    print(f"  ID: {data.get('id')}")
                    print(f"  Телефон: {data.get('phone')}")
                    print(f"  Последняя покупка: {data.get('last_purchase_date')}")
                    print(f"  Количество покупок: {data.get('total_purchases')}")
                    print(f"  Общая сумма: {data.get('total_spent_rub')} руб")
                    print(f"  Сегмент: {data.get('customer_segment')}")
                else:
                    print(f"❌ API вернул ошибку {response.status_code}")
                    print(f"Ответ: {response.text[:500]}")
                    
        except Exception as e:
            print(f"❌ Ошибка при вызове API: {e}")
            print()
            print("Попробуем синхронизировать напрямую через сервис...")
            
            # Пытаемся импортировать сервис без зависимостей
            try:
                from app.services.onec_customers_service import OneCCustomersService
                
                onec_service = OneCCustomersService()
                
                print()
                print("Получение данных из 1С...")
                
                # Получаем покупки по дисконтной карте
                if user.discount_card_id_1c:
                    end_date = datetime.now(timezone.utc)
                    start_date = end_date - timedelta(days=days)
                    
                    purchases = await onec_service.fetch_sales_by_discount_card(
                        discount_card_key=user.discount_card_id_1c,
                        start_date=start_date,
                        end_date=end_date,
                        limit=10000,
                    )
                    
                    print(f"Получено {len(purchases)} покупок из 1С")
                    
                    if purchases:
                        # Сортируем по дате
                        sorted_purchases = sorted(
                            purchases,
                            key=lambda x: x.get("Period", ""),
                            reverse=True
                        )
                        
                        print()
                        print("Последние 5 покупок из 1С:")
                        for i, p in enumerate(sorted_purchases[:5], 1):
                            period = p.get("Period", "N/A")
                            doc = p.get("Документ") or p.get("Recorder")
                            product = p.get("Номенклатура_Key")
                            amount = p.get("Сумма", 0)
                            store = p.get("Склад_Key")
                            
                            print(f"  {i}. {period} | {doc or 'N/A'} | {product or 'N/A'} | {amount} | {store or 'N/A'}")
                        
                        # Проверяем, есть ли покупки после последней в БД
                        if user.last_purchase_date:
                            last_db_date = user.last_purchase_date.date()
                            recent_1c_purchases = [
                                p for p in sorted_purchases
                                if datetime.fromisoformat(p.get("Period", "").replace("Z", "+00:00")).date() > last_db_date
                            ]
                            
                            if recent_1c_purchases:
                                print()
                                print(f"⚠️  НАЙДЕНО {len(recent_1c_purchases)} ПОКУПОК ПОСЛЕ ПОСЛЕДНЕЙ В БД!")
                                print()
                                print("Эти покупки нужно добавить в БД:")
                                for i, p in enumerate(recent_1c_purchases[:10], 1):
                                    period = p.get("Period", "N/A")
                                    doc = p.get("Документ") or p.get("Recorder")
                                    product = p.get("Номенклатура_Key")
                                    amount = p.get("Сумма", 0)
                                    
                                    print(f"  {i}. {period} | {doc or 'N/A'} | {product or 'N/A'} | {amount}")
                            else:
                                print()
                                print("✅ Все покупки из 1С уже есть в БД")
                        
                else:
                    print("❌ У пользователя нет discount_card_id_1c")
                    
            except Exception as e:
                print(f"❌ Ошибка при прямом доступе к 1С: {e}")
                import traceback
                traceback.print_exc()


def main():
    phone = "79787566405"
    days = 3650  # 10 лет
    
    print()
    asyncio.run(sync_customer_purchases(phone, days))


if __name__ == "__main__":
    main()
