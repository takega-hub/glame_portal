#!/usr/bin/env python3
"""Sync platform staff store assignments from 1C employee register.

1C Catalog_Сотрудники does not publish the store field in this database. The current
employee structural unit comes from InformationRegister_Сотрудники_RecordType:
Сотрудник_Key -> СтруктурнаяЕдиница_Key. GLAME store external_id values match those
structural unit keys, so this script updates users.preferences with canonical store
bindings used by manager-scoped KPI pages.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT / "backend"))

from app.database.connection import AsyncSessionLocal  # noqa: E402
from app.models.store import Store  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.onec_sellers_service import OneCSellersService  # noqa: E402
from app.services.seller_kpi_service import SellerKPIService  # noqa: E402


STAFF_ROLES = {"seller", "manager", "admin"}
MANAGER_ROLES = {"manager"}
MANAGER_POSITION_MARKERS = ("управля",)


def _prefs(user: User) -> dict[str, Any]:
    preferences = getattr(user, "preferences", None)
    return dict(preferences) if isinstance(preferences, dict) else {}


def _employee_ids(user: User) -> set[str]:
    preferences = _prefs(user)
    ids = {
        str(preferences.get("seller_external_id") or "").strip(),
        str(preferences.get("onec_seller_id") or "").strip(),
        str(preferences.get("employee_external_id") or "").strip(),
        str(preferences.get("onec_seller_external_id") or "").strip(),
    }
    for value in preferences.get("seller_external_ids") or []:
        ids.add(str(value or "").strip())
    ids.discard("")
    ids.discard("00000000-0000-0000-0000-000000000000")
    return ids


def _unique_store_names(names: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for name in names:
        canonical = SellerKPIService._canonical_store_name(name)
        key = SellerKPIService._normalize_store_name(canonical)
        if canonical and key not in seen:
            seen.add(key)
            result.append(canonical)
    return result


def _unique_store_ids(ids: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in ids:
        store_id = str(value or "").strip()
        if store_id and store_id not in seen:
            seen.add(store_id)
            result.append(store_id)
    return result


def _is_manager_position(position_name: str | None) -> bool:
    normalized = " ".join((position_name or "").strip().lower().replace("ё", "е").split())
    return any(marker in normalized for marker in MANAGER_POSITION_MARKERS)


async def sync_staff_store_assignments(*, apply: bool = False, limit: int = 1000) -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / "backend" / ".env")

    async with OneCSellersService() as service:
        result = await service.fetch_staff_store_assignments(limit=limit)
        position_rows = await service.fetch_from_endpoint("/Catalog_Должности", limit=1000)

    assignments = {
        item["employee_external_id"]: item
        for item in result.get("assignments") or []
        if item.get("employee_external_id") and item.get("store_external_id")
    }
    position_name_by_id = {
        str(row.get("Ref_Key") or "").strip(): str(row.get("Description") or row.get("НаименованиеКраткое") or "").strip()
        for row in position_rows
        if row.get("Ref_Key")
    }
    touched: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    async with AsyncSessionLocal() as db:
        stores = (await db.execute(select(Store))).scalars().all()
        store_by_external_id = {str(store.external_id): store for store in stores if getattr(store, "external_id", None)}
        store_by_canonical_name = {
            SellerKPIService._normalize_store_name(SellerKPIService._canonical_store_name(store.name) or store.name): store
            for store in stores
            if store.name
        }

        users = (await db.execute(
            select(User)
            .where(User.is_customer.is_(False))
            .where(User.role.in_(STAFF_ROLES))
            .order_by(User.full_name.asc().nullslast(), User.email.asc().nullslast())
        )).scalars().all()

        for user in users:
            ids = _employee_ids(user)
            assignment = next((assignments[external_id] for external_id in ids if external_id in assignments), None)
            if not assignment:
                skipped.append({"user_id": str(user.id), "full_name": user.full_name, "reason": "no_1c_assignment"})
                continue

            store = store_by_external_id.get(str(assignment["store_external_id"]))
            if not store:
                skipped.append({
                    "user_id": str(user.id),
                    "full_name": user.full_name,
                    "reason": "store_not_found",
                    "store_external_id": assignment["store_external_id"],
                })
                continue

            canonical_name = SellerKPIService._canonical_store_name(store.name) or store.name
            preferences = _prefs(user)
            user_is_manager = (user.role or "").lower() in MANAGER_ROLES
            position_name = position_name_by_id.get(str(assignment.get("position_external_id") or "").strip())
            assignment_is_manager = _is_manager_position(position_name)
            preferred_manager_store_name = SellerKPIService._canonical_store_name(preferences.get("staff_store"))
            preferred_manager_store = store_by_canonical_name.get(SellerKPIService._normalize_store_name(preferred_manager_store_name))
            before = {
                "staff_store_external_id": preferences.get("staff_store_external_id"),
                "staff_store_name": preferences.get("staff_store_name"),
                "managed_store_external_ids": preferences.get("managed_store_external_ids"),
                "managed_store_names": preferences.get("managed_store_names"),
            }
            if user_is_manager and not assignment_is_manager and preferred_manager_store_name and preferred_manager_store:
                preferences.update({
                    "staff_store_external_id": str(preferred_manager_store.external_id),
                    "staff_store_name": preferred_manager_store_name,
                    "staff_store_assignment_source": "platform_staff_store",
                    "staff_store_assignment_position": position_name,
                    "staff_store_assignment_synced_at": now,
                })
            elif not user_is_manager or assignment_is_manager:
                preferences.update({
                    "staff_store_external_id": str(store.external_id),
                    "staff_store_name": canonical_name,
                    "staff_store_assignment_source": result.get("endpoint"),
                    "staff_store_assignment_period": assignment.get("period"),
                    "staff_store_assignment_position": position_name,
                    "staff_store_assignment_synced_at": now,
                })
            if user_is_manager:
                existing_names = preferences.get("managed_store_names") if isinstance(preferences.get("managed_store_names"), list) else []
                existing_ids = preferences.get("managed_store_external_ids") if isinstance(preferences.get("managed_store_external_ids"), list) else []
                names = [*existing_names] if assignment_is_manager else []
                ids = [*existing_ids] if assignment_is_manager else []
                if preferred_manager_store_name and preferred_manager_store:
                    names.insert(0, preferred_manager_store_name)
                    ids.insert(0, str(preferred_manager_store.external_id))
                if assignment_is_manager:
                    names.append(canonical_name)
                    ids.append(str(store.external_id))
                preferences["managed_store_external_ids"] = _unique_store_ids(ids)
                preferences["managed_store_names"] = _unique_store_names(names)
                preferences["managed_store_source"] = result.get("endpoint") if assignment_is_manager else "platform_staff_store"
                preferences["managed_store_synced_at"] = now

            after = {
                "staff_store_external_id": preferences.get("staff_store_external_id"),
                "staff_store_name": preferences.get("staff_store_name"),
                "managed_store_external_ids": preferences.get("managed_store_external_ids"),
                "managed_store_names": preferences.get("managed_store_names"),
            }
            if before == after:
                continue
            touched.append({
                "user_id": str(user.id),
                "full_name": user.full_name,
                "role": user.role,
                "before": before,
                "after": after,
            })
            if apply:
                user.preferences = preferences

        if apply:
            await db.commit()
        else:
            await db.rollback()

    return {
        "dry_run": not apply,
        "source_endpoint": result.get("endpoint"),
        "source_loaded": result.get("total_loaded"),
        "source_assignments": result.get("count"),
        "updated": len(touched),
        "skipped": len(skipped),
        "changes": touched,
        "skipped_examples": skipped[:20],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes to users.preferences")
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()
    result = asyncio.run(sync_staff_store_assignments(apply=args.apply, limit=args.limit))
    import json

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
