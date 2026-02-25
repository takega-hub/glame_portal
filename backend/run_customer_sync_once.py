#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Одноразовая синхронизация покупателей из 1С.
"""
import sys
import os
import asyncio
from dotenv import load_dotenv, find_dotenv

# Устанавливаем кодировку для Windows
if sys.platform == "win32":
    import codecs
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

# Загружаем переменные окружения из .env файла
# Ищем .env файл в корне проекта (на уровень выше backend)
env_path = find_dotenv(usecwd=True)
if env_path:
    load_dotenv(env_path, override=False)
else:
    # Пробуем найти .env в корне проекта
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_file = os.path.join(project_root, ".env")
    if os.path.exists(env_file):
        load_dotenv(env_file, override=False)

sys.path.insert(0, os.path.dirname(__file__))

from app.database.connection import AsyncSessionLocal
from app.services.customer_sync_service import CustomerSyncService


async def main() -> None:
    api_url = os.getenv("ONEC_API_URL")
    if not api_url:
        print("ONEC_API_URL is not set. Configure 1C connection before syncing.")
        return

    async with AsyncSessionLocal() as session:
        service = CustomerSyncService(session)
        
        # Настройки синхронизации
        batch_size = int(os.getenv("CUSTOMER_SYNC_BATCH_SIZE", "1000"))
        load_all = os.getenv("CUSTOMER_SYNC_LOAD_ALL", "true").lower() in ("true", "1", "yes")
        limit = int(os.getenv("CUSTOMER_SYNC_CARDS_LIMIT", "1000")) if not load_all else 10000
        days = int(os.getenv("CUSTOMER_SYNC_PURCHASE_DAYS", "365"))

        print("=" * 60)
        print("Синхронизация покупателей из 1С")
        print("=" * 60)
        if load_all:
            print(f"Режим: Загрузка ВСЕХ покупателей порциями по {batch_size}")
        else:
            print(f"Режим: Загрузка до {limit} покупателей порциями по {batch_size}")
        print("=" * 60)
        
        print("\nStarting sync_discount_cards...")
        cards_stats = await service.sync_discount_cards(
            limit=limit,
            batch_size=batch_size,
            load_all=load_all
        )

        print("\nStarting sync_purchase_history...")
        await service.sync_purchase_history(days=days)

        print("\n" + "=" * 60)
        print("Sync completed.")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
