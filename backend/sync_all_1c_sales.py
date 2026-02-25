"""
Скрипт для полной синхронизации всех доступных данных о продажах из 1С
Синхронизирует данные с самой ранней доступной даты до текущей даты
"""
import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import logging

# Добавляем корневую директорию проекта в путь
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))
# Также добавляем родительскую директорию для импорта app
parent_dir = backend_dir.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from app.database.connection import AsyncSessionLocal
from app.services.onec_sales_sync_service import OneCSalesSyncService
from dotenv import load_dotenv

# Исправление кодировки для Windows
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Загружаем переменные окружения
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def sync_all_1c_sales(
    start_date: datetime = None,
    end_date: datetime = None,
    chunk_days: int = 30,
    incremental: bool = True
):
    """
    Полная синхронизация всех доступных данных из 1С
    
    Args:
        start_date: Начальная дата (если None, используется 2025-11-10 - самая ранняя доступная)
        end_date: Конечная дата (если None, используется текущая дата)
        chunk_days: Количество дней в одном чанке (для разбиения больших периодов)
        incremental: Инкрементальная синхронизация (только новые данные)
    """
    # Определяем даты
    if not start_date:
        # Самая ранняя доступная дата из 1С (из проверки)
        start_date = datetime(2025, 11, 10, 0, 0, 0)
    
    if not end_date:
        end_date = datetime.now()
    
    logger.info("=" * 80)
    logger.info("ПОЛНАЯ СИНХРОНИЗАЦИЯ ДАННЫХ О ПРОДАЖАХ ИЗ 1С")
    logger.info("=" * 80)
    logger.info(f"Период: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
    logger.info(f"Режим: {'Инкрементальная' if incremental else 'Полная'} синхронизация")
    logger.info(f"Размер чанка: {chunk_days} дней")
    logger.info("")
    
    total_days = (end_date - start_date).days + 1
    logger.info(f"Всего дней для синхронизации: {total_days}")
    
    # Разбиваем период на чанки
    chunks = []
    current_start = start_date
    
    while current_start < end_date:
        current_end = min(current_start + timedelta(days=chunk_days - 1), end_date)
        chunks.append((current_start, current_end))
        current_start = current_end + timedelta(seconds=1)
    
    logger.info(f"Период разбит на {len(chunks)} чанков")
    logger.info("")
    
    total_stats = {
        "total_records": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "chunks_processed": 0,
        "chunks_total": len(chunks)
    }
    
    try:
        async with AsyncSessionLocal() as db:
            async with OneCSalesSyncService(db) as sync_service:
                for i, (chunk_start, chunk_end) in enumerate(chunks, 1):
                    logger.info("-" * 80)
                    logger.info(f"Обработка чанка {i}/{len(chunks)}: {chunk_start.strftime('%Y-%m-%d')} - {chunk_end.strftime('%Y-%m-%d')}")
                    logger.info("-" * 80)
                    
                    try:
                        result = await sync_service.sync_period(
                            start_date=chunk_start,
                            end_date=chunk_end,
                            incremental=incremental
                        )
                        
                        # Коммитим после каждого чанка
                        await db.commit()
                        
                        logger.info(f"Чанк {i} завершен:")
                        logger.info(f"  - Всего записей: {result.get('total_records', 0)}")
                        logger.info(f"  - Добавлено: {result.get('inserted', 0)}")
                        logger.info(f"  - Обновлено: {result.get('updated', 0)}")
                        logger.info(f"  - Пропущено: {result.get('skipped', 0)}")
                        
                        # Суммируем статистику
                        total_stats["total_records"] += result.get('total_records', 0)
                        total_stats["inserted"] += result.get('inserted', 0)
                        total_stats["updated"] += result.get('updated', 0)
                        total_stats["skipped"] += result.get('skipped', 0)
                        total_stats["chunks_processed"] += 1
                        
                    except Exception as e:
                        logger.error(f"Ошибка при обработке чанка {i}: {e}", exc_info=True)
                        await db.rollback()
                        total_stats["errors"] += 1
                        # Продолжаем обработку следующих чанков
                        continue
                    
                    # Небольшая пауза между чанками, чтобы не перегружать 1С
                    if i < len(chunks):
                        await asyncio.sleep(1)
    
    except Exception as e:
        logger.error(f"Критическая ошибка синхронизации: {e}", exc_info=True)
        raise
    
    # Итоговая статистика
    logger.info("")
    logger.info("=" * 80)
    logger.info("ИТОГОВАЯ СТАТИСТИКА")
    logger.info("=" * 80)
    logger.info(f"Обработано чанков: {total_stats['chunks_processed']}/{total_stats['chunks_total']}")
    logger.info(f"Всего записей: {total_stats['total_records']:,}")
    logger.info(f"Добавлено: {total_stats['inserted']:,}")
    logger.info(f"Обновлено: {total_stats['updated']:,}")
    logger.info(f"Пропущено: {total_stats['skipped']:,}")
    if total_stats['errors'] > 0:
        logger.warning(f"Ошибок: {total_stats['errors']}")
    logger.info("=" * 80)
    
    return total_stats


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Полная синхронизация данных о продажах из 1С')
    parser.add_argument(
        '--start-date',
        type=str,
        help='Начальная дата (формат: YYYY-MM-DD, по умолчанию: 2025-11-10)'
    )
    parser.add_argument(
        '--end-date',
        type=str,
        help='Конечная дата (формат: YYYY-MM-DD, по умолчанию: текущая дата)'
    )
    parser.add_argument(
        '--chunk-days',
        type=int,
        default=30,
        help='Количество дней в одном чанке (по умолчанию: 30)'
    )
    parser.add_argument(
        '--full-sync',
        action='store_true',
        help='Полная синхронизация (перезапись существующих данных)'
    )
    
    args = parser.parse_args()
    
    # Парсим даты
    start_date = None
    if args.start_date:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
    
    end_date = None
    if args.end_date:
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
        # Добавляем время до конца дня
        end_date = end_date.replace(hour=23, minute=59, second=59)
    
    incremental = not args.full_sync
    
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        result = asyncio.run(sync_all_1c_sales(
            start_date=start_date,
            end_date=end_date,
            chunk_days=args.chunk_days,
            incremental=incremental
        ))
        
        if result['errors'] == 0:
            print("\n✅ Синхронизация успешно завершена!")
            sys.exit(0)
        else:
            print(f"\n⚠️ Синхронизация завершена с ошибками ({result['errors']} чанков)")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n❌ Синхронизация прервана пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
