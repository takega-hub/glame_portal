"""
Скрипт для определения пола всех клиентов по имени
1. Сначала пытается определить алгоритмом (быстро)
2. Если не получается - использует LLM (точнее)
3. Или сразу использует LLM для всех (опция --use-llm)
"""
import asyncio
import sys
import json
from typing import Optional
from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.connection import AsyncSessionLocal
from app.models.user import User
from app.agents.communication_agent import CommunicationAgent
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def determine_gender_with_llm(agent: CommunicationAgent, name: str) -> Optional[str]:
    """
    Определение пола через LLM
    
    Args:
        agent: CommunicationAgent
        name: Полное имя клиента
    
    Returns:
        "male", "female" или None
    """
    prompt = f"""Определи пол человека по имени.

Имя: {name}

Верни только одно слово: "male" (мужской), "female" (женский) или "unknown" (не удалось определить).

Примеры:
- "Кальчева Татьяна" → female
- "Корлюков Андрей" → male
- "Елена" → female
- "Андрей" → male

Ответ (только одно слово):"""

    try:
        response = await agent.generate_response(
            prompt=prompt,
            system_prompt="Ты помощник для определения пола по имени. Отвечай только одним словом: male, female или unknown.",
            max_tokens=10
        )
        
        if response:
            response_lower = response.strip().lower()
            if response_lower in ["male", "мужской"]:
                return "male"
            elif response_lower in ["female", "женский"]:
                return "female"
            else:
                return None
    except Exception as e:
        logger.error(f"Ошибка при определении пола через LLM для '{name}': {e}")
        return None
    
    return None


async def determine_gender_for_all_customers(
    db: AsyncSession,
    agent: CommunicationAgent,
    batch_size: int = 50,
    dry_run: bool = False
):
    """
    Определяет пол для всех клиентов (только алгоритм по списку имен)
    
    Args:
        db: Database session
        agent: CommunicationAgent для определения пола
        batch_size: Размер батча для коммита
        dry_run: Если True, только показывает что будет сделано, не сохраняет
    """
    # Проверяем, существует ли колонка gender в БД
    try:
        check_query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' AND column_name = 'gender'
        """)
        result = await db.execute(check_query)
        column_exists = result.scalar_one_or_none() is not None
        
        if not column_exists:
            logger.warning("⚠️  Колонка 'gender' не найдена в таблице 'users'")
            logger.info("💡 Запустите скрипт 'add_gender_column.py' для создания колонки:")
            logger.info("   python add_gender_column.py")
            return
    except Exception as e:
        logger.error(f"Ошибка при проверке колонки gender: {e}")
        return
    
    # Получаем всех клиентов с именами
    stmt = select(User).where(
        User.is_customer == True,
        User.full_name.isnot(None)
    ).order_by(User.id)
    
    result = await db.execute(stmt)
    customers = result.scalars().all()
    
    total = len(customers)
    logger.info(f"Найдено {total} клиентов с именами")
    
    if total == 0:
        logger.info("Клиенты не найдены")
        return
    
    # Статистика
    updated = 0
    skipped = 0
    errors = 0
    algorithm_determined = 0
    llm_determined = 0
    already_has_gender = 0
    
    for i, customer in enumerate(customers, 1):
        try:
            # Пропускаем, если пол уже определен (безопасный доступ к атрибуту)
            current_gender = getattr(customer, 'gender', None)
            if current_gender:
                already_has_gender += 1
                if i % 100 == 0:
                    logger.info(f"Обработано {i}/{total} клиентов... (пропущено с полом: {already_has_gender})")
                continue
            
            gender = None
            method = None
            
            # Используем ТОЛЬКО алгоритм по списку имен (без LLM и без окончаний)
            # Если имя не найдено в списке - пропускаем (пол определяется вручную)
            gender = agent.determine_gender(customer.full_name)
            if gender:
                method = "алгоритм (только явные имена)"
                algorithm_determined += 1
            else:
                # Если алгоритм не определил - пропускаем (не используем LLM)
                # Пол будет определен вручную в кабинете
                method = None
            
            if gender:
                if dry_run:
                    logger.info(f"[{i}/{total}] {customer.full_name} → {gender} ({method}) [DRY RUN]")
                else:
                    # Обновляем пол в базе через прямой SQL UPDATE (так как поле может быть не видно в ORM)
                    try:
                        # Извлекаем данные сразу, чтобы избежать lazy loading
                        customer_id = customer.id
                        customer_name = customer.full_name
                        
                        # Используем прямой SQL UPDATE
                        sql_update = text("UPDATE users SET gender = :gender_value WHERE id = :user_id")
                        result = await db.execute(sql_update, {"gender_value": gender, "user_id": str(customer_id)})
                        updated += 1
                        
                        # Коммитим батчами
                        if updated % batch_size == 0:
                            await db.commit()
                            logger.info(f"✅ Коммит: обработано {i}/{total} клиентов... (обновлено: {updated}, алгоритм: {algorithm_determined}, LLM: {llm_determined})")
                    except Exception as update_error:
                        logger.error(f"❌ Ошибка при обновлении пола для {customer.id}: {update_error}", exc_info=True)
                        await db.rollback()
                        errors += 1
            else:
                skipped += 1
                if i % 100 == 0:
                    logger.warning(f"[{i}/{total}] Не удалось определить пол для: {customer_name}")
                
        except Exception as e:
            errors += 1
            customer_id_str = str(customer_id) if 'customer_id' in locals() else "unknown"
            customer_name_str = customer_name if 'customer_name' in locals() else "unknown"
            logger.error(f"Ошибка при обработке клиента {customer_id_str} ({customer_name_str}): {e}", exc_info=True)
    
    if not dry_run:
        # Коммитим оставшиеся изменения
        try:
            await db.commit()
            logger.info("✅ Финальный коммит выполнен")
        except Exception as e:
            logger.error(f"❌ Ошибка при финальном коммите: {e}", exc_info=True)
            await db.rollback()
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Обработка завершена:")
    logger.info(f"  Всего клиентов: {total}")
    logger.info(f"  Уже имели пол: {already_has_gender}")
    logger.info(f"  Обновлено: {updated}")
    logger.info(f"    - Определено алгоритмом: {algorithm_determined}")
    logger.info(f"    - Определено через LLM: {llm_determined}")
    logger.info(f"  Пропущено (не удалось определить): {skipped}")
    logger.info(f"  Ошибок: {errors}")
    if dry_run:
        logger.info(f"\n⚠️  Это был DRY RUN. Для реального обновления запустите без флага --dry-run")


async def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Определение пола клиентов по имени',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  # Сначала алгоритм, потом LLM для неопределенных (рекомендуется)
  python determine_gender_all_customers.py
  
  # Сразу использовать LLM для всех (медленнее, но точнее)
  python determine_gender_all_customers.py --use-llm
  
  # Только показать что будет сделано
  python determine_gender_all_customers.py --dry-run
        """
    )
    parser.add_argument(
        '--use-llm',
        action='store_true',
        help='Использовать LLM для всех клиентов (медленнее, но точнее). По умолчанию: сначала алгоритм, потом LLM'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Только показать что будет сделано, не сохранять'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=50,
        help='Размер батча для коммита (по умолчанию: 50)'
    )
    
    args = parser.parse_args()
    
    async with AsyncSessionLocal() as db:
        try:
            # Создаем агента
            agent = CommunicationAgent(db)
            
            logger.info(f"Режим: Алгоритм по списку имен (без LLM и без окончаний)")
            logger.info(f"Режим выполнения: {'DRY RUN' if args.dry_run else 'РЕАЛЬНОЕ ОБНОВЛЕНИЕ'}")
            logger.info(f"Размер батча: {args.batch_size}")
            logger.info("")
            
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
