"""
Скрипт для удаления тестовых образов из базы данных
"""
import asyncio
import sys
from pathlib import Path

# Добавляем путь к корню проекта
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from app.database.connection import AsyncSessionLocal
from app.models.look import Look


async def delete_test_looks():
    """Удаление тестовых образов"""
    test_look_names = [
        "Романтичный вечер",
        "Повседневный стиль"
    ]
    
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(Look).where(Look.name.in_(test_look_names))
            )
            test_looks = result.scalars().all()
            
            if not test_looks:
                print("Тестовые образы не найдены.")
                return
            
            deleted_count = 0
            for look in test_looks:
                print(f"Удаление образа: {look.name} (ID: {look.id})")
                await db.delete(look)
                deleted_count += 1
            
            await db.commit()
            print(f"\nУспешно удалено тестовых образов: {deleted_count}")
            
        except Exception as e:
            await db.rollback()
            print(f"Ошибка при удалении тестовых образов: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(delete_test_looks())
