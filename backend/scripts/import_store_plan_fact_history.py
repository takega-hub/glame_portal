#!/usr/bin/env python3
"""Import GLAME ЕО monthly store plan/fact Excel files into historical KPI tables.

This script intentionally uses Python stdlib for XLSX parsing (zipfile + XML) so it
works in the Hermes container without pandas/openpyxl. It stores:
- file/sheet provenance
- normalized store KPI target/fact rows
- daily fact rows from the main store sheet
- summary rows from Сводная / Св. по пок.
- schedule/raw rows from График
- raw rows for every parsed sheet (for future reprocessing)

It also upserts historical store plan values into seller_kpi_target_plans so the
existing KPI page can show plan values for imported past periods.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IMPORT_ROOT = ROOT / "data" / "imports" / "plan_fact"
REPORT_DIR = ROOT / "reports" / "plan_fact_import_preview"

NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

STORE_DIRS = {
    "yalta": "Ялта, Набережная 18",
    "centrum": "ТРК Центрум",
}

STORE_SHEET_HINTS = {
    "yalta": ("ялта", "ленина", "набереж"),
    "centrum": ("центрум", "трк"),
}

TARGET_METRIC_KEYS = {
    "revenue", "items_count", "avg_check", "avg_item_price", "items_per_check",
    "checks_count", "shifts_count", "avg_sales_per_shift", "lag_lead", "traffic",
    "revenue_per_visitor", "conversion",
}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def database_url() -> str:
    load_env_file(ROOT / ".env")
    load_env_file(ROOT / "backend" / ".env")
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        host = os.environ.get("DB_HOST", "localhost")
        port = os.environ.get("DB_PORT", "5433")
        user = os.environ.get("DB_USER", "glame_user")
        password = os.environ.get("DB_PASSWORD", "glame_password")
        name = os.environ.get("DB_NAME", "glame_db")
        raw = f"postgresql://{user}:{password}@{host}:{port}/{name}"
    raw = raw.replace("postgresql+psycopg://", "postgresql://", 1).replace("postgresql+asyncpg://", "postgresql://", 1)
    # Same docker bridge adjustment as backend connection.py.
    try:
        p = urlparse(raw)
        if p.hostname in {"localhost", "127.0.0.1"} and (p.port is None or p.port == 5432):
            netloc = p.netloc
            if "@" in netloc:
                creds, hostpart = netloc.split("@", 1)
                host_only = hostpart.split(":", 1)[0]
                netloc = f"{creds}@{host_only}:5433"
            else:
                host_only = netloc.split(":", 1)[0]
                netloc = f"{host_only}:5433"
            raw = urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))
    except Exception:
        pass
    return raw


def col_to_idx(ref: str) -> int:
    letters = "".join(ch for ch in ref if ch.isalpha())
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch.upper()) - 64
    return n


def excel_date(value: Any) -> str | None:
    try:
        return (datetime(1899, 12, 30) + timedelta(days=float(value))).date().isoformat()
    except Exception:
        return None


def num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    s = str(value).replace("\xa0", " ").strip().replace(" ", "").replace(",", ".")
    if s in {"#VALUE!", "#DIV/0!", "#REF!", "#N/A"}:
        return None
    try:
        return float(s)
    except Exception:
        return None


def decimal_or_none(value: Any) -> Decimal | None:
    n = num(value)
    if n is None:
        return None
    try:
        return Decimal(str(n))
    except InvalidOperation:
        return None


def cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    typ = cell.attrib.get("t")
    if typ == "inlineStr":
        return "".join((t.text or "") for t in cell.findall(".//" + NS_MAIN + "t")).strip()
    v = cell.find(NS_MAIN + "v")
    if v is not None:
        raw = v.text or ""
        if typ == "s" and raw.isdigit() and int(raw) < len(shared_strings):
            return shared_strings[int(raw)].strip()
        return raw.strip()
    f = cell.find(NS_MAIN + "f")
    return "=" + (f.text or "") if f is not None else ""


def read_xlsx(path: Path) -> dict[str, list[dict[int, str]]]:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(NS_MAIN + "si"):
                shared_strings.append("".join((t.text or "") for t in si.findall(".//" + NS_MAIN + "t")))
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rid_target = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
        sheets: dict[str, list[dict[int, str]]] = {}
        for sh in wb.findall(".//" + NS_MAIN + "sheet"):
            sheet_name = sh.attrib.get("name") or "Sheet"
            rid = sh.attrib.get(NS_REL + "id")
            if not rid:
                continue
            target = rid_target[rid]
            sheet_path = "xl/" + target.lstrip("/") if not target.startswith("xl/") else target
            root = ET.fromstring(z.read(sheet_path))
            rows: list[dict[int, str]] = []
            for row in root.findall(".//" + NS_MAIN + "row"):
                vals: dict[int, str] = {}
                for cell in row.findall(NS_MAIN + "c"):
                    value = cell_value(cell, shared_strings)
                    if value not in ("", None):
                        vals[col_to_idx(cell.attrib.get("r", ""))] = value
                if vals:
                    rows.append(vals)
            sheets[sheet_name] = rows
        return sheets


def norm_metric(label: Any) -> str | None:
    l = str(label or "").lower().replace("ё", "е")
    if ("выруч" in l and "вошед" in l) or "на вошедшего" in l:
        return "revenue_per_visitor"
    if "выруч" in l or "оборот" in l or "продажи" == l.strip():
        return "revenue"
    if "кол-во изделий" in l or "количество изделий" in l:
        return "items_count"
    if "средний чек" in l:
        return "avg_check"
    if "средняя стоимость" in l:
        return "avg_item_price"
    if "длина чека" in l or "изделий в чеке" in l:
        return "items_per_check"
    if "кол-во чек" in l or "количество чек" in l or l.strip() == "чеки":
        return "checks_count"
    if "кол-во смен" in l or l.strip() == "смены":
        return "shifts_count"
    if "средние продажи" in l:
        return "avg_sales_per_shift"
    if "отставание" in l or "перевыполнение" in l or "отклонение от плана" in l:
        return "lag_lead"
    if "трафик" in l or "вошедш" in l:
        return "traffic"
    if "конверсия" in l:
        return "conversion"
    return None


def row_text(row: dict[int, str]) -> str:
    return " ".join(str(v) for v in row.values())


def period_from_filename(name: str, store_slug: str) -> str | None:
    lower = name.lower()
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", name)
    if m:
        _day, month, year = m.groups()
        return f"{year}-{month}"
    m = re.search(r"_(\d{2})\.(\d{4})", name)
    if m:
        month, year = m.groups()
        return f"{year}-{month}"
    m = re.search(r"\s(\d{2})\.(\d{4})", name)
    if m:
        month, year = m.groups()
        return f"{year}-{month}"
    if "декабр" in lower:
        return "2025-12"
    return None


def detect_period(rows: list[dict[int, str]], file_name: str, store_slug: str) -> str | None:
    by_name = period_from_filename(file_name, store_slug)
    if by_name:
        return by_name
    dates: list[str] = []
    started = False
    for row in rows:
        txt = row_text(row).lower()
        if "сотрудник" in txt and "дата" in txt and "выруч" in txt:
            started = True
            continue
        if started:
            d = num(row.get(2))
            if d and 45000 < d < 47000:
                ed = excel_date(d)
                if ed:
                    dates.append(ed[:7])
    if dates:
        counts = {month: dates.count(month) for month in set(dates)}
        return max(counts, key=counts.get)
    return None


def parse_metric_rows(rows: list[dict[int, str]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    header_i: int | None = None
    for i, row in enumerate(rows):
        txt = row_text(row).lower()
        if "показатель" in txt and "план" in txt and "факт" in txt:
            header_i = i
            break
    if header_i is None:
        return [], {}
    header = rows[header_i]
    cols: dict[str, int] = {}
    for c, v in header.items():
        vl = str(v).lower().strip()
        if vl == "показатель":
            cols["label"] = c
        elif vl == "план":
            cols["plan"] = c
        elif vl == "факт":
            cols["fact"] = c
        elif vl == "% выполнения":
            cols["percent"] = c
        elif vl == "прогноз выполнения":
            cols["forecast"] = c
        elif vl == "% выполнения по прогнозу":
            cols["forecast_percent"] = c
        elif vl == "отклонение":
            cols["deviation"] = c
        elif "аналогичного месяца" in vl:
            cols["last_year_fact"] = c
        elif "lfl" in vl:
            cols["lfl_deviation"] = c
    parsed: list[dict[str, Any]] = []
    for idx, row in enumerate(rows[header_i + 1:], start=header_i + 2):
        if "Факт продаж за месяц" in row_text(row):
            break
        label = row.get(cols.get("label", -1))
        key = norm_metric(label)
        if not key:
            continue
        item = {
            "row_number": idx,
            "metric_key": key,
            "metric_label": label,
            "plan_value": decimal_or_none(row.get(cols.get("plan", -1))),
            "fact_value": decimal_or_none(row.get(cols.get("fact", -1))),
            "completion_percent": decimal_or_none(row.get(cols.get("percent", -1))),
            "forecast_value": decimal_or_none(row.get(cols.get("forecast", -1))),
            "forecast_percent": decimal_or_none(row.get(cols.get("forecast_percent", -1))),
            "deviation_value": decimal_or_none(row.get(cols.get("deviation", -1))),
            "last_year_fact_value": decimal_or_none(row.get(cols.get("last_year_fact", -1))),
            "lfl_deviation_value": decimal_or_none(row.get(cols.get("lfl_deviation", -1))),
            "raw_row": row,
        }
        parsed.append(item)
    return parsed, cols


def choose_main_sheet(sheets: dict[str, list[dict[int, str]]], store_slug: str) -> tuple[str, list[dict[str, Any]]]:
    hints = STORE_SHEET_HINTS.get(store_slug, ())
    best_name = ""
    best_metrics: list[dict[str, Any]] = []
    for name, rows in sheets.items():
        metrics, _ = parse_metric_rows(rows)
        lname = name.lower()
        score = len(metrics) + (20 if any(h in lname for h in hints) else 0)
        if score > len(best_metrics) + (20 if best_name and any(h in best_name.lower() for h in hints) else 0):
            best_name, best_metrics = name, metrics
    return best_name or next(iter(sheets)), best_metrics


def parse_daily_rows(rows: list[dict[int, str]]) -> list[dict[str, Any]]:
    header: dict[int, str] | None = None
    out: list[dict[str, Any]] = []
    for row in rows:
        txt = row_text(row).lower()
        if header is None and "сотрудник" in txt and "дата" in txt and "выруч" in txt:
            header = row
            continue
        if header is None:
            continue
        # stop at next section-like row with no date and no numeric daily values
        date_serial = num(row.get(2))
        if not date_serial:
            continue
        sale_date = excel_date(date_serial)
        values = {str(header.get(c, f"col_{c}")): v for c, v in row.items()}
        out.append({
            "sale_date": sale_date,
            "seller_names": row.get(1),
            "weekday": row.get(3),
            "revenue": decimal_or_none(row.get(4)),
            "items_count": decimal_or_none(row.get(5)),
            "avg_item_price": decimal_or_none(row.get(6)),
            "checks_count": decimal_or_none(row.get(7)),
            "avg_check": decimal_or_none(row.get(8)),
            "traffic": decimal_or_none(row.get(9)),
            "items_per_check": decimal_or_none(row.get(10)),
            "conversion": decimal_or_none(row.get(14)) if row.get(14) is not None else None,
            "raw_row": values,
        })
    return out


def parse_summary_rows(sheet_name: str, rows: list[dict[int, str]]) -> list[dict[str, Any]]:
    if not any(k in sheet_name.lower() for k in ["свод", "св. по пок"]):
        return []
    out: list[dict[str, Any]] = []
    context_headers: dict[int, str] = {}
    for i, row in enumerate(rows, start=1):
        first = row.get(1)
        if first and str(first).strip().lower() == "показатель":
            context_headers = {c: v for c, v in row.items() if c > 1}
            continue
        key = norm_metric(first)
        if not key:
            continue
        out.append({"row_number": i, "metric_key": key, "metric_label": first, "headers": context_headers, "raw_row": row})
    return out


def parse_schedule_rows(sheet_name: str, rows: list[dict[int, str]]) -> list[dict[str, Any]]:
    if "график" not in sheet_name.lower():
        return []
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=1):
        if not row:
            continue
        out.append({"row_number": i, "raw_row": row})
    return out


def json_dumps(value: Any) -> str:
    def default(o: Any) -> Any:
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        return str(o)
    return json.dumps(value, ensure_ascii=False, default=default)


def create_tables(conn: psycopg.Connection) -> None:
    stmts = [
        """
        CREATE TABLE IF NOT EXISTS seller_kpi_store_plan_fact_imports (
            id UUID PRIMARY KEY,
            store_name TEXT NOT NULL,
            store_slug TEXT NOT NULL,
            period_month DATE NOT NULL,
            source_file TEXT NOT NULL,
            source_archive TEXT NULL,
            source_sheet TEXT NULL,
            source_hash TEXT NOT NULL,
            import_status TEXT NOT NULL DEFAULT 'parsed',
            raw_metadata JSONB NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NULL,
            UNIQUE (store_name, period_month, source_hash)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS seller_kpi_store_plan_fact_rows (
            id UUID PRIMARY KEY,
            import_id UUID NOT NULL REFERENCES seller_kpi_store_plan_fact_imports(id) ON DELETE CASCADE,
            store_name TEXT NOT NULL,
            period_month DATE NOT NULL,
            metric_key TEXT NOT NULL,
            metric_label TEXT NULL,
            plan_value NUMERIC(18, 6) NULL,
            fact_value NUMERIC(18, 6) NULL,
            completion_percent NUMERIC(10, 4) NULL,
            forecast_value NUMERIC(18, 6) NULL,
            forecast_percent NUMERIC(10, 4) NULL,
            deviation_value NUMERIC(18, 6) NULL,
            last_year_fact_value NUMERIC(18, 6) NULL,
            lfl_deviation_value NUMERIC(18, 6) NULL,
            raw_row JSONB NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (store_name, period_month, metric_key, import_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS seller_kpi_store_plan_fact_daily_rows (
            id UUID PRIMARY KEY,
            import_id UUID NOT NULL REFERENCES seller_kpi_store_plan_fact_imports(id) ON DELETE CASCADE,
            store_name TEXT NOT NULL,
            period_month DATE NOT NULL,
            sale_date DATE NULL,
            seller_names TEXT NULL,
            weekday TEXT NULL,
            revenue NUMERIC(18, 6) NULL,
            items_count NUMERIC(18, 6) NULL,
            avg_item_price NUMERIC(18, 6) NULL,
            checks_count NUMERIC(18, 6) NULL,
            avg_check NUMERIC(18, 6) NULL,
            traffic NUMERIC(18, 6) NULL,
            items_per_check NUMERIC(18, 6) NULL,
            conversion NUMERIC(18, 6) NULL,
            raw_row JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (import_id, sale_date, seller_names, raw_row)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS seller_kpi_store_plan_fact_summary_rows (
            id UUID PRIMARY KEY,
            import_id UUID NOT NULL REFERENCES seller_kpi_store_plan_fact_imports(id) ON DELETE CASCADE,
            store_name TEXT NOT NULL,
            period_month DATE NOT NULL,
            source_sheet TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            metric_key TEXT NULL,
            metric_label TEXT NULL,
            headers JSONB NULL,
            raw_row JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (import_id, source_sheet, row_number)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS seller_kpi_store_plan_fact_schedule_rows (
            id UUID PRIMARY KEY,
            import_id UUID NOT NULL REFERENCES seller_kpi_store_plan_fact_imports(id) ON DELETE CASCADE,
            store_name TEXT NOT NULL,
            period_month DATE NOT NULL,
            source_sheet TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            raw_row JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (import_id, source_sheet, row_number)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS seller_kpi_store_plan_fact_sheet_rows (
            id UUID PRIMARY KEY,
            import_id UUID NOT NULL REFERENCES seller_kpi_store_plan_fact_imports(id) ON DELETE CASCADE,
            store_name TEXT NOT NULL,
            period_month DATE NOT NULL,
            source_sheet TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            raw_row JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (import_id, source_sheet, row_number)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_seller_kpi_plan_fact_rows_lookup ON seller_kpi_store_plan_fact_rows(store_name, period_month, metric_key)",
        "CREATE INDEX IF NOT EXISTS ix_seller_kpi_plan_fact_imports_period ON seller_kpi_store_plan_fact_imports(store_name, period_month)",
        "CREATE INDEX IF NOT EXISTS ix_seller_kpi_plan_fact_daily_period ON seller_kpi_store_plan_fact_daily_rows(store_name, period_month, sale_date)",
    ]
    with conn.cursor() as cur:
        for stmt in stmts:
            cur.execute(stmt)
    conn.commit()


def period_date(period: str) -> date:
    return datetime.strptime(period[:7], "%Y-%m").date().replace(day=1)


def upsert_import(conn: psycopg.Connection, *, store_slug: str, store_name: str, period: str, path: Path, main_sheet: str, sheets: dict[str, list[dict[int, str]]], sha: str, metrics_count: int) -> str:
    metadata = {
        "source_path": str(path),
        "file_size": path.stat().st_size,
        "sheets": list(sheets.keys()),
        "metrics_count": metrics_count,
        "parser": "backend/scripts/import_store_plan_fact_history.py",
    }
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO seller_kpi_store_plan_fact_imports
                (id, store_name, store_slug, period_month, source_file, source_sheet, source_hash, import_status, raw_metadata, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'parsed', %s::jsonb, NOW())
            ON CONFLICT (store_name, period_month, source_hash)
            DO UPDATE SET source_file=EXCLUDED.source_file, source_sheet=EXCLUDED.source_sheet,
                          import_status='parsed', raw_metadata=EXCLUDED.raw_metadata, updated_at=NOW()
            RETURNING id::text
            """,
            (str(uuid4()), store_name, store_slug, period_date(period), path.name, main_sheet, sha, json_dumps(metadata)),
        )
        return cur.fetchone()["id"]


def clear_import_children(conn: psycopg.Connection, import_id: str) -> None:
    with conn.cursor() as cur:
        for table in [
            "seller_kpi_store_plan_fact_rows",
            "seller_kpi_store_plan_fact_daily_rows",
            "seller_kpi_store_plan_fact_summary_rows",
            "seller_kpi_store_plan_fact_schedule_rows",
            "seller_kpi_store_plan_fact_sheet_rows",
        ]:
            cur.execute(f"DELETE FROM {table} WHERE import_id = %s", (import_id,))


def insert_rows(conn: psycopg.Connection, import_id: str, store_name: str, period: str, metrics: list[dict[str, Any]], daily: list[dict[str, Any]], summary: list[dict[str, Any]], schedule: list[dict[str, Any]], raw_rows: list[dict[str, Any]]) -> None:
    pdate = period_date(period)
    with conn.cursor() as cur:
        for r in metrics:
            cur.execute(
                """
                INSERT INTO seller_kpi_store_plan_fact_rows
                (id, import_id, store_name, period_month, metric_key, metric_label, plan_value, fact_value,
                 completion_percent, forecast_value, forecast_percent, deviation_value, last_year_fact_value,
                 lfl_deviation_value, raw_row)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (store_name, period_month, metric_key, import_id) DO UPDATE SET
                    metric_label=EXCLUDED.metric_label,
                    plan_value=EXCLUDED.plan_value,
                    fact_value=EXCLUDED.fact_value,
                    completion_percent=EXCLUDED.completion_percent,
                    forecast_value=EXCLUDED.forecast_value,
                    forecast_percent=EXCLUDED.forecast_percent,
                    deviation_value=EXCLUDED.deviation_value,
                    last_year_fact_value=EXCLUDED.last_year_fact_value,
                    lfl_deviation_value=EXCLUDED.lfl_deviation_value,
                    raw_row=EXCLUDED.raw_row
                """,
                (str(uuid4()), import_id, store_name, pdate, r["metric_key"], r.get("metric_label"), r.get("plan_value"), r.get("fact_value"), r.get("completion_percent"), r.get("forecast_value"), r.get("forecast_percent"), r.get("deviation_value"), r.get("last_year_fact_value"), r.get("lfl_deviation_value"), json_dumps(r.get("raw_row"))),
            )
        for r in daily:
            cur.execute(
                """
                INSERT INTO seller_kpi_store_plan_fact_daily_rows
                (id, import_id, store_name, period_month, sale_date, seller_names, weekday, revenue, items_count,
                 avg_item_price, checks_count, avg_check, traffic, items_per_check, conversion, raw_row)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (import_id, sale_date, seller_names, raw_row) DO NOTHING
                """,
                (str(uuid4()), import_id, store_name, pdate, r.get("sale_date"), r.get("seller_names"), r.get("weekday"), r.get("revenue"), r.get("items_count"), r.get("avg_item_price"), r.get("checks_count"), r.get("avg_check"), r.get("traffic"), r.get("items_per_check"), r.get("conversion"), json_dumps(r.get("raw_row"))),
            )
        for r in summary:
            cur.execute(
                """
                INSERT INTO seller_kpi_store_plan_fact_summary_rows
                (id, import_id, store_name, period_month, source_sheet, row_number, metric_key, metric_label, headers, raw_row)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT (import_id, source_sheet, row_number) DO UPDATE SET
                    metric_key=EXCLUDED.metric_key, metric_label=EXCLUDED.metric_label,
                    headers=EXCLUDED.headers, raw_row=EXCLUDED.raw_row
                """,
                (str(uuid4()), import_id, store_name, pdate, r["source_sheet"], r["row_number"], r.get("metric_key"), r.get("metric_label"), json_dumps(r.get("headers")), json_dumps(r.get("raw_row"))),
            )
        for r in schedule:
            cur.execute(
                """
                INSERT INTO seller_kpi_store_plan_fact_schedule_rows
                (id, import_id, store_name, period_month, source_sheet, row_number, raw_row)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (import_id, source_sheet, row_number) DO UPDATE SET raw_row=EXCLUDED.raw_row
                """,
                (str(uuid4()), import_id, store_name, pdate, r["source_sheet"], r["row_number"], json_dumps(r.get("raw_row"))),
            )
        for r in raw_rows:
            cur.execute(
                """
                INSERT INTO seller_kpi_store_plan_fact_sheet_rows
                (id, import_id, store_name, period_month, source_sheet, row_number, raw_row)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (import_id, source_sheet, row_number) DO UPDATE SET raw_row=EXCLUDED.raw_row
                """,
                (str(uuid4()), import_id, store_name, pdate, r["source_sheet"], r["row_number"], json_dumps(r.get("raw_row"))),
            )


def upsert_target_plans(conn: psycopg.Connection, store_name: str, period: str, metrics: list[dict[str, Any]]) -> int:
    saved = 0
    pdate = period_date(period)
    with conn.cursor() as cur:
        for r in metrics:
            key = r["metric_key"]
            plan_value = r.get("plan_value")
            if key not in TARGET_METRIC_KEYS or plan_value is None:
                continue
            cur.execute(
                """
                INSERT INTO seller_kpi_target_plans (id, month, scope_type, scope_key, metric_key, plan_value, updated_at)
                VALUES (%s, %s, 'store', %s, %s, %s, NOW())
                ON CONFLICT (month, scope_type, scope_key, metric_key)
                DO UPDATE SET plan_value=EXCLUDED.plan_value, updated_at=NOW()
                """,
                (str(uuid4()), pdate, store_name, key, plan_value),
            )
            saved += 1
    return saved


def write_preview(records: list[dict[str, Any]]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = REPORT_DIR / "archive_plan_fact_imported_rows.csv"
    fields = ["store_name", "period_month", "source_file", "source_sheet", "metric_key", "metric_label", "plan_value", "fact_value", "completion_percent", "forecast_value", "forecast_percent", "deviation_value", "last_year_fact_value", "lfl_deviation_value"]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            writer.writerow({k: r.get(k) for k in fields})
    by_store_period: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in records:
        by_store_period.setdefault((r["store_name"], r["period_month"]), []).append(r)
    def get(rows: list[dict[str, Any]], key: str, field: str) -> Any:
        for r in rows:
            if r["metric_key"] == key:
                return r.get(field)
        return None
    def fmt(v: Any) -> str:
        if v is None:
            return "—"
        try:
            n = float(v)
        except Exception:
            return str(v)
        if abs(n) >= 1000:
            return f"{n:,.0f}".replace(",", " ")
        return f"{n:.4g}"
    md = ["# Imported archive store KPI plan/fact\n\n", f"Rows: {len(records)}\n\n", "| Store | Month | Revenue plan | Revenue fact | Traffic plan | Traffic fact | Conversion plan | Conversion fact |\n", "|---|---|---:|---:|---:|---:|---:|---:|\n"]
    for (store, period), rows in sorted(by_store_period.items()):
        md.append(f"| {store} | {period} | {fmt(get(rows,'revenue','plan_value'))} | {fmt(get(rows,'revenue','fact_value'))} | {fmt(get(rows,'traffic','plan_value'))} | {fmt(get(rows,'traffic','fact_value'))} | {fmt(get(rows,'conversion','plan_value'))} | {fmt(get(rows,'conversion','fact_value'))} |\n")
    (REPORT_DIR / "archive_plan_fact_imported_rows.md").write_text("".join(md), encoding="utf-8")


def main() -> int:
    create_only = "--create-only" in sys.argv
    import_root = DEFAULT_IMPORT_ROOT
    all_metric_records: list[dict[str, Any]] = []
    with psycopg.connect(database_url()) as conn:
        create_tables(conn)
        if create_only:
            print("created tables")
            return 0
        total = {"files": 0, "metric_rows": 0, "daily_rows": 0, "summary_rows": 0, "schedule_rows": 0, "raw_rows": 0, "target_plans": 0}
        for store_slug, store_name in STORE_DIRS.items():
            store_dir = import_root / store_slug
            if not store_dir.exists():
                continue
            for path in sorted(store_dir.glob("*.xlsx")):
                sha = hashlib.sha256(path.read_bytes()).hexdigest()
                sheets = read_xlsx(path)
                main_sheet, metrics = choose_main_sheet(sheets, store_slug)
                main_rows = sheets.get(main_sheet, [])
                period = detect_period(main_rows, path.name, store_slug)
                if not period:
                    print(f"skip:no_period {path}")
                    continue
                daily = parse_daily_rows(main_rows)
                summary: list[dict[str, Any]] = []
                schedule: list[dict[str, Any]] = []
                raw_rows: list[dict[str, Any]] = []
                for sheet_name, rows in sheets.items():
                    for item in parse_summary_rows(sheet_name, rows):
                        item["source_sheet"] = sheet_name
                        summary.append(item)
                    for item in parse_schedule_rows(sheet_name, rows):
                        item["source_sheet"] = sheet_name
                        schedule.append(item)
                    for row_number, row in enumerate(rows, start=1):
                        raw_rows.append({"source_sheet": sheet_name, "row_number": row_number, "raw_row": row})
                import_id = upsert_import(conn, store_slug=store_slug, store_name=store_name, period=period, path=path, main_sheet=main_sheet, sheets=sheets, sha=sha, metrics_count=len(metrics))
                clear_import_children(conn, import_id)
                insert_rows(conn, import_id, store_name, period, metrics, daily, summary, schedule, raw_rows)
                target_saved = upsert_target_plans(conn, store_name, period, metrics)
                conn.commit()
                total["files"] += 1
                total["metric_rows"] += len(metrics)
                total["daily_rows"] += len(daily)
                total["summary_rows"] += len(summary)
                total["schedule_rows"] += len(schedule)
                total["raw_rows"] += len(raw_rows)
                total["target_plans"] += target_saved
                for m in metrics:
                    all_metric_records.append({
                        "store_name": store_name,
                        "period_month": period,
                        "source_file": path.name,
                        "source_sheet": main_sheet,
                        **m,
                    })
                print(f"imported {store_name} {period} {path.name}: metrics={len(metrics)} daily={len(daily)} summary={len(summary)} schedule={len(schedule)} raw={len(raw_rows)} target_plans={target_saved}")
        write_preview(all_metric_records)
        print("TOTAL", json.dumps(total, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
