"""
Скрипт для ночной синхронизации остатков из 1С.

Использование:
    python -m scripts.sync_stocks_nightly
"""
import asyncio
import sys
from pathlib import Path
import logging

# Добавляем корневую директорию проекта в путь
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.database.connection import AsyncSessionLocal
from app.services.onec_stock_service import OneCStockService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def sync_nightly() -> None:
    async with AsyncSessionLocal() as session:
        async with OneCStockService(session) as stock_service:
            logger.info("Starting nightly 1C stock sync")
            result = await stock_service.sync_stocks()
            logger.info("Nightly stock sync finished: %s", result)


def main() -> None:
    asyncio.run(sync_nightly())


if __name__ == "__main__":
    main()
