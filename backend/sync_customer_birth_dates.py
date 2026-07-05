#!/usr/bin/env python3
"""
Синхронизация дат рождения покупателей из 1С.

Берет из справочника Контрагенты только записи с заполненной ДатаРождения
и обновляет users.birth_date по customer_id_1c.
"""
import asyncio
import os
import sys
from datetime import date, datetime
from typing import Any, Optional

import httpx
from dotenv import load_dotenv
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.connection import AsyncSessionLocal

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=False)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"), override=False)


def parse_birth_date(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                parsed = date.fromisoformat(raw[:10])
            except ValueError:
                return None
    else:
        return None

    if parsed.year <= 1900:
        return None
    return parsed


async def fetch_customers_with_birth_dates(limit: int, offset: int) -> list[dict[str, Any]]:
    api_url = os.getenv("ONEC_API_URL")
    api_token = os.getenv("ONEC_API_TOKEN")
    endpoint = os.getenv("ONEC_CUSTOMERS_ENDPOINT", "/Catalog_Контрагенты")
    if not api_url or not api_token:
        raise RuntimeError("ONEC_API_URL/ONEC_API_TOKEN не настроены")

    headers = {"Accept": "application/json"}
    headers["Authorization"] = api_token if api_token.startswith("Basic ") else f"Basic {api_token}"
    params = {
        "$filter": "ДатаРождения gt datetime'1900-01-01T00:00:00'",
        "$top": limit,
        "$skip": offset,
        "$orderby": "Ref_Key",
    }
    url = f"{api_url.rstrip('/')}{endpoint}"

    async with httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(60.0, read=300.0)) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json().get("value", [])


async def sync_birth_dates(batch_size: int = 1000, dry_run: bool = False) -> dict[str, int]:
    stats = {
        "loaded_from_1c": 0,
        "matched_users": 0,
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
    }
    offset = 0

    async with AsyncSessionLocal() as db:
        while True:
            customers = await fetch_customers_with_birth_dates(batch_size, offset)
            if not customers:
                break

            stats["loaded_from_1c"] += len(customers)
            print(f"Загружено из 1С: {stats['loaded_from_1c']}")

            for item in customers:
                customer_id_1c = item.get("Ref_Key")
                birth_date = parse_birth_date(item.get("ДатаРождения"))
                if not customer_id_1c or not birth_date:
                    stats["skipped"] += 1
                    continue

                result = await db.execute(
                    text(
                        """
                        SELECT id, birth_date
                        FROM users
                        WHERE customer_id_1c = :customer_id_1c
                          AND is_customer = true
                        LIMIT 1
                        """
                    ),
                    {"customer_id_1c": customer_id_1c},
                )
                row = result.first()
                if not row:
                    stats["skipped"] += 1
                    continue

                stats["matched_users"] += 1
                if row.birth_date == birth_date:
                    stats["unchanged"] += 1
                    continue

                stats["updated"] += 1
                if not dry_run:
                    await db.execute(
                        text(
                            """
                            UPDATE users
                            SET birth_date = :birth_date, synced_at = now()
                            WHERE id = :user_id
                            """
                        ),
                        {"birth_date": birth_date, "user_id": row.id},
                    )

            if not dry_run:
                await db.commit()

            if len(customers) < batch_size:
                break
            offset += len(customers)

    return stats


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Синхронизировать даты рождения покупателей из 1С")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stats = await sync_birth_dates(batch_size=args.batch_size, dry_run=args.dry_run)
    print("Готово:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
