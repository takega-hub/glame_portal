#!/usr/bin/env python3
"""Import CRM call history from the Google Sheets `Звонки` tab.

Rows are matched to platform customers by normalized phone number and saved as
`customer_messages` records with `event_type=crm_call`.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import re
import sys
import uuid
from datetime import datetime, time, timezone
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.connection import AsyncSessionLocal
from app.models.customer_message import CustomerMessage
from app.models.user import User


DEFAULT_SPREADSHEET_ID = "1v6Fz6N1qwrN78G8WTyA9YmX01VcddUWPTMGexiW9zMc"
DEFAULT_SHEET_NAME = "Звонки"
SOURCE_NAMESPACE = uuid.UUID("070fe229-6627-459b-8cf2-ecf632e26f0d")

REQUIRED_COLUMNS = {
    "Дата отработки",
    "Статус работы",
    "Итог продавца",
    "Комментарий продавца",
    "CRM группа",
    "Ключ скрипта",
    "Готовый текст / скрипт",
    "Имя",
    "Телефон",
}


def normalize_phone(value: Any) -> str | None:
    digits = re.sub(r"\D+", "", str(value or ""))
    if not digits:
        return None
    if len(digits) >= 11 and digits[0] in {"7", "8"}:
        digits = "7" + digits[-10:]
    elif len(digits) == 10:
        digits = "7" + digits
    elif len(digits) > 11:
        digits = digits[:11]
    return digits if len(digits) == 11 else None


def parse_date(value: Any) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return datetime.now(timezone.utc)
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            d = datetime.strptime(raw, fmt).date()
            return datetime.combine(d, time(12, 0), tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value[:limit]


def build_csv_url(spreadsheet_id: str, sheet_name: str, data_range: str) -> str:
    query = f"tqx=out:csv&sheet={quote(sheet_name)}&range={quote(data_range)}"
    return f"https://docs.google.com/spreadsheets/d/{quote(spreadsheet_id)}/gviz/tq?{query}"


def fetch_csv(spreadsheet_id: str, sheet_name: str, data_range: str) -> str:
    req = Request(
        build_csv_url(spreadsheet_id, sheet_name, data_range),
        headers={"User-Agent": "glame-platform-crm-call-import/1.0"},
    )
    with urlopen(req, timeout=60) as resp:
        body = resp.read()
    return body.decode("utf-8-sig")


def read_csv_matrix(csv_text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(csv_text)))


def ensure_headers(headers: list[str]) -> None:
    if not headers:
        raise RuntimeError("Sheet header row is empty")
    missing = REQUIRED_COLUMNS - set(headers)
    if missing:
        raise RuntimeError(f"Missing required columns: {', '.join(sorted(missing))}")


def fetch_sheet_rows(spreadsheet_id: str, sheet_name: str, max_rows: int, chunk_size: int) -> list[dict[str, str]]:
    header_matrix = read_csv_matrix(fetch_csv(spreadsheet_id, sheet_name, "A1:Z1"))
    if not header_matrix:
        return []
    headers = header_matrix[0]
    ensure_headers(headers)

    rows: list[dict[str, str]] = []
    start = 2
    while start <= max_rows:
        end = min(max_rows, start + chunk_size - 1)
        matrix = read_csv_matrix(fetch_csv(spreadsheet_id, sheet_name, f"A{start}:Z{end}"))
        if not matrix:
            break
        non_empty_in_chunk = 0
        for values in matrix:
            padded = values + [""] * max(0, len(headers) - len(values))
            item = dict(zip(headers, padded[:len(headers)]))
            if any(clean(v) for v in item.values()):
                rows.append(item)
                non_empty_in_chunk += 1
        if non_empty_in_chunk == 0:
            break
        start = end + 1
    return rows


def build_message(row: dict[str, str]) -> str:
    reason = clean(row.get("Причина сегмента")) or clean(row.get("CRM группа")) or clean(row.get("Ключ скрипта")) or "CRM звонок"
    responsible = clean(row.get("Ответственный / чей клиент")) or clean(row.get("Кто создавал клиента")) or "не указан"
    comment = clean(row.get("Комментарий продавца")) or "без комментария"
    parts = [
        f"Повод: {reason}",
        f"Кто взаимодействовал: {responsible}",
        f"Комментарий: {comment}",
    ]
    outcome = clean(row.get("Итог продавца"))
    next_action = clean(row.get("Дата следующего действия"))
    if outcome:
        parts.append(f"Итог: {outcome}")
    if next_action:
        parts.append(f"Следующее действие: {next_action}")
    return ". ".join(parts)


async def load_customer_phone_map() -> tuple[dict[str, uuid.UUID], set[str]]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User.id, User.phone).where(User.is_customer == True, User.phone.isnot(None))
        )
    matches: dict[str, uuid.UUID] = {}
    duplicates: set[str] = set()
    for user_id, phone in result.all():
        normalized = normalize_phone(phone)
        if not normalized:
            continue
        if normalized in matches and matches[normalized] != user_id:
            duplicates.add(normalized)
            matches.pop(normalized, None)
        elif normalized not in duplicates:
            matches[normalized] = user_id
    return matches, duplicates


async def import_calls(args: argparse.Namespace) -> dict[str, Any]:
    rows = fetch_sheet_rows(args.spreadsheet_id, args.sheet_name, args.max_rows, args.chunk_size)
    phone_to_user_id, duplicate_phones = await load_customer_phone_map()

    prepared: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    invalid_phone = 0
    skipped_empty = 0

    for row_number, row in enumerate(rows, start=2):
        if not any(clean(v) for v in row.values()):
            skipped_empty += 1
            continue
        phone = normalize_phone(row.get("Телефон"))
        if not phone:
            invalid_phone += 1
            unmatched.append({"row": row_number, "name": clean(row.get("Имя")), "phone": row.get("Телефон"), "reason": "invalid_phone"})
            continue
        user_id = phone_to_user_id.get(phone)
        if not user_id:
            reason = "duplicate_phone_in_db" if phone in duplicate_phones else "not_found"
            unmatched.append({"row": row_number, "name": clean(row.get("Имя")), "phone": phone, "reason": reason})
            continue

        worked_at = parse_date(row.get("Дата отработки"))
        payload = {
            "message_kind": "crm_call",
            "source": "google_sheet_calls",
            "source_spreadsheet_id": args.spreadsheet_id,
            "source_sheet": args.sheet_name,
            "source_row": row_number,
            "interaction_date": worked_at.date().isoformat(),
            "interaction_reason": clean(row.get("Причина сегмента")) or clean(row.get("CRM группа")) or clean(row.get("Ключ скрипта")),
            "interacted_by": clean(row.get("Ответственный / чей клиент")) or clean(row.get("Кто создавал клиента")),
            "comment": clean(row.get("Комментарий продавца")),
            "worked_at": worked_at.isoformat(),
            "responsible": clean(row.get("Ответственный / чей клиент")),
            "customer_created_by": clean(row.get("Кто создавал клиента")),
            "work_status": clean(row.get("Статус работы")),
            "seller_outcome": clean(row.get("Итог продавца")),
            "next_action_date": clean(row.get("Дата следующего действия")),
            "seller_comment": clean(row.get("Комментарий продавца")),
            "crm_group": clean(row.get("CRM группа")),
            "priority": clean(row.get("Приоритет")),
            "segment_reason": clean(row.get("Причина сегмента")),
            "seller_task": clean(row.get("Что сделать продавцу")),
            "script_key": clean(row.get("Ключ скрипта")),
            "script_text": clean(row.get("Готовый текст / скрипт")),
            "sheet_customer_name": clean(row.get("Имя")),
            "sheet_phone": phone,
            "sheet_city": clean(row.get("Город")),
            "preferred_store": clean(row.get("Магазин предпочтительный")),
        }
        message_id = uuid.uuid5(SOURCE_NAMESPACE, f"{args.spreadsheet_id}:{args.sheet_name}:{row_number}:{phone}")
        prepared.append(
            {
                "id": message_id,
                "user_id": user_id,
                "message": build_message(row),
                "cta": truncate(payload["seller_task"], 255),
                "segment": truncate(clean(row.get("CRM группа")), 20),
                "event_type": "crm_call",
                "event_brand": truncate(payload["script_key"], 255),
                "event_store": truncate(payload["preferred_store"], 255),
                "payload": payload,
                "status": "sent",
                "sent_at": worked_at,
                "created_at": worked_at,
            }
        )

    if args.apply and prepared:
        async with AsyncSessionLocal() as db:
            stmt = pg_insert(CustomerMessage).values(prepared)
            update_cols = {
                "message": stmt.excluded.message,
                "cta": stmt.excluded.cta,
                "segment": stmt.excluded.segment,
                "event_type": stmt.excluded.event_type,
                "event_brand": stmt.excluded.event_brand,
                "event_store": stmt.excluded.event_store,
                "payload": stmt.excluded.payload,
                "status": stmt.excluded.status,
                "sent_at": stmt.excluded.sent_at,
                "created_at": stmt.excluded.created_at,
            }
            await db.execute(stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols))
            await db.commit()

    return {
        "sheet_rows": len(rows),
        "prepared": len(prepared),
        "applied": len(prepared) if args.apply else 0,
        "unmatched": len(unmatched),
        "invalid_phone": invalid_phone,
        "skipped_empty": skipped_empty,
        "sample_unmatched": unmatched[:20],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import customer CRM calls from Google Sheets.")
    parser.add_argument("--spreadsheet-id", default=DEFAULT_SPREADSHEET_ID)
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET_NAME)
    parser.add_argument("--max-rows", type=int, default=1500, help="Maximum sheet row number to scan.")
    parser.add_argument("--chunk-size", type=int, default=100, help="Rows to fetch per Google Sheets CSV request.")
    parser.add_argument("--apply", action="store_true", help="Write records to customer_messages.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = asyncio.run(import_calls(args))
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
