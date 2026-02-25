"""
Скрипт для исправления пола: сбрасывает пол для клиентов, у которых только фамилия (без явного имени)
"""
import asyncio
import sys
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.connection import AsyncSessionLocal
from app.models.user import User
from app.agents.communication_agent import CommunicationAgent
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def fix_gender_for_surnames_only(
    db: AsyncSession,
    agent: CommunicationAgent,
    batch_size: int = 50,
    dry_run: bool = False
):
    """
    Исправляет пол для клиентов: сбрасывает пол, если только фамилия (без явного имени)
    
    Args:
        db: Database session
        agent: CommunicationAgent для определения пола
        batch_size: Размер батча для коммита
        dry_run: Если True, только показывает что будет сделано, не сохраняет
    """
    # Получаем всех клиентов с именами и полом
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
    reset_count = 0
    kept_count = 0
    errors = 0
    
    # Список явных женских имен
    female_names = {
        'анна', 'мария', 'елена', 'наталья', 'ольга', 'татьяна', 'ирина', 'екатерина',
        'светлана', 'юлия', 'анастасия', 'дарья', 'марина', 'людмила', 'валентина',
        'галина', 'надежда', 'виктория', 'любовь', 'валерия', 'алина',
        'кристина', 'полина', 'вероника', 'диана', 'майя', 'софия',
        'александра', 'василиса', 'милана', 'милена', 'алиса', 'эмилия', 'эмили',
        'виолетта', 'маргарита', 'елизавета', 'ксения', 'мирослава',
        'злата', 'ярослава', 'арина', 'карина', 'ангелина', 'дугма', 'нисо',
        'эмине', 'яна', 'лариса', 'раиса', 'тамара', 'зоя', 'лидия',
        'ханум', 'лилия', 'влада'
    }
    
    # Список явных мужских имен
    male_names = {
        'александр', 'дмитрий', 'максим', 'сергей', 'андрей', 'алексей', 'артем',
        'илья', 'кирилл', 'михаил', 'николай', 'матвей', 'роман', 'павел', 'владимир',
        'денис', 'тимофей', 'иван', 'евгений', 'даниил', 'данил', 'данила', 'арсений',
        'леонид', 'степан', 'владислав', 'игорь', 'семен', 'антон',
        'василий', 'виктор', 'юрий', 'олег', 'валерий'
    }
    
    for i, customer in enumerate(customers, 1):
        try:
            # Извлекаем данные сразу
            customer_id = customer.id
            customer_name = customer.full_name
            
            # Получаем текущий пол через прямой SQL
            check_gender_query = text("SELECT gender FROM users WHERE id = :user_id")
            gender_result = await db.execute(check_gender_query, {"user_id": str(customer_id)})
            gender_row = gender_result.first()
            current_gender = gender_row[0] if gender_row else None
            
            # Если пол не установлен - пропускаем
            if not current_gender:
                if i % 100 == 0:
                    logger.info(f"Обработано {i}/{total} клиентов... (пропущено без пола: {i - reset_count - kept_count})")
                continue
            
            # Проверяем имя
            if not customer_name or not customer_name.strip():
                continue
            
            name_parts = customer_name.strip().split()
            
            # Если только одно слово (фамилия) - сбрасываем пол
            if len(name_parts) == 1:
                if dry_run:
                    logger.info(f"[{i}/{total}] {customer_name} → сброс пола (только фамилия) [DRY RUN]")
                else:
                    sql_update = text("UPDATE users SET gender = NULL WHERE id = :user_id")
                    await db.execute(sql_update, {"user_id": str(customer_id)})
                    reset_count += 1
                    
                    if reset_count % batch_size == 0:
                        await db.commit()
                        logger.info(f"✅ Коммит: обработано {i}/{total} клиентов... (сброшено: {reset_count}, оставлено: {kept_count})")
                continue
            
            # Если второе слово начинается с цифры (телефон) - сбрасываем пол
            if len(name_parts) >= 2 and name_parts[1][0].isdigit():
                if dry_run:
                    logger.info(f"[{i}/{total}] {customer_name} → сброс пола (фамилия + телефон) [DRY RUN]")
                else:
                    sql_update = text("UPDATE users SET gender = NULL WHERE id = :user_id")
                    await db.execute(sql_update, {"user_id": str(customer_id)})
                    reset_count += 1
                    
                    if reset_count % batch_size == 0:
                        await db.commit()
                        logger.info(f"✅ Коммит: обработано {i}/{total} клиентов... (сброшено: {reset_count}, оставлено: {kept_count})")
                continue
            
            # Проверяем, есть ли явное имя в списке
            words_to_check = []
            if len(name_parts) >= 1:
                words_to_check.append(name_parts[0].lower())
            if len(name_parts) >= 2 and not name_parts[1][0].isdigit():
                words_to_check.append(name_parts[1].lower())
            
            # Проверяем, есть ли хотя бы одно явное имя в списке
            # ВАЖНО: Женские имена имеют приоритет - если есть женское имя, пол должен быть female
            has_female_name = False
            has_male_name = False
            has_explicit_name = False
            
            for word in words_to_check:
                if word in female_names:
                    has_female_name = True
                    has_explicit_name = True
                elif word in male_names:
                    has_male_name = True
                    has_explicit_name = True
            
            # Если есть женское имя, но пол установлен как male - исправляем
            if has_female_name and current_gender == "male":
                if dry_run:
                    logger.info(f"[{i}/{total}] {customer_name} → исправление: female (есть женское имя) [DRY RUN]")
                else:
                    sql_update = text("UPDATE users SET gender = 'female' WHERE id = :user_id")
                    await db.execute(sql_update, {"user_id": str(customer_id)})
                    reset_count += 1  # Считаем как исправление
                    
                    if reset_count % batch_size == 0:
                        await db.commit()
                        logger.info(f"✅ Коммит: обработано {i}/{total} клиентов... (исправлено: {reset_count}, оставлено: {kept_count})")
                continue
            
            # Если есть мужское имя, но пол установлен как female - исправляем
            if has_male_name and not has_female_name and current_gender == "female":
                if dry_run:
                    logger.info(f"[{i}/{total}] {customer_name} → исправление: male (есть мужское имя) [DRY RUN]")
                else:
                    sql_update = text("UPDATE users SET gender = 'male' WHERE id = :user_id")
                    await db.execute(sql_update, {"user_id": str(customer_id)})
                    reset_count += 1  # Считаем как исправление
                    
                    if reset_count % batch_size == 0:
                        await db.commit()
                        logger.info(f"✅ Коммит: обработано {i}/{total} клиентов... (исправлено: {reset_count}, оставлено: {kept_count})")
                continue
            
            # Если нет явного имени в списке - сбрасываем пол
            if not has_explicit_name:
                if dry_run:
                    logger.info(f"[{i}/{total}] {customer_name} → сброс пола (нет явного имени в списке) [DRY RUN]")
                else:
                    sql_update = text("UPDATE users SET gender = NULL WHERE id = :user_id")
                    await db.execute(sql_update, {"user_id": str(customer_id)})
                    reset_count += 1
                    
                    if reset_count % batch_size == 0:
                        await db.commit()
                        logger.info(f"✅ Коммит: обработано {i}/{total} клиентов... (сброшено: {reset_count}, оставлено: {kept_count})")
            else:
                # Пол оставляем, так как есть явное имя
                kept_count += 1
                if i % 100 == 0:
                    logger.info(f"Обработано {i}/{total} клиентов... (сброшено: {reset_count}, оставлено: {kept_count})")
                
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
    logger.info(f"  Сброшено/исправлено пола: {reset_count}")
    logger.info(f"    - Сброшено (только фамилия/нет явного имени)")
    logger.info(f"    - Исправлено (неправильно определенный пол)")
    logger.info(f"  Оставлено пола (есть явное имя и пол правильный): {kept_count}")
    logger.info(f"  Ошибок: {errors}")
    if dry_run:
        logger.info(f"\n⚠️  Это был DRY RUN. Для реального обновления запустите без флага --dry-run")


async def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Исправление пола: сброс для клиентов с только фамилией',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  # Исправить пол для всех клиентов
  python fix_gender_for_surnames_only.py
  
  # Только показать что будет сделано
  python fix_gender_for_surnames_only.py --dry-run
        """
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
            
            logger.info(f"Режим выполнения: {'DRY RUN' if args.dry_run else 'РЕАЛЬНОЕ ОБНОВЛЕНИЕ'}")
            logger.info(f"Размер батча: {args.batch_size}")
            logger.info("")
            
            # Исправляем пол
            await fix_gender_for_surnames_only(
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
