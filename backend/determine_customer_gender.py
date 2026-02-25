"""
Скрипт для определения пола всех клиентов по имени
Использует AI агента для определения пола
"""
import asyncio
import sys
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.connection import AsyncSessionLocal
from app.models.user import User
from app.agents.communication_agent import CommunicationAgent
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def determine_gender_for_all_customers(
    db: AsyncSession,
    agent: CommunicationAgent,
    batch_size: int = 100,
    dry_run: bool = False
):
    """
    Определяет пол для всех клиентов
    
    Args:
        db: Database session
        agent: CommunicationAgent для определения пола
        batch_size: Размер батча для обработки
        dry_run: Если True, только показывает что будет сделано, не сохраняет
    """
    # Получаем всех клиентов с именами, у которых пол еще не определен
    stmt = select(User).where(
        User.is_customer == True,
        User.full_name.isnot(None),
        User.gender.is_(None)
    )
    
    result = await db.execute(stmt)
    customers = result.scalars().all()
    
    total = len(customers)
    logger.info(f"Найдено {total} клиентов без определенного пола")
    
    if total == 0:
        logger.info("Все клиенты уже имеют определенный пол")
        return
    
    updated = 0
    errors = 0
    skipped = 0
    
    for i, customer in enumerate(customers, 1):
        try:
            # Определяем пол через агента
            gender = agent.determine_gender(customer.full_name)
            
            if gender:
                if dry_run:
                    logger.info(f"[{i}/{total}] {customer.full_name} → {gender} (DRY RUN)")
                else:
                    # Обновляем пол в базе
                    await db.execute(
                        update(User)
                        .where(User.id == customer.id)
                        .values(gender=gender)
                    )
                    updated += 1
                    if i % 10 == 0:
                        await db.commit()
                        logger.info(f"Обработано {i}/{total} клиентов...")
            else:
                skipped += 1
                logger.warning(f"[{i}/{total}] Не удалось определить пол для: {customer.full_name}")
                
        except Exception as e:
            errors += 1
            logger.error(f"Ошибка при обработке клиента {customer.id} ({customer.full_name}): {e}")
    
    if not dry_run:
        await db.commit()
    
    logger.info(f"\n{'='*50}")
    logger.info(f"Обработка завершена:")
    logger.info(f"  Всего клиентов: {total}")
    logger.info(f"  Обновлено: {updated}")
    logger.info(f"  Пропущено (не удалось определить): {skipped}")
    logger.info(f"  Ошибок: {errors}")
    if dry_run:
        logger.info(f"\n⚠️  Это был DRY RUN. Для реального обновления запустите без флага --dry-run")


async def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Определение пола клиентов по имени')
    parser.add_argument('--dry-run', action='store_true', help='Только показать что будет сделано, не сохранять')
    parser.add_argument('--batch-size', type=int, default=100, help='Размер батча для обработки')
    
    args = parser.parse_args()
    
    async with AsyncSessionLocal() as db:
        try:
            # Создаем агента
            agent = CommunicationAgent(db)
            
            # Определяем пол для всех клиентов
            await determine_gender_for_all_customers(
                db=db,
                agent=agent,
                batch_size=args.batch_size,
                dry_run=args.dry_run
            )
            
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}", exc_info=True)
            await db.rollback()
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
