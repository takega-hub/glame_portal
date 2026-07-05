"""
Заполняет preferred_store_* для всех покупателей.

Правила:
- если в истории есть покупки с store_id_1c, берем магазин с максимумом строк,
  при равенстве - с максимальной суммой, затем с самой свежей покупкой;
- если магазин в истории отсутствует (например, только перенос продаж ДК),
  выбираем активный магазин по городу покупателя;
- если город пустой/не распознан, используем основной магазин ТРК Центрум.
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import text

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.database.connection import AsyncSessionLocal


CENTRUM_ID = "6c3a8322-a2ab-11f0-96fc-fa163e4cc04e"
YALTA_ID = "3daee4e4-a2ab-11f0-96fc-fa163e4cc04e"
MEGANOM_ID = "8cebda58-a2ab-11f0-96fc-fa163e4cc04e"
CLOSED_STORE_REDIRECTS = {
    MEGANOM_ID: CENTRUM_ID,
}


def normalize_city(city: Optional[str]) -> str:
    value = (city or "").strip().lower().replace("ё", "е")
    value = value.replace("c", "с")  # латинская C в Cимферополь
    return value


def store_for_city(city: Optional[str]) -> str:
    city_norm = normalize_city(city)
    if "ял" in city_norm:
        return YALTA_ID
    if any(part in city_norm for part in ("сим", "сім", "смф", "сфер", "сифм", "севаст", "севас", "сев")):
        return CENTRUM_ID
    return CENTRUM_ID


def to_float(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    return float(value or 0)


async def ensure_store_city_data(db) -> None:
    await db.execute(
        text(
            """
            UPDATE stores
            SET city = CASE external_id
                WHEN :centrum_id THEN 'Симферополь'
                WHEN :yalta_id THEN 'Ялта'
                WHEN '8cebda58-a2ab-11f0-96fc-fa163e4cc04e' THEN 'Симферополь'
                ELSE city
            END
            WHERE external_id IN (:centrum_id, :yalta_id, '8cebda58-a2ab-11f0-96fc-fa163e4cc04e');
            """
        ),
        {"centrum_id": CENTRUM_ID, "yalta_id": YALTA_ID},
    )


async def load_stores(db) -> Dict[str, Dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                """
                SELECT external_id, name, city, is_active
                FROM stores
                WHERE external_id IS NOT NULL
                """
            )
        )
    ).mappings().all()
    return {row["external_id"]: dict(row) for row in rows}


async def load_history_preferred(db) -> Dict[str, Dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                """
                WITH store_stats AS (
                    SELECT
                        ph.user_id,
                        ph.store_id_1c,
                        COUNT(*) AS purchase_count,
                        COALESCE(SUM(ph.total_amount), 0) AS total_amount,
                        MAX(ph.purchase_date) AS last_purchase_date
                    FROM purchase_history ph
                    WHERE ph.store_id_1c IS NOT NULL
                      AND ph.total_amount <> 0
                    GROUP BY ph.user_id, ph.store_id_1c
                ),
                ranked AS (
                    SELECT
                        store_stats.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY user_id
                            ORDER BY purchase_count DESC, total_amount DESC, last_purchase_date DESC NULLS LAST
                        ) AS rn,
                        SUM(purchase_count) OVER (PARTITION BY user_id) AS all_count
                    FROM store_stats
                )
                SELECT
                    user_id::text AS user_id,
                    store_id_1c,
                    purchase_count,
                    total_amount,
                    last_purchase_date,
                    all_count
                FROM ranked
                WHERE rn = 1
                """
            )
        )
    ).mappings().all()
    return {row["user_id"]: dict(row) for row in rows}


async def load_customers(db):
    return (
        await db.execute(
            text(
                """
                SELECT
                    u.id::text AS id,
                    u.phone,
                    u.full_name,
                    u.city,
                    u.preferred_store_external_id,
                    u.preferred_store_name,
                    COUNT(ph.id) AS purchase_rows,
                    COUNT(ph.id) FILTER (
                        WHERE COALESCE(ph.sync_metadata->>'Документ_Type', ph.sync_metadata->>'Recorder_Type', '') ILIKE '%ВводНачальныхОстатков%'
                    ) AS initial_rows,
                    COUNT(ph.id) FILTER (WHERE ph.store_id_1c IS NOT NULL) AS store_rows
                FROM users u
                LEFT JOIN purchase_history ph ON ph.user_id = u.id
                WHERE u.is_customer = TRUE
                GROUP BY u.id, u.phone, u.full_name, u.city, u.preferred_store_external_id, u.preferred_store_name
                ORDER BY u.created_at
                """
            )
        )
    ).mappings().all()


async def backfill(dry_run: bool) -> Dict[str, int]:
    async with AsyncSessionLocal() as db:
        await ensure_store_city_data(db)
        stores = await load_stores(db)
        history_preferred = await load_history_preferred(db)
        customers = await load_customers(db)

        stats = {
            "customers": len(customers),
            "from_history": 0,
            "from_city": 0,
            "only_initial_or_no_store": 0,
            "changed": 0,
            "unchanged": 0,
        }
        now = datetime.now(timezone.utc)

        examples = []
        for customer in customers:
            user_id = customer["id"]
            source = "city"
            if user_id in history_preferred:
                preferred = history_preferred[user_id]
                store_id = CLOSED_STORE_REDIRECTS.get(preferred["store_id_1c"], preferred["store_id_1c"])
                source = "history"
                stats["from_history"] += 1
                all_count = int(preferred["all_count"] or preferred["purchase_count"] or 1)
                share = to_float(preferred["purchase_count"]) / max(all_count, 1)
            else:
                store_id = store_for_city(customer["city"])
                stats["from_city"] += 1
                share = 0.0
                if int(customer["store_rows"] or 0) == 0:
                    stats["only_initial_or_no_store"] += 1

            store = stores.get(store_id)
            if not store:
                store_id = CENTRUM_ID
                store = stores[store_id]
                source = f"{source}_fallback"

            store_name = store["name"]
            changed = (
                customer["preferred_store_external_id"] != store_id
                or customer["preferred_store_name"] != store_name
            )
            if changed:
                stats["changed"] += 1
                if len(examples) < 12:
                    examples.append(
                        {
                            "phone": customer["phone"],
                            "name": customer["full_name"],
                            "city": customer["city"],
                            "old": customer["preferred_store_name"],
                            "new": store_name,
                            "source": source,
                        }
                    )
                if not dry_run:
                    await db.execute(
                        text(
                            """
                            UPDATE users
                            SET preferred_store_external_id = :store_id,
                                preferred_store_name = :store_name,
                                preferred_store_share = :share,
                                preferred_store_updated_at = :updated_at
                            WHERE id = :user_id
                            """
                        ),
                        {
                            "store_id": store_id,
                            "store_name": store_name,
                            "share": share,
                            "updated_at": now,
                            "user_id": user_id,
                        },
                    )
            else:
                stats["unchanged"] += 1
                if not dry_run:
                    await db.execute(
                        text(
                            """
                            UPDATE users
                            SET preferred_store_share = COALESCE(preferred_store_share, :share),
                                preferred_store_updated_at = COALESCE(preferred_store_updated_at, :updated_at)
                            WHERE id = :user_id
                            """
                        ),
                        {"share": share, "updated_at": now, "user_id": user_id},
                    )

        if dry_run:
            await db.rollback()
        else:
            await db.commit()

        stats["examples"] = examples
        return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill preferred stores for customers")
    parser.add_argument("--dry-run", action="store_true", help="Only print planned changes")
    args = parser.parse_args()

    result = asyncio.run(backfill(dry_run=args.dry_run))
    print("Результат:")
    for key, value in result.items():
        if key != "examples":
            print(f"  {key}: {value}")
    if result.get("examples"):
        print("\nПримеры изменений:")
        for item in result["examples"]:
            print(
                f"  {item['phone'] or '-'} | {item['name'] or '-'} | "
                f"{item['city'] or '-'} | {item['old'] or '-'} -> {item['new']} ({item['source']})"
            )


if __name__ == "__main__":
    main()
