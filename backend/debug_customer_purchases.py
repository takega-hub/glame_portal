"""
Диагностический скрипт для проверки расхождения данных о покупках покупателя
Проверяет:
1. Данные покупателя в БД
2. Последнюю покупку в PurchaseHistory
3. Данные из 1С OData API
4. Синхронизацию покупок
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from uuid import UUID

# Добавляем backend в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.connection import AsyncSessionLocal
from app.models.user import User
from app.models.purchase_history import PurchaseHistory
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

# Настройка переменных окружения
os.environ.setdefault("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata")
os.environ.setdefault("ONEC_API_TOKEN", "your_1c_api_token_here")

from app.services.onec_customers_service import OneCCustomersService


async def check_customer_purchases(phone: str):
    """Проверка истории покупок покупателя"""
    async with AsyncSessionLocal() as db:
        # 1. Находим покупателя по телефону
        stmt = select(User).where(User.phone == phone, User.is_customer == True)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f'❌ Покупатель с телефоном {phone} не найден')
            return
        
        print(f'✅ Покупатель найден:')
        print(f'   ID: {user.id}')
        print(f'   Телефон: {user.phone}')
        print(f'   1C Customer ID: {user.customer_id_1c}')
        print(f'   1C Discount Card ID: {user.discount_card_id_1c}')
        print(f'   Полное имя: {user.full_name}')
        print(f'   Последняя покупка в БД: {user.last_purchase_date}')
        print(f'   Количество покупок: {user.total_purchases}')
        print(f'   Общая сумма: {user.total_spent}')
        print()
        
        # 2. Проверяем историю покупок в PurchaseHistory
        print("=" * 80)
        print("ИСТОРИЯ ПОКУПОК В БД (PurchaseHistory):")
        print("=" * 80)
        
        purchase_stmt = (
            select(PurchaseHistory)
            .where(PurchaseHistory.user_id == user.id)
            .order_by(PurchaseHistory.purchase_date.desc())
            .limit(20)
        )
        result = await db.execute(purchase_stmt)
        purchases = result.scalars().all()
        
        if not purchases:
            print('   ❌ Покупок не найдено')
        else:
            print(f'   Найдено {len(purchases)} записей в PurchaseHistory')
            for i, p in enumerate(purchases[:10], 1):
                print(f'   {i}. {p.purchase_date} | {p.document_id_1c or "N/A"} | {p.product_id_1c or "N/A"} | {p.total_amount} коп')
            
            last_purchase = purchases[0]
            print()
            print(f'   Последняя покупка в PurchaseHistory:')
            print(f'      Дата: {last_purchase.purchase_date}')
            print(f'      Документ 1С: {last_purchase.document_id_1c}')
            print(f'      Товар 1С: {last_purchase.product_id_1c}')
            print(f'      Сумма: {last_purchase.total_amount} коп')
        print()
        
        # 3. Проверяем данные из 1С
        print("=" * 80)
        print("ПРОВЕРКА ДАННЫХ ИЗ 1С:")
        print("=" * 80)
        
        onec_service = OneCCustomersService()
        
        # Проверяем по дисконтной карте
        if user.discount_card_id_1c:
            print(f'\nПоиск покупок по дисконтной карте: {user.discount_card_id_1c}')
            try:
                # Получаем покупки за последний год
                end_date = datetime.now(timezone.utc)
                start_date = end_date - timedelta(days=365)
                
                purchases_1c = await onec_service.fetch_sales_by_discount_card(
                    discount_card_key=user.discount_card_id_1c,
                    start_date=start_date,
                    end_date=end_date,
                    limit=10000,
                )
                
                print(f'   Найдено {len(purchases_1c)} покупок за последний год')
                
                if purchases_1c:
                    # Сортируем по дате
                    sorted_purchases = sorted(
                        purchases_1c,
                        key=lambda x: x.get("Period", ""),
                        reverse=True
                    )
                    
                    print(f'\n   Последние 5 покупок из 1С:')
                    for i, p in enumerate(sorted_purchases[:5], 1):
                        period = p.get("Period", "N/A")
                        doc = p.get("Документ") or p.get("Recorder")
                        product = p.get("Номенклатура_Key")
                        amount = p.get("Сумма", 0)
                        store = p.get("Склад_Key")
                        recorder_type = p.get("Recorder_Type", "")
                        
                        print(f'   {i}. {period} | {doc or "N/A"} | {product or "N/A"} | {amount} | {store or "N/A"} | {recorder_type}')
                    
                    # Проверяем, есть ли покупки после последней в БД
                    if last_purchase.purchase_date:
                        last_db_date = last_purchase.purchase_date.date()
                        recent_1c_purchases = [
                            p for p in sorted_purchases
                            if datetime.fromisoformat(p.get("Period", "").replace("Z", "+00:00")).date() > last_db_date
                        ]
                        
                        if recent_1c_purchases:
                            print(f'\n   ⚠️  НАЙДЕНО {len(recent_1c_purchases)} ПОКУПОК ПОСЛЕ ПОСЛЕДНЕЙ В БД!')
                            for i, p in enumerate(recent_1c_purchases[:5], 1):
                                period = p.get("Period", "N/A")
                                doc = p.get("Документ") or p.get("Recorder")
                                product = p.get("Номенклатура_Key")
                                amount = p.get("Сумма", 0)
                                store = p.get("Склад_Key")
                                recorder_type = p.get("Recorder_Type", "")
                                
                                print(f'      {i}. {period} | {doc or "N/A"} | {product or "N/A"} | {amount} | {store or "N/A"} | {recorder_type}')
                        else:
                            print('\n   ✅ Все покупки из 1С уже есть в БД')
                
            except Exception as e:
                print(f'   ❌ Ошибка при получении покупок из 1С: {e}')
        
        # Проверяем по контрагенту
        if user.customer_id_1c:
            print(f'\nПоиск покупок по контрагенту: {user.customer_id_1c}')
            try:
                end_date = datetime.now(timezone.utc)
                start_date = end_date - timedelta(days=365)
                
                purchases_1c = await onec_service.get_customer_purchases(
                    customer_key=user.customer_id_1c,
                    start_date=start_date,
                    end_date=end_date,
                )
                
                print(f'   Найдено {len(purchases_1c)} покупок за последний год')
                
                if purchases_1c:
                    sorted_purchases = sorted(
                        purchases_1c,
                        key=lambda x: x.get("Period", ""),
                        reverse=True
                    )
                    
                    print(f'\n   Последние 5 покупок из 1С (по контрагенту):')
                    for i, p in enumerate(sorted_purchases[:5], 1):
                        period = p.get("Period", "N/A")
                        doc = p.get("Документ") or p.get("Recorder")
                        product = p.get("Номенклатура_Key")
                        amount = p.get("Сумма", 0)
                        store = p.get("Склад_Key")
                        recorder_type = p.get("Recorder_Type", "")
                        
                        print(f'   {i}. {period} | {doc or "N/A"} | {product or "N/A"} | {amount} | {store or "N/A"} | {recorder_type}')
                        
            except Exception as e:
                print(f'   ❌ Ошибка при получении покупок из 1С: {e}')
        
        print()
        print("=" * 80)
        print("АНАЛИЗ ПРОБЛЕМЫ:")
        print("=" * 80)
        
        # Проверяем возможные причины расхождения
        reasons = []
        
        if not purchases:
            reasons.append("В PurchaseHistory нет записей - синхронизация не проводилась")
        
        if last_purchase.purchase_date:
            end_date = datetime.now(timezone.utc)
            days_since_last = (end_date - last_purchase.purchase_date).days
            if days_since_last > 365:
                reasons.append(f"Последняя покупка более 365 дней назад ({days_since_last} дней)")
        
        if user.discount_card_id_1c:
            # Проверяем, есть ли покупки с ночным временем или без склада
            try:
                end_date = datetime.now(timezone.utc)
                start_date = end_date - timedelta(days=365)
                
                purchases_1c = await onec_service.fetch_sales_by_discount_card(
                    discount_card_key=user.discount_card_id_1c,
                    start_date=start_date,
                    end_date=end_date,
                    limit=10000,
                )
                
                night_reports = 0
                no_store = 0
                for p in purchases_1c:
                    recorder_type = str(p.get("Recorder_Type", "") or "")
                    is_report = "ОтчетОРозничныхПродажах" in recorder_type
                    store_key = p.get("Склад_Key")
                    
                    if is_report and not store_key:
                        no_store += 1
                    
                    if is_report:
                        date_str = p.get("Period")
                        if date_str:
                            try:
                                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                                h = dt.hour
                                if h >= 20 or h <= 5:
                                    night_reports += 1
                            except:
                                pass
                
                if night_reports > 0:
                    reasons.append(f"Обнаружено {night_reports} покупок с ночным временем (20:00-05:00), которые фильтруются")
                if no_store > 0:
                    reasons.append(f"Обнаружено {no_store} покупок без склада (отчеты), которые фильтруются")
                    
            except Exception as e:
                reasons.append(f"Ошибка проверки фильтров: {e}")
        
        if reasons:
            print("\nВозможные причины расхождения:")
            for reason in reasons:
                print(f"  • {reason}")
        else:
            print("\nПричины расхождения не найдены. Проверьте:")
            print("  • Период синхронизации (по умолчанию 365 дней)")
            print("  • Фильтрацию ночных отчетов")
            print("  • Наличие discount_card_id_1c у пользователя")
        
        print()


def main():
    """Точка входа"""
    # Телефон для проверки
    phone = "79787566405"
    
    print("=" * 80)
    print(f"ДИАГНОСТИКА ПОКУПАТЕЛЯ: {phone}")
    print("=" * 80)
    print()
    
    asyncio.run(check_customer_purchases(phone))


if __name__ == "__main__":
    main()
