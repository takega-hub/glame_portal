"""
Скрипт для ночной синхронизации продаж из 1С
Запускается по расписанию (например, через cron или планировщик задач Windows)

Использование:
    python -m scripts.sync_sales_nightly

Или через cron (Linux/Mac):
    0 2 * * * cd /path/to/backend && python -m scripts.sync_sales_nightly

Или через Task Scheduler (Windows):
    Создайте задачу, которая запускает:
    python -m scripts.sync_sales_nightly
"""
import asyncio
import sys
import os
from pathlib import Path

# Добавляем корневую директорию проекта в путь
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from datetime import datetime, timedelta
from app.database.connection import AsyncSessionLocal
from app.services.onec_sales_sync_service import OneCSalesSyncService
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def sync_nightly():
    """Ночная синхронизация продаж"""
    logger.info("Начало ночной синхронизации продаж")
    
    try:
        async with AsyncSessionLocal() as db:
            async with OneCSalesSyncService(db) as sync_service:
                # Синхронизируем данные за последние 7 дней (инкрементально)
                # Это гарантирует, что мы не пропустим данные, даже если скрипт не запускался несколько дней
                end_date = datetime.now()
                start_date = end_date - timedelta(days=7)
                
                # Инкрементальная синхронизация (только новые данные)
                result = await sync_service.sync_period(
                    start_date=start_date,
                    end_date=end_date,
                    incremental=True
                )
                
                logger.info(f"Ночная синхронизация завершена: {result}")
                
                # Также синхронизируем данные за вчерашний день полностью
                yesterday = (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                yesterday_end = yesterday + timedelta(days=1) - timedelta(seconds=1)
                
                result_yesterday = await sync_service.sync_period(
                    start_date=yesterday,
                    end_date=yesterday_end,
                    incremental=False  # Полная синхронизация вчерашнего дня
                )
                
                logger.info(f"Синхронизация вчерашнего дня завершена: {result_yesterday}")
                
                return {
                    "success": True,
                    "last_7_days": result,
                    "yesterday": result_yesterday
                }
    except Exception as e:
        logger.error(f"Ошибка ночной синхронизации: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


if __name__ == "__main__":
    result = asyncio.run(sync_nightly())
    if result.get("success"):
        print("✅ Синхронизация успешно завершена")
        sys.exit(0)
    else:
        print(f"❌ Ошибка синхронизации: {result.get('error')}")
        sys.exit(1)
