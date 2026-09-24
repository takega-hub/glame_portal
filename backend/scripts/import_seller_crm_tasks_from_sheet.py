#!/usr/bin/env python3
"""Import seller CRM tasks from the current GLAME Google Sheets CRM bridge.

Dry-run by default:
    PYTHONPATH=backend python backend/scripts/import_seller_crm_tasks_from_sheet.py

Apply to DB:
    PYTHONPATH=backend python backend/scripts/import_seller_crm_tasks_from_sheet.py --apply

The script fetches CSV export from the sheet, maps rows into the same
CrmTaskImportRequest used by `/api/admin/crm/tasks/import`, and therefore keeps
idempotency/source metadata consistent with the platform CRM module.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.connection import AsyncSessionLocal
from app.schemas.crm_tasks import CrmTaskImportRequest, CrmTaskImportRow
from app.services.crm_task_service import CrmTaskService

DEFAULT_SPREADSHEET_ID = "1v6Fz6N1qwrN78G8WTyA9YmX01VcddUWPTMGexiW9zMc"
DEFAULT_SHEET_NAME = "Звонки"
DEFAULT_CAMPAIGN_ID = "seller-crm-google-sheet"
REQUIRED_COLUMNS = {"Телефон", "CRM группа", "Дата отработки"}

STORE_NAME_MAP = {
    "меганом": "Мрия",
    "мрия": "Мрия",
    "glame мрия": "Мрия",
    "трк центрум": "ТРК Центрум",
    "центрум": "ТРК Центрум",
    "ялта": "Ялта, Набережная 18",
    "ялта, набережная 18": "Ялта, Набережная 18",
}

SELLER_NAME_MAP = {
    "бешлиева": "Бешлиева",
    "рогалевич": "Рогалевич",
    "ширинская": "Ширинская",
}


def clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def normalize_store_name(value: Any) -> str | None:
    text = clean(value)
    if not text:
        return None
    return STORE_NAME_MAP.get(text.lower(), text)


def normalize_seller_name(value: Any) -> str | None:
    text = clean(value)
    if not text:
        return None
    return SELLER_NAME_MAP.get(text.lower(), text)


def parse_date(value: Any, *, fallback: date | None = None) -> date:
    raw = str(value or "").strip()
    if not raw:
        return fallback or date.today()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")[:10]).date()
    except ValueError:
        return fallback or date.today()


STATUS_MAP = {
    "новая": "new",
    "новый": "new",
    "в работе": "in_progress",
    "позвонили": "worked",
    "проверено": "worked",
    "отработано": "worked",
    "проверено / отработано": "worked",
    "перенести": "postponed",
    "перенесено": "postponed",
    "неактуально": "not_relevant",
    "не беспокоить": "do_not_disturb",
    "жалоба на качество": "quality_complaint",
    "жалобы на качество": "quality_complaint",
    "качество": "quality_complaint",
    "закрыто": "closed",
}
VALID_STATUSES = {"new", "in_progress", "worked", "postponed", "not_relevant", "do_not_disturb", "quality_complaint", "closed"}

CRM_GROUP_MAP = {
    "a": "personal_call",
    "a. личный звонок": "personal_call",
    "личный звонок": "personal_call",
    "personal_call": "personal_call",
    "b": "personal_message",
    "b. личное сообщение": "personal_message",
    "личное сообщение": "personal_message",
    "personal_message": "personal_message",
    "c": "segmented_message",
    "c. сегментированное сообщение": "segmented_message",
    "сегментированное сообщение": "segmented_message",
    "segmented_message": "segmented_message",
    "d": "do_not_touch_review",
    "d. не трогать / проверить": "do_not_touch_review",
    "не трогать / проверить": "do_not_touch_review",
    "не трогать": "do_not_touch_review",
    "do_not_touch_review": "do_not_touch_review",
}
VALID_CRM_GROUPS = {"personal_call", "personal_message", "segmented_message", "do_not_touch_review"}

OUTCOME_MAP = {
    "не дозвонились": "no_answer",
    "отправлено, ответа нет": "sent_no_reply",
    "ответила": "replied",
    "попросила видео/фото": "requested_photo_video",
    "видео отправлено": "photo_video_sent",
    "продажа": "sale",
    "перенести": "postpone",
    "неактуально": "not_relevant",
    "не беспокоить": "do_not_disturb",
    "жалоба на качество": "quality_complaint",
    "жалобы на качество": "quality_complaint",
    "качество": "quality_complaint",
}
VALID_OUTCOMES = {
    "no_answer",
    "sent_no_reply",
    "replied",
    "requested_photo_video",
    "photo_video_sent",
    "sale",
    "postpone",
    "not_relevant",
    "do_not_disturb",
    "quality_complaint",
    "create_cdek",
}


def parse_priority(value: Any) -> int:
    raw = str(value or "").strip()
    try:
        priority = int(raw)
    except ValueError:
        return 3
    return max(1, min(priority, 5))


def normalize_status(value: Any) -> str:
    raw = str(value or "").strip()
    normalized = STATUS_MAP.get(raw.lower(), raw)
    return normalized if normalized in VALID_STATUSES else "new"


def normalize_outcome(value: Any) -> str | None:
    raw = str(value or "").strip()
    normalized = OUTCOME_MAP.get(raw.lower(), raw)
    return normalized if normalized in VALID_OUTCOMES else None


def normalize_crm_group(value: Any) -> str:
    raw = str(value or "").strip()
    normalized = CRM_GROUP_MAP.get(raw.lower(), raw)
    return normalized if normalized in VALID_CRM_GROUPS else "personal_message"


def build_csv_url(spreadsheet_id: str, sheet_name: str, data_range: str) -> str:
    query = f"tqx=out:csv&sheet={quote(sheet_name)}&range={quote(data_range)}"
    return f"https://docs.google.com/spreadsheets/d/{quote(spreadsheet_id)}/gviz/tq?{query}"


def fetch_csv(spreadsheet_id: str, sheet_name: str, data_range: str) -> str:
    req = Request(build_csv_url(spreadsheet_id, sheet_name, data_range), headers={"User-Agent": "glame-platform-seller-crm-import/1.0"})
    with urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8-sig")


def read_csv_matrix(csv_text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(csv_text)))


def fetch_sheet_rows(spreadsheet_id: str, sheet_name: str, max_rows: int, chunk_size: int) -> list[dict[str, str]]:
    header_matrix = read_csv_matrix(fetch_csv(spreadsheet_id, sheet_name, "A1:Z1"))
    if not header_matrix:
        return []
    headers = header_matrix[0]
    missing = REQUIRED_COLUMNS - set(headers)
    if missing:
        raise RuntimeError(f"Missing required columns: {', '.join(sorted(missing))}")

    rows: list[dict[str, str]] = []
    start = 2
    while start <= max_rows:
        end = min(max_rows, start + chunk_size - 1)
        matrix = read_csv_matrix(fetch_csv(spreadsheet_id, sheet_name, f"A{start}:Z{end}"))
        if not matrix:
            break
        non_empty = 0
        for idx, values in enumerate(matrix, start=start):
            padded = values + [""] * max(0, len(headers) - len(values))
            row = dict(zip(headers, padded[:len(headers)]))
            if any(clean(v) for v in row.values()):
                row["__row_number"] = str(idx)
                rows.append(row)
                non_empty += 1
        if non_empty == 0:
            break
        start = end + 1
    return rows


def row_to_import(row: dict[str, str]) -> CrmTaskImportRow | None:
    phone = clean(row.get("Телефон"))
    if not phone:
        return None
    row_number = clean(row.get("__row_number")) or "unknown"
    work_date = parse_date(row.get("Дата отработки"))
    next_action = clean(row.get("Дата следующего действия"))
    return CrmTaskImportRow(
        phone=phone,
        customer_name=clean(row.get("Имя")),
        seller_name=normalize_seller_name(row.get("Ответственный / чей клиент")),
        store_name=normalize_store_name(row.get("Магазин предпочтительный")) or normalize_store_name(row.get("Магазин")),
        work_date=work_date,
        priority=parse_priority(row.get("Приоритет")),
        crm_group=normalize_crm_group(row.get("CRM группа")),
        reason=clean(row.get("Причина сегмента")) or clean(row.get("CRM группа")),
        seller_action=clean(row.get("Что сделать продавцу")),
        script_key=clean(row.get("Ключ скрипта")),
        script_text=clean(row.get("Готовый текст / скрипт")),
        status=normalize_status(row.get("Статус работы")),
        seller_outcome=normalize_outcome(row.get("Итог продавца")),
        seller_comment=clean(row.get("Комментарий продавца")),
        next_action_date=parse_date(next_action) if next_action else None,
        source_row_id=row_number,
        source_payload={k: v for k, v in row.items() if not k.startswith("__")},
    )


async def import_sheet(args: argparse.Namespace) -> dict[str, Any]:
    rows = fetch_sheet_rows(args.spreadsheet_id, args.sheet_name, args.max_rows, args.chunk_size)
    import_rows = [item for row in rows if (item := row_to_import(row))]
    request = CrmTaskImportRequest(
        source="google_sheet_seller_crm",
        campaign_id=args.campaign_id,
        campaign_name=args.campaign_name,
        rows=import_rows,
    )
    if not args.apply:
        return {
            "sheet_rows": len(rows),
            "prepared_tasks": len(import_rows),
            "apply": False,
            "sample": [row.model_dump() for row in import_rows[:3]],
        }
    async with AsyncSessionLocal() as db:
        result = await CrmTaskService(db).import_tasks(request, actor=None)
    return result.model_dump()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import seller CRM tasks from Google Sheets.")
    parser.add_argument("--spreadsheet-id", default=DEFAULT_SPREADSHEET_ID)
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET_NAME)
    parser.add_argument("--campaign-id", default=DEFAULT_CAMPAIGN_ID)
    parser.add_argument("--campaign-name", default="Google Sheets CRM bridge")
    parser.add_argument("--max-rows", type=int, default=1500)
    parser.add_argument("--chunk-size", type=int, default=100)
    parser.add_argument("--apply", action="store_true", help="Write rows into crm_tasks.")
    return parser.parse_args()


def main() -> int:
    result = asyncio.run(import_sheet(parse_args()))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
