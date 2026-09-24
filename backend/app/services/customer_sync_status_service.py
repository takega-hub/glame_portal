"""Persistent status markers for customer sync jobs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting


FULL_CUSTOMER_SYNC_SETTING_KEY = "last_successful_full_customer_sync"


async def mark_successful_full_customer_sync(
    db: AsyncSession,
    *,
    source: str,
    task_id: str | None = None,
    stats: dict[str, Any] | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    completed_at = datetime.now(timezone.utc)
    payload = {
        "completed_at": completed_at.isoformat(),
        "source": source,
        "task_id": task_id,
        "stats": stats or {},
    }

    row = (
        await db.execute(
            select(AppSetting).where(AppSetting.key == FULL_CUSTOMER_SYNC_SETTING_KEY)
        )
    ).scalar_one_or_none()
    if row:
        row.value = json.dumps(payload, ensure_ascii=False)
    else:
        db.add(
            AppSetting(
                key=FULL_CUSTOMER_SYNC_SETTING_KEY,
                value=json.dumps(payload, ensure_ascii=False),
            )
        )

    if commit:
        await db.commit()

    return payload


async def get_successful_full_customer_sync(db: AsyncSession) -> dict[str, Any] | None:
    row = (
        await db.execute(
            select(AppSetting).where(AppSetting.key == FULL_CUSTOMER_SYNC_SETTING_KEY)
        )
    ).scalar_one_or_none()
    if not row or not row.value:
        return None

    try:
        payload = json.loads(row.value)
    except json.JSONDecodeError:
        payload = {"completed_at": row.value}

    if row.updated_at:
        payload["updated_at"] = row.updated_at.isoformat()
    return payload
