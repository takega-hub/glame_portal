#!/usr/bin/env python3
"""Reconcile SMS Aero history with customer_messages.

Matches by normalized phone and message text. Runs as dry-run by default.
"""
from __future__ import annotations

import argparse
import asyncio
import difflib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import text

from app.database.connection import AsyncSessionLocal
from app.models.customer_message import CustomerMessage
from app.services.sms_service import get_sms_service

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT.parent / ".env", override=False)
load_dotenv(ROOT / ".env", override=False)

STATUS_LABELS = {
    0: "В очереди",
    1: "Доставлено",
    2: "Не доставлено",
    3: "Передано оператору",
    6: "Отклонено",
    8: "На модерации",
}
STATUS_MAP = {
    0: "queued",
    1: "delivered",
    2: "failed",
    3: "sent",
    6: "failed",
    8: "moderation",
}


def normalize_phone(value: Any) -> str:
    digits = "".join(c for c in str(value or "") if c.isdigit())
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    return digits


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def sms_datetime(row: dict[str, Any]) -> datetime | None:
    raw = row.get("dateSend") or row.get("dateCreate")
    try:
        return datetime.fromtimestamp(int(raw), timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def delivery_payload(row: dict[str, Any]) -> dict[str, Any]:
    status_code = row.get("status")
    try:
        status_int = int(status_code)
    except (TypeError, ValueError):
        status_int = None
    return {
        "provider": "sms_aero",
        "sms_id": row.get("id"),
        "status": STATUS_MAP.get(status_int, "sent"),
        "status_code": status_int,
        "status_label": STATUS_LABELS.get(status_int) if status_int is not None else None,
        "extend_status": row.get("extendStatus"),
        "last_response": row,
        "last_checked_at": datetime.now(timezone.utc).isoformat(),
    }


async def fetch_sms_rows(max_pages: int) -> list[dict[str, Any]]:
    service = get_sms_service()
    if not service:
        raise RuntimeError("SMS Aero is not configured")

    rows: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        response = await service.list_sms(page=page)
        data = response.get("data") if isinstance(response, dict) else {}
        if not isinstance(data, dict):
            break
        page_rows = [value for key, value in data.items() if str(key).isdigit() and isinstance(value, dict)]
        rows.extend(page_rows)
        total = int(data.get("totalCount") or len(rows))
        if len(rows) >= total or not page_rows:
            break
    return rows


async def reconcile(max_pages: int, threshold: float, apply: bool) -> dict[str, Any]:
    sms_rows = await fetch_sms_rows(max_pages=max_pages)
    matched = 0
    updated = 0
    unmatched: list[dict[str, Any]] = []

    async with AsyncSessionLocal() as db:
        for sms in sms_rows:
            phone = normalize_phone(sms.get("number"))
            sms_text = normalize_text(sms.get("text"))
            candidates = (
                await db.execute(
                    text(
                        """
                        select cm.id, cm.message
                        from customer_messages cm
                        join users u on u.id = cm.user_id
                        where regexp_replace(coalesce(u.phone,''), '\\D', '', 'g') in (:phone, :phone8, :phone10)
                        order by cm.created_at desc
                        limit 50
                        """
                    ),
                    {
                        "phone": phone,
                        "phone8": "8" + phone[1:] if phone.startswith("7") else phone,
                        "phone10": phone[1:] if phone.startswith("7") else phone,
                    },
                )
            ).all()

            best_id = None
            best_score = 0.0
            for row in candidates:
                score = difflib.SequenceMatcher(None, sms_text, normalize_text(row.message)).ratio()
                if score > best_score:
                    best_score = score
                    best_id = row.id

            if not best_id or best_score < threshold:
                unmatched.append(
                    {
                        "sms_id": sms.get("id"),
                        "number": phone,
                        "status": sms.get("status"),
                        "extendStatus": sms.get("extendStatus"),
                        "date": sms_datetime(sms).isoformat() if sms_datetime(sms) else None,
                        "text_preview": str(sms.get("text") or "")[:120],
                        "best_score": round(best_score, 3),
                    }
                )
                continue

            matched += 1
            if apply:
                msg = await db.get(CustomerMessage, best_id)
                if msg:
                    payload = dict(msg.payload or {})
                    payload["sms_id"] = sms.get("id")
                    payload["sms_delivery"] = delivery_payload(sms)
                    msg.payload = payload
                    msg.status = payload["sms_delivery"]["status"]
                    if sms_datetime(sms):
                        msg.sent_at = sms_datetime(sms)
                    updated += 1

        if apply:
            await db.commit()
        else:
            await db.rollback()

    return {
        "sms_rows": len(sms_rows),
        "matched": matched,
        "updated": updated,
        "unmatched": unmatched,
        "applied": apply,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--threshold", type=float, default=0.92)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = asyncio.run(reconcile(args.max_pages, args.threshold, args.apply))
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
