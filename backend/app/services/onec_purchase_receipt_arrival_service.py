"""Import 1C stock arrival documents as CRM new-arrival events.

Business rule: CRM "Новое поступление" is created only from a real merchandise
arrival source: supplier purchase receipts on the main warehouse. Posted store
transfers update availability/routing only and can never create a CRM wave.
Stock sync snapshots are not considered a new-arrival source. Packaging,
 расходники and other technical companion items are filtered out.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_stock_arrival_event import ProductStockArrivalEvent
from app.models.store import Store
from app.services.sales_record_filters import is_analytics_eligible_product

logger = logging.getLogger(__name__)

ZERO_GUID = "00000000-0000-0000-0000-000000000000"
SOURCE = "onec_purchase_receipt"
TRANSFER_SOURCE = "onec_store_transfer"


def _env_bool(name: str, default: str = "true") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").strip().split())


def _parse_1c_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).split(".")[0].replace("Z", "")
        parsed = datetime.fromisoformat(text)
        if parsed.year <= 1:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _product_external_candidates(line: Dict[str, Any]) -> List[str]:
    product_key = _clean(line.get("Номенклатура_Key"))
    characteristic_key = _clean(line.get("Характеристика_Key"))
    candidates: List[str] = []
    if product_key and product_key != ZERO_GUID and characteristic_key and characteristic_key != ZERO_GUID:
        candidates.append(f"{product_key}#{characteristic_key}")
    if product_key and product_key != ZERO_GUID:
        candidates.append(product_key)
    return list(dict.fromkeys(candidates))


class OneCPurchaseReceiptArrivalService:
    """Creates product_stock_arrival_events from 1C supplier receipt documents."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        api_url: Optional[str] = None,
        api_token: Optional[str] = None,
        receipt_endpoint: Optional[str] = None,
        receipt_lines_endpoint: Optional[str] = None,
        transfer_endpoint: Optional[str] = None,
        main_warehouse_id: Optional[str] = None,
    ):
        self.db = db
        self.api_url = (api_url or os.getenv("ONEC_API_URL") or "").rstrip("/")
        self.api_token = api_token or os.getenv("ONEC_API_TOKEN")
        self.receipt_endpoint = receipt_endpoint or os.getenv("ONEC_PURCHASE_RECEIPT_ENDPOINT", "/Document_ПриходнаяНакладная")
        self.receipt_lines_endpoint = receipt_lines_endpoint or os.getenv("ONEC_PURCHASE_RECEIPT_LINES_ENDPOINT", "/Document_ПриходнаяНакладная_Запасы")
        self.transfer_endpoint = transfer_endpoint or os.getenv("ONEC_STOCK_TRANSFER_ENDPOINT", "/Document_ПеремещениеЗапасов")
        self.main_warehouse_id = main_warehouse_id or os.getenv(
            "ONEC_MAIN_WAREHOUSE_ID",
            "e1a2eace-fdc8-11ef-8c0c-fa163e4cc04e",
        )
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "OneCPurchaseReceiptArrivalService":
        if self.api_url:
            headers = {"Accept": "application/json"}
            if self.api_token:
                headers["Authorization"] = self.api_token if self.api_token.startswith("Basic ") else f"Basic {self.api_token}"
            self.client = httpx.AsyncClient(timeout=120.0, headers=headers, verify=True)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.client:
            await self.client.aclose()

    def _url(self, endpoint: str) -> str:
        if not self.api_url:
            raise ValueError("ONEC_API_URL is not configured")
        return f"{self.api_url}{endpoint if endpoint.startswith('/') else '/' + endpoint}"

    async def _fetch_json_page(self, endpoint: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.client:
            raise ValueError("1C client is not configured")
        response = await self.client.get(self._url(endpoint), params=params)
        response.raise_for_status()
        data = response.json()
        return list(data.get("value") or [])

    async def _fetch_count(self, endpoint: str) -> int:
        if not self.client:
            raise ValueError("1C client is not configured")
        response = await self.client.get(self._url(f"{endpoint.rstrip('/')}/$count"))
        response.raise_for_status()
        return int(str(response.text or "0").strip() or "0")

    async def _fetch_receipts(self, *, since: datetime, page_size: int, max_documents: int) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        skip = 0
        select_fields = ",".join([
            "Ref_Key",
            "Number",
            "Date",
            "Posted",
            "DeletionMark",
            "ВидОперации",
            "СтруктурнаяЕдиница_Key",
            "Комментарий",
        ])
        # 1C Fresh can be inconsistent with datetime filters on this endpoint.
        # We still send a filter, but apply the authoritative date filter locally.
        filter_text = f"Posted eq true and Date ge datetime'{since.replace(tzinfo=None).isoformat(timespec='seconds')}'"
        while len(rows) < max_documents:
            page = await self._fetch_json_page(
                self.receipt_endpoint,
                {
                    "$top": page_size,
                    "$skip": skip,
                    "$select": select_fields,
                    "$filter": filter_text,
                    "$orderby": "Date desc",
                },
            )
            if not page:
                break
            for row in page:
                doc_date = _parse_1c_datetime(row.get("Date"))
                if not doc_date or doc_date < since:
                    continue
                if row.get("Posted") is not True or row.get("DeletionMark") is True:
                    continue
                if _clean(row.get("ВидОперации")) != "ПоступлениеОтПоставщика":
                    continue
                rows.append(row)
                if len(rows) >= max_documents:
                    break
            if len(page) < page_size:
                break
            skip += page_size
        return rows

    async def _fetch_recent_transfer_documents(
        self,
        *,
        since: datetime,
        page_size: int,
        max_documents: int,
    ) -> List[Dict[str, Any]]:
        """Fetch recent transfer documents from the tail of the 1C endpoint.

        On this 1C Fresh base datetime filters/orderby for transfer documents can
        fail server-side, so we read recent tail pages and apply date/store rules
        locally. Natural endpoint order is stable enough for tail scanning here.
        """
        rows: List[Dict[str, Any]] = []
        select_fields = ",".join([
            "Ref_Key",
            "Number",
            "Date",
            "Posted",
            "DeletionMark",
            "ВидОперации",
            "СтруктурнаяЕдиница_Key",
            "СтруктурнаяЕдиницаПолучатель_Key",
            "Комментарий",
        ])
        try:
            total = await self._fetch_count(self.transfer_endpoint)
        except Exception:
            logger.info("1C transfer count failed; falling back to first pages", exc_info=True)
            total = max_documents

        skip = max(total - page_size, 0)
        scanned = 0
        while skip >= 0 and len(rows) < max_documents and scanned < max_documents * 4:
            page = await self._fetch_json_page(
                self.transfer_endpoint,
                {
                    "$top": page_size,
                    "$skip": skip,
                    "$select": select_fields,
                },
            )
            if not page:
                break
            page_dates = [_parse_1c_datetime(row.get("Date")) for row in page]
            page_newest = max([value for value in page_dates if value], default=None)
            for row in page:
                doc_date = _parse_1c_datetime(row.get("Date"))
                if not doc_date or doc_date < since:
                    continue
                if row.get("Posted") is not True or row.get("DeletionMark") is True:
                    continue
                if _clean(row.get("ВидОперации")) not in {"Перемещение", ""}:
                    continue
                rows.append(row)
                if len(rows) >= max_documents:
                    break
            scanned += len(page)
            if page_newest and page_newest < since:
                break
            if skip == 0:
                break
            skip = max(skip - page_size, 0)
        rows.sort(key=lambda row: row.get("Date") or "")
        return rows[:max_documents]

    async def _fetch_document_table_lines(self, endpoint: str, document_id: str) -> List[Dict[str, Any]]:
        if not self.client:
            raise ValueError("1C client is not configured")
        response = await self.client.get(self._url(f"{endpoint.rstrip('/')}(guid'{document_id}')/Запасы"))
        response.raise_for_status()
        data = response.json()
        return list(data.get("value") or [])

    async def _fetch_receipt_lines_page(
        self,
        *,
        receipt_ids: List[str],
        page_size: int,
        skip: int,
    ) -> List[Dict[str, Any]]:
        select_fields = ",".join([
            "Ref_Key",
            "LineNumber",
            "Номенклатура_Key",
            "Характеристика_Key",
            "СтруктурнаяЕдиница_Key",
            "Количество",
            "Цена",
            "Сумма",
            "Содержание",
            "Комментарий",
        ])
        receipt_filter = " or ".join([f"Ref_Key eq guid'{receipt_id}'" for receipt_id in receipt_ids if receipt_id])
        params: Dict[str, Any] = {
            "$top": page_size,
            "$skip": skip,
            "$select": select_fields,
        }
        if receipt_filter:
            params["$filter"] = receipt_filter
        return await self._fetch_json_page(self.receipt_lines_endpoint, params)

    async def _fetch_receipt_lines(self, receipt_id: str, page_size: int = 1000) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        skip = 0
        select_fields = ",".join([
            "Ref_Key",
            "LineNumber",
            "Номенклатура_Key",
            "Характеристика_Key",
            "СтруктурнаяЕдиница_Key",
            "Количество",
            "Цена",
            "Сумма",
            "Содержание",
            "Комментарий",
        ])
        while True:
            page = await self._fetch_json_page(
                self.receipt_lines_endpoint,
                {
                    "$top": page_size,
                    "$skip": skip,
                    "$select": select_fields,
                    "$filter": f"Ref_Key eq guid'{receipt_id}'",
                },
            )
            rows.extend(page)
            if len(page) < page_size:
                break
            skip += page_size
        return rows

    async def _fetch_receipt_lines_bulk(self, receipt_ids: List[str], page_size: int = 1000) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch document table lines.

        Some 1C/OData installations reject large OR filters on document table
        parts. In that case we fall back to one request per receipt.
        """
        grouped: Dict[str, List[Dict[str, Any]]] = {receipt_id: [] for receipt_id in receipt_ids if receipt_id}
        if not grouped:
            return grouped

        for index in range(0, len(receipt_ids), 15):
            chunk = [receipt_id for receipt_id in receipt_ids[index : index + 15] if receipt_id]
            if not chunk:
                continue
            try:
                skip = 0
                while True:
                    page = await self._fetch_receipt_lines_page(receipt_ids=chunk, page_size=page_size, skip=skip)
                    for line in page:
                        receipt_id = _clean(line.get("Ref_Key"))
                        if receipt_id in grouped:
                            grouped[receipt_id].append(line)
                    if len(page) < page_size:
                        break
                    skip += page_size
            except Exception:
                logger.info("1C receipt lines bulk request failed; falling back to per-document requests", exc_info=True)
                for receipt_id in chunk:
                    grouped[receipt_id] = await self._fetch_receipt_lines(receipt_id, page_size=page_size)
        return grouped

    async def _target_crm_stores(self) -> List[Store]:
        result = await self.db.execute(
            select(Store).where(
                Store.is_active.is_(True),
                Store.external_id.isnot(None),
            ).order_by(Store.name.asc())
        )
        stores: List[Store] = []
        for store in result.scalars().all():
            name = _clean(store.name).lower()
            if "склад" in name or "основной" in name or "меганом" in name:
                continue
            stores.append(store)
        return stores

    async def _store_by_external_id(self, external_id: str) -> Optional[Store]:
        cleaned_id = _clean(external_id)
        if not cleaned_id:
            return None
        return await self.db.scalar(select(Store).where(Store.external_id == cleaned_id))

    async def _products_by_external_id(self, candidates: Iterable[str]) -> Dict[str, Product]:
        values = [value for value in dict.fromkeys(candidates) if value]
        mapping: Dict[str, Product] = {}
        for index in range(0, len(values), 1000):
            chunk = values[index : index + 1000]
            result = await self.db.execute(select(Product).where(Product.external_id.in_(chunk)))
            for product in result.scalars().all():
                if product.external_id:
                    mapping[str(product.external_id)] = product
        return mapping

    async def sync_recent_receipts(
        self,
        *,
        since: Optional[datetime] = None,
        lookback_hours: int = 48,
        page_size: int = 200,
        max_documents: int = 500,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        if not _env_bool("CRM_NEW_ARRIVAL_RECEIPT_SYNC_ENABLED", "true"):
            return {"enabled": False, "created": 0, "skipped": 0, "errors": []}
        since = since or (datetime.now(timezone.utc) - timedelta(hours=max(1, lookback_hours)))
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        since = since.astimezone(timezone.utc)

        receipts = await self._fetch_receipts(since=since, page_size=page_size, max_documents=max_documents)
        primary_store = await self._store_by_external_id(self.main_warehouse_id)
        if not primary_store:
            return {"enabled": True, "since": since.isoformat(), "receipts": len(receipts), "created": 0, "skipped": 0, "errors": ["main_warehouse_store_not_found"]}
        primary_store_name = primary_store.name

        receipt_ids = [_clean(receipt.get("Ref_Key")) for receipt in receipts if _clean(receipt.get("Ref_Key"))]
        raw_lines_by_doc = await self._fetch_receipt_lines_bulk(receipt_ids, page_size=page_size)
        all_lines_by_doc: Dict[str, List[Dict[str, Any]]] = {}
        product_candidates: List[str] = []
        for receipt_id, lines in raw_lines_by_doc.items():
            filtered_lines = [
                line for line in lines
                if _clean(line.get("СтруктурнаяЕдиница_Key")) == self.main_warehouse_id
            ]
            all_lines_by_doc[receipt_id] = filtered_lines
            for line in filtered_lines:
                product_candidates.extend(_product_external_candidates(line))

        products_by_external_id = await self._products_by_external_id(product_candidates)
        created = 0
        skipped = 0
        errors: List[Dict[str, Any]] = []
        by_receipt: Dict[str, Dict[str, Any]] = {}

        for receipt in receipts:
            receipt_id = _clean(receipt.get("Ref_Key"))
            receipt_date = _parse_1c_datetime(receipt.get("Date")) or since
            receipt_number = _clean(receipt.get("Number"))
            lines = all_lines_by_doc.get(receipt_id, [])
            stats = by_receipt.setdefault(receipt_id, {"number": receipt_number, "date": receipt_date.isoformat(), "created": 0, "skipped": 0})
            for line in lines:
                candidates = _product_external_candidates(line)
                product = next((products_by_external_id.get(candidate) for candidate in candidates if products_by_external_id.get(candidate)), None)
                if not product:
                    skipped += 1
                    stats["skipped"] += 1
                    continue
                if not is_analytics_eligible_product(
                    product_name=product.name,
                    product_category=product.category,
                    product_article=product.article or product.external_code,
                    product_id=product.external_id,
                    raw_text=" ".join([_clean(line.get("Содержание")), _clean(line.get("Комментарий"))]),
                    total_amount_kopecks=product.price,
                ):
                    skipped += 1
                    stats["skipped"] += 1
                    continue
                try:
                    quantity = float(line.get("Количество") or 0)
                except (TypeError, ValueError):
                    quantity = 0.0
                if quantity <= 0:
                    skipped += 1
                    stats["skipped"] += 1
                    continue
                idempotency_key = f"{SOURCE}:{receipt_id}:{line.get('LineNumber')}:{product.id}:{self.main_warehouse_id}"
                existing = await self.db.scalar(
                    select(ProductStockArrivalEvent.id).where(ProductStockArrivalEvent.source_idempotency_key == idempotency_key)
                )
                if existing:
                    skipped += 1
                    stats["skipped"] += 1
                    continue
                batch_id = f"{SOURCE}:{receipt_id}:{receipt_date.date().isoformat()}:{self.main_warehouse_id}"
                if not dry_run:
                    self.db.add(ProductStockArrivalEvent(
                        id=uuid.uuid4(),
                        product_id=product.id,
                        store_id=self.main_warehouse_id,
                        previous_available_quantity=0.0,
                        available_quantity=quantity,
                        delta_quantity=quantity,
                        event_type="PRIMARY_RECEIPT",
                        source=SOURCE,
                        source_sync_id=receipt_id,
                        source_idempotency_key=idempotency_key,
                        source_payload={
                            "batch_id": batch_id,
                            "batch_status": "detected_on_main_warehouse",
                            "receipt_id": receipt_id,
                            "receipt_number": receipt_number,
                            "receipt_date": receipt_date.isoformat(),
                                "receipt_operation": receipt.get("ВидОперации"),
                                "primary_location_id": self.main_warehouse_id,
                                "primary_location_name": primary_store_name,
                            "line_number": line.get("LineNumber"),
                            "quantity": quantity,
                            "price": line.get("Цена"),
                            "amount": line.get("Сумма"),
                            "source_rule": "primary_purchase_receipt_to_main_warehouse",
                        },
                        received_at=receipt_date,
                    ))
                created += 1
                stats["created"] += 1

        if dry_run:
            await self.db.rollback()
        else:
            await self.db.commit()
        return {
            "enabled": True,
            "source": SOURCE,
            "since": since.isoformat(),
            "receipts": len(receipts),
            "primary_location_id": self.main_warehouse_id,
            "primary_location_name": primary_store_name,
            "created": created,
            "skipped": skipped,
            "errors": errors,
            "by_receipt": by_receipt,
            "dry_run": dry_run,
        }

    async def sync_recent_transfers(
        self,
        *,
        since: Optional[datetime] = None,
        lookback_hours: int = 48,
        page_size: int = 200,
        max_documents: int = 500,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        if not _env_bool("CRM_NEW_ARRIVAL_TRANSFER_SYNC_ENABLED", "true"):
            return {"enabled": False, "created": 0, "skipped": 0, "errors": []}
        since = since or (datetime.now(timezone.utc) - timedelta(hours=max(1, lookback_hours)))
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        since = since.astimezone(timezone.utc)

        transfers = await self._fetch_recent_transfer_documents(since=since, page_size=page_size, max_documents=max_documents)
        target_stores = await self._target_crm_stores()
        target_store_by_external_id = {
            _clean(store.external_id): store
            for store in target_stores
            if _clean(store.external_id)
        }
        if not target_store_by_external_id:
            return {"enabled": True, "since": since.isoformat(), "transfers": len(transfers), "created": 0, "availability_updates": 0, "skipped": 0, "errors": ["no_target_crm_stores"], "ignored_as_new_arrival_source": True}

        product_candidates: List[str] = []
        candidate_transfers: List[Dict[str, Any]] = []
        skipped = 0
        errors: List[Dict[str, Any]] = []

        for transfer in transfers:
            transfer_id = _clean(transfer.get("Ref_Key"))
            recipient_store_id = _clean(transfer.get("СтруктурнаяЕдиницаПолучатель_Key"))
            if not transfer_id or recipient_store_id not in target_store_by_external_id:
                skipped += 1
                continue
            try:
                lines = await self._fetch_document_table_lines(self.transfer_endpoint, transfer_id)
            except Exception as exc:
                errors.append({"transfer_id": transfer_id, "error": str(exc)})
                continue
            transfer["__lines"] = lines
            candidate_transfers.append(transfer)
            for line in lines:
                product_candidates.extend(_product_external_candidates(line))

        products_by_external_id = await self._products_by_external_id(product_candidates)
        availability_updates = 0
        by_transfer: Dict[str, Dict[str, Any]] = {}

        for transfer in candidate_transfers:
            transfer_id = _clean(transfer.get("Ref_Key"))
            transfer_date = _parse_1c_datetime(transfer.get("Date")) or since
            transfer_number = _clean(transfer.get("Number"))
            recipient_store_id = _clean(transfer.get("СтруктурнаяЕдиницаПолучатель_Key"))
            source_store_id = _clean(transfer.get("СтруктурнаяЕдиница_Key"))
            target_store = target_store_by_external_id.get(recipient_store_id)
            if not target_store:
                skipped += 1
                continue
            stats = by_transfer.setdefault(
                transfer_id,
                {
                    "number": transfer_number,
                    "date": transfer_date.isoformat(),
                    "source_store_id": source_store_id,
                    "target_store_id": recipient_store_id,
                    "availability_updates": 0,
                    "skipped": 0,
                },
            )
            for line in transfer.get("__lines") or []:
                candidates = _product_external_candidates(line)
                product = next((products_by_external_id.get(candidate) for candidate in candidates if products_by_external_id.get(candidate)), None)
                if not product:
                    skipped += 1
                    stats["skipped"] += 1
                    continue
                if not is_analytics_eligible_product(
                    product_name=product.name,
                    product_category=product.category,
                    product_article=product.article or product.external_code,
                    product_id=product.external_id,
                    raw_text=" ".join([
                        _clean(transfer.get("Комментарий")),
                        _clean(line.get("Содержание")),
                        _clean(line.get("Комментарий")),
                    ]),
                    total_amount_kopecks=product.price,
                ):
                    skipped += 1
                    stats["skipped"] += 1
                    continue
                try:
                    quantity = float(line.get("Количество") or 0)
                except (TypeError, ValueError):
                    quantity = 0.0
                if quantity <= 0:
                    skipped += 1
                    stats["skipped"] += 1
                    continue
                availability_updates += 1
                stats["availability_updates"] += 1

        await self.db.rollback()
        return {
            "enabled": True,
            "source": TRANSFER_SOURCE,
            "since": since.isoformat(),
            "transfers": len(candidate_transfers),
            "target_stores": len(target_store_by_external_id),
            "created": 0,
            "availability_updates": availability_updates,
            "skipped": skipped,
            "errors": errors,
            "by_transfer": by_transfer,
            "dry_run": dry_run,
            "ignored_as_new_arrival_source": True,
            "source_rule": "transfers_update_availability_only_do_not_create_arrival_events",
        }
