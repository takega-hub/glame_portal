"""
Скрипт для обновления сегментов и городов для существующих покупателей.
"""
import asyncio
import sys
import os

# Добавляем путь к backend в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.core.config import get_settings
from app.models.user import User
from app.services.customer_sync_service import CustomerSyncService

# Для Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def update_all_segments():
    """Обновление сегментов для всех покупателей"""
    settings = get_settings()
    
    # Создаем движок БД
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            # Создаем сервис
            sync_service = CustomerSyncService(db)
            
            # Получаем всех покупателей
            stmt = select(User).where(User.is_customer == True)
            result = await db.execute(stmt)
            users = result.scalars().all()
            
            print(f"\nНайдено покупателей: {len(users)}")
            print("=" * 60)
            
            updated_count = 0
            skipped_count = 0
            error_count = 0
            
            for i, user in enumerate(users, 1):
                try:
                    print(f"\n[{i}/{len(users)}] Обработка: {user.full_name or 'Без имени'} ({user.phone})")
                    
                    # Обновляем сегмент
                    segment = await sync_service.update_customer_segment(user.id)
                    
                    if segment:
                        print(f"  ✓ Сегмент обновлен: {segment}")
                        updated_count += 1
                    else:
                        print(f"  - Сегмент не определен")
                        skipped_count += 1
                    
                    # Выводим город если есть
                    if user.city:
                        print(f"  Город: {user.city}")
                    else:
                        print(f"  Город: не указан")
                    
                except Exception as e:
                    print(f"  ✗ Ошибка: {e}")
                    error_count += 1
                    continue
            
            print("\n" + "=" * 60)
            print(f"Обработка завершена:")
            print(f"  Обновлено: {updated_count}")
            print(f"  Пропущено: {skipped_count}")
            print(f"  Ошибок: {error_count}")
            print("=" * 60)
            
        except Exception as e:
            print(f"\nКритическая ошибка: {e}")
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    print("Обновление сегментов покупателей...")
    asyncio.run(update_all_segments())
