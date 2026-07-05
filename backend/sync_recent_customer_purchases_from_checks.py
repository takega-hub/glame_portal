#!/usr/bin/env python3
"""Sync recent customer purchase history from exact 1C receipt documents."""
import argparse
import asyncio
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.connection import AsyncSessionLocal
from app.models.user import User
from app.services.customer_analytics_service import CustomerAnalyticsService
from app.services.onec_customers_service import OneCCustomersService
from app.services.onec_sales_service import OneCSalesService
from sync_customer_sales_and_points import recalculate_customer_metrics, upsert_purchase

ZERO_GUID = "00000000-0000-0000-0000-000000000000"


def load_env() -> None:
    backend_dir = Path(__file__).resolve().parent
    load_dotenv(backend_dir.parent / ".env", override=False)
    load_dotenv(backend_dir / ".env", override=False)


def normalize_phone(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 11 and digits.startswith("8"):
        return "7" + digits[1:]
    if len(digits) == 10:
        return "7" + digits
    return digits


def gender_by_name(name: Optional[str]) -> Optional[str]:
    text = (name or "").strip().lower()
    if text.endswith(("а", "я")):
        return "female"
    return None


def order_to_purchase(order: Dict[str, Any]) -> Dict[str, Any]:
    raw = order.get("raw_1c_data") or {}
    document_id = order.get("document_id") or raw.get("Recorder")
    return {
        "Period": order.get("date") or raw.get("Period"),
        "Сумма": order.get("revenue", 0),
        "Количество": order.get("items_count", 0),
        "Номенклатура_Key": order.get("product_id") or raw.get("Номенклатура_Key"),
        "Номенклатура_Description": order.get("product_name") or raw.get("Номенклатура_Description"),
        "Характеристика_Key": raw.get("Характеристика_Key"),
        "Документ": document_id,
        "Документ_Type": "StandardODATA.Document_ЧекККМ",
        "Recorder": document_id,
        "Recorder_Type": "StandardODATA.Document_ЧекККМ",
        "Склад_Key": order.get("store_id") or raw.get("СтруктурнаяЕдиница_Key") or raw.get("Склад_Key"),
        "Контрагент_Key": order.get("customer_id") or raw.get("Контрагент_Key"),
        "ДисконтнаяКарта_Key": raw.get("ДисконтнаяКарта_Key"),
        "raw_1c_data": raw,
    }


async def fetch_discount_card(onec: OneCCustomersService, card_id: str) -> Optional[Dict[str, Any]]:
    if not onec.client or not card_id or card_id == ZERO_GUID:
        return None
    url = f"{onec.api_url.rstrip('/')}/Catalog_ДисконтныеКарты(guid'{card_id}')"
    response = await onec.client.get(url)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


async def resolve_or_create_user(
    db,
    onec: OneCCustomersService,
    customer_id: Optional[str],
    discount_card_id: Optional[str],
    create_missing: bool,
) -> Optional[User]:
    if discount_card_id and discount_card_id != ZERO_GUID:
        result = await db.execute(select(User).where(User.discount_card_id_1c == discount_card_id))
        user = result.scalars().first()
        if user:
            return user

        card = await fetch_discount_card(onec, discount_card_id)
        phone = normalize_phone((card or {}).get("КодКартыШтрихкод"))
        if phone:
            result = await db.execute(select(User).where(User.phone == phone))
            user = result.scalars().first()
            if user:
                user.discount_card_id_1c = discount_card_id
                user.customer_id_1c = user.customer_id_1c or (card or {}).get("ВладелецКарты_Key") or customer_id
                user.discount_card_number = user.discount_card_number or phone
                user.is_customer = True
                return user

        if create_missing and card and phone:
            customer_key = card.get("ВладелецКарты_Key") or customer_id
            name = card.get("Description") or phone
            if customer_key:
                try:
                    customer = await onec.client.get(f"{onec.api_url.rstrip('/')}/Catalog_Контрагенты(guid'{customer_key}')")
                    if customer.status_code == 200:
                        customer_data = customer.json()
                        name = (
                            customer_data.get("Description")
                            or customer_data.get("ФИО")
                            or customer_data.get("НаименованиеПолное")
                            or name
                        )
                except Exception:
                    pass
            user = User(
                phone=phone,
                discount_card_number=phone,
                discount_card_id_1c=discount_card_id,
                customer_id_1c=customer_key,
                full_name=name,
                is_customer=True,
                role="customer",
                synced_at=datetime.now(timezone.utc),
                gender=gender_by_name(name),
                loyalty_points=0,
                total_purchases=0,
                total_spent=0,
            )
            db.add(user)
            await db.flush()
            return user

    if customer_id and customer_id != ZERO_GUID:
        result = await db.execute(select(User).where(User.customer_id_1c == customer_id))
        users = result.scalars().all()
        if len(users) == 1:
            return users[0]
    return None


async def sync_recent(days: int, create_missing: bool, dry_run: bool) -> Dict[str, Any]:
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    print(f"Receipt purchase sync: {start_date.isoformat()} -> {end_date.isoformat()}")

    async with OneCSalesService() as sales:
        sales_data = await sales.fetch_sales_from_api(start_date, end_date)
    if sales_data.get("source") != "Document_ЧекККМ":
        raise RuntimeError(f"Expected Document_ЧекККМ source, got {sales_data.get('source')!r}")

    orders = sales_data.get("orders", [])
    print(f"Fetched receipt lines: {len(orders)}")

    stats = Counter()
    skipped_examples = []
    touched_users = set()
    product_cache: Dict[str, Dict[str, Any]] = {}

    async with AsyncSessionLocal() as db:
        async with OneCCustomersService() as onec:
            for order in orders:
                raw = order.get("raw_1c_data") or {}
                customer_id = order.get("customer_id") or raw.get("Контрагент_Key")
                card_id = raw.get("ДисконтнаяКарта_Key")
                user = await resolve_or_create_user(db, onec, customer_id, card_id, create_missing)
                if not user:
                    stats["unresolved"] += 1
                    if len(skipped_examples) < 10:
                        skipped_examples.append({
                            "document": order.get("document_id"),
                            "date": order.get("date"),
                            "customer_id": customer_id,
                            "discount_card_id": card_id,
                            "amount": order.get("revenue"),
                        })
                    continue

                if dry_run:
                    stats["dry_run_matched"] += 1
                    touched_users.add(user.id)
                    continue

                status = await upsert_purchase(db, user, onec, order_to_purchase(order), product_cache)
                stats[status] += 1
                if status in {"created", "updated"}:
                    touched_users.add(user.id)

        if not dry_run:
            for user_id in touched_users:
                user = await db.get(User, user_id)
                if not user:
                    continue
                await recalculate_customer_metrics(db, user)
                await CustomerAnalyticsService(db).refresh_preferred_store_by_count(user_id, commit=False)
                user.synced_at = end_date
            await db.commit()
        else:
            await db.rollback()

    print(f"Stats: {dict(stats)}")
    print(f"Touched users: {len(touched_users)}")
    if skipped_examples:
        print("Unresolved examples:")
        for item in skipped_examples:
            print(item)
    return {
        "fetched": len(orders),
        "created": stats.get("created", 0),
        "updated": stats.get("updated", 0),
        "skipped": stats.get("skipped", 0),
        "unresolved": stats.get("unresolved", 0),
        "dry_run_matched": stats.get("dry_run_matched", 0),
        "touched_users": len(touched_users),
        "unresolved_examples": skipped_examples,
        "source": "Document_ЧекККМ",
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": days,
        },
    }


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Sync recent purchase_history from exact 1C receipts.")
    parser.add_argument("--days", type=int, default=2, help="How many recent days to sync.")
    parser.add_argument("--no-create-missing", action="store_true", help="Do not create users found in 1C receipts.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve and report without writing.")
    args = parser.parse_args()
    asyncio.run(sync_recent(args.days, not args.no_create_missing, args.dry_run))


if __name__ == "__main__":
    main()
