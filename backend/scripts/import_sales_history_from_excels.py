import argparse
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Optional
import sys
import uuid
import re

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from zoneinfo import ZoneInfo

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.database.connection import AsyncSessionLocal
from app.models.sales_record import SalesRecord
from app.models.store import Store
from app.services.sales_product_link_service import SalesProductLinkService


@dataclass(frozen=True)
class StoreImportSpec:
    name: str
    file_path: Path
    store_external_id: str


def _parse_name_article(value: str) -> tuple[str, Optional[str]]:
    s = (value or "").strip()
    if not s:
        return "", None
    if "," not in s:
        return s, None
    left, right = s.rsplit(",", 1)
    article = right.strip() or None
    name = left.strip() or s
    return name, article


def _stable_key(name: str, article: Optional[str]) -> str:
    base = f"{name}|{article or ''}".encode("utf-8", errors="ignore")
    return sha1(base).hexdigest()[:12]

_DT_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2}$")


def _parse_number(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, float) or isinstance(value, int):
        if pd.isna(value):
            return None
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def _read_excel_sale_rows(
    path: Path,
    store_external_id: str,
    tz: ZoneInfo,
    cutoff_utc: datetime,
) -> tuple[list[dict], int]:
    df = pd.read_excel(path, sheet_name=0, header=None)

    records: list[dict] = []
    current_dt_utc: Optional[datetime] = None
    current_doc_id: Optional[str] = None
    doc_counter = 0
    line_counter = 0

    for row_idx in range(len(df)):
        c0 = df.iat[row_idx, 0] if df.shape[1] > 0 else None
        if c0 is None or (isinstance(c0, float) and pd.isna(c0)):
            continue

        c0s = str(c0).strip()
        if not c0s:
            continue

        if c0s in ("Документ.Дата", "Номенклатура, Артикул"):
            continue

        if _DT_RE.match(c0s):
            dt_local = datetime.strptime(c0s, "%d.%m.%Y %H:%M:%S").replace(tzinfo=tz)
            dt_utc = dt_local.astimezone(timezone.utc)
            current_dt_utc = dt_utc
            doc_counter += 1
            current_doc_id = (
                f"excel_doc_v2:{store_external_id}:{dt_utc.strftime('%Y%m%dT%H%M%S')}:{doc_counter}"
            )
            line_counter = 0
            continue

        if current_dt_utc is None or current_doc_id is None:
            continue

        if current_dt_utc >= cutoff_utc:
            continue

        unit = df.iat[row_idx, 5] if df.shape[1] > 5 else None
        unit_s = str(unit).strip().lower() if unit is not None and not pd.isna(unit) else ""
        if not unit_s:
            continue

        qty = _parse_number(df.iat[row_idx, 6] if df.shape[1] > 6 else None)
        rev = _parse_number(df.iat[row_idx, 7] if df.shape[1] > 7 else None)
        if qty is None or rev is None:
            continue

        name, article = _parse_name_article(c0s)
        if not name:
            continue

        key = _stable_key(name, article)
        external_id = f"{current_doc_id}:{key}:{row_idx}:{line_counter}"
        line_counter += 1

        records.append(
            {
                "id": uuid.uuid4(),
                "sale_date": current_dt_utc,
                "external_id": external_id,
                "document_id": current_doc_id,
                "store_id": store_external_id,
                "product_id": None,
                "customer_id": None,
                "organization_id": None,
                "product_name": name,
                "product_article": article,
                "product_category": None,
                "product_brand": None,
                "product_type": None,
                "revenue": float(rev),
                "quantity": float(qty),
                "revenue_without_discount": None,
                "cost_price": None,
                "margin": None,
                "channel": "offline",
                "raw_data": {
                    "source": "excel_import_v2",
                    "file": path.name,
                    "original_datetime": current_dt_utc.isoformat(),
                    "unit": unit_s,
                },
                "sync_batch_id": f"excel_import_v2:{store_external_id}:{path.name}",
            }
        )

    return records, doc_counter


async def _get_store_display_name_by_external_id(external_id: str) -> Optional[str]:
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Store.name).where(Store.external_id == external_id))
        row = res.first()
        return row[0] if row else None


async def _bulk_upsert_sales_records(records: list[dict]) -> None:
    if not records:
        return
    async with AsyncSessionLocal() as db:
        linker = SalesProductLinkService(db)
        for r in records:
            if (not r.get("product_id")) and r.get("product_article"):
                r["product_id"] = await linker.resolve_product_external_id(r.get("product_article"), r.get("product_name"))

        stmt = pg_insert(SalesRecord).values(records)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["external_id"],
            index_where=SalesRecord.external_id.isnot(None),
        )
        await db.execute(stmt)
        await db.commit()


async def import_store_file(
    spec: StoreImportSpec,
    batch_size: int,
    tz: ZoneInfo,
    cutoff_utc: datetime,
) -> tuple[int, int]:
    records, docs = _read_excel_sale_rows(
        path=spec.file_path,
        store_external_id=spec.store_external_id,
        tz=tz,
        cutoff_utc=cutoff_utc,
    )
    if not records:
        return 0, 0

    inserted = 0
    batch: list[dict] = []
    for r in records:
        batch.append(r)
        if len(batch) >= batch_size:
            await _bulk_upsert_sales_records(batch)
            inserted += len(batch)
            batch.clear()

    if batch:
        await _bulk_upsert_sales_records(batch)
        inserted += len(batch)
        batch.clear()

    return inserted, docs


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cutoff-date", default="2026-01-25")
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--timezone", default="Europe/Moscow")
    args = parser.parse_args()

    load_dotenv("/root/glame-platform/backend/.env", override=False)

    tz = ZoneInfo(args.timezone)
    cutoff_utc = datetime.fromisoformat(args.cutoff_date + "T00:00:00").replace(tzinfo=timezone.utc)

    specs = [
        StoreImportSpec(
            name="Центрум",
            file_path=Path("/root/glame-platform/data/Centrum.xlsx"),
            store_external_id="6c3a8322-a2ab-11f0-96fc-fa163e4cc04e",
        ),
        StoreImportSpec(
            name="Меганом",
            file_path=Path("/root/glame-platform/data/Meganom.xlsx"),
            store_external_id="8cebda58-a2ab-11f0-96fc-fa163e4cc04e",
        ),
        StoreImportSpec(
            name="Ялта",
            file_path=Path("/root/glame-platform/data/Yalta.xlsx"),
            store_external_id="3daee4e4-a2ab-11f0-96fc-fa163e4cc04e",
        ),
    ]

    for spec in specs:
        if not spec.file_path.exists():
            raise FileNotFoundError(str(spec.file_path))

    for spec in specs:
        store_name = await _get_store_display_name_by_external_id(spec.store_external_id)
        store_label = store_name or spec.name

        inserted, docs = await import_store_file(
            spec=spec,
            batch_size=args.batch_size,
            tz=tz,
            cutoff_utc=cutoff_utc,
        )
        print(f"[{store_label}] imported rows={inserted} docs={docs} cutoff<{cutoff_utc.isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
