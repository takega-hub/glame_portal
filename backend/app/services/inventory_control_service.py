import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store import Store
from app.models.product import Product
from app.models.product_stock import ProductStock
from app.models.sales_record import SalesRecord
from app.services.sales_record_filters import (
    is_analytics_eligible_product,
    product_eligible_filter,
    sales_record_eligible_product_filter,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InventoryRow:
    product_id: Optional[str] = None
    external_id: str = ""
    article: Optional[str] = None
    barcode: Optional[str] = None
    nomenclature: str = ""
    color: str = "—"
    category: Optional[str] = None
    brand: Optional[str] = None
    collection: Optional[str] = None
    price_cents: Optional[int] = None
    is_core_assortment: bool = False
    supports_brand_concept: bool = False
    sold_qty: float = 0.0
    revenue: float = 0.0
    checks_count: int = 0
    stock_qty: float = 0.0

    sales_month: float = 0.0
    stock_cover: Optional[float] = None
    status: str = "unknown"


class InventoryControlService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def build_inventory_rows(
        self,
        analysis_period_days: int = 90,
        store_id: Optional[str] = None,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        category: Optional[str] = None,
        color: Optional[str] = None,
        brand: Optional[str] = None,
        collection: Optional[str] = None,
    ) -> List[InventoryRow]:
        if start_dt is None or end_dt is None:
            if analysis_period_days < 1:
                analysis_period_days = 1
            now = datetime.now(timezone.utc)
            end_date = now.date()
            start_date = end_date - timedelta(days=analysis_period_days - 1)
            start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
            end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        else:
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            delta_days = int((end_dt - start_dt).total_seconds() // 86400)
            analysis_period_days = max(1, delta_days)
        months_in_period = analysis_period_days / 30.0
        if months_in_period <= 0:
            months_in_period = 1.0

        resolved_store_id = await self._resolve_store_id(store_id)
        sales_map = await self._load_sales_map(start_dt=start_dt, end_dt=end_dt, store_id=resolved_store_id)
        stock_map = await self._load_stock_map(store_id=resolved_store_id)

        external_ids = set(sales_map.keys()) | set(stock_map.keys())
        if not external_ids:
            return []

        meta_map = await self._load_product_meta_map(external_ids)

        rows: List[InventoryRow] = []
        for ext_id in external_ids:
            meta = meta_map.get(ext_id) or {}
            sales = sales_map.get(ext_id) or {"sold_qty": 0.0, "revenue": 0.0, "checks_count": 0}
            stock_qty = float(stock_map.get(ext_id) or 0.0)

            nomenclature = str(meta.get("nomenclature") or sales.get("product_name") or "").strip()
            if not nomenclature:
                continue
            if not is_analytics_eligible_product(
                product_name=nomenclature,
                product_category=meta.get("category"),
                product_article=meta.get("article"),
                product_id=ext_id,
            ):
                continue  # accessory/supplementary item

            row_color = str(meta.get("color") or "").strip()
            if not row_color:
                row_color = "—"

            row_category = meta.get("category")
            row_brand = meta.get("brand")
            row_collection = meta.get("collection")
            price_cents = meta.get("price_cents")
            is_core_assortment = bool(meta.get("is_core_assortment") or False)
            supports_brand_concept = bool(meta.get("supports_brand_concept") or False)

            sold_qty = float(sales.get("sold_qty") or 0.0)
            revenue = float(sales.get("revenue") or 0.0)
            checks_count = int(sales.get("checks_count") or 0)
            if stock_qty <= 0 and sold_qty <= 0 and revenue <= 0:
                continue

            sales_month = sold_qty / months_in_period if months_in_period > 0 else sold_qty
            stock_cover: Optional[float] = None
            status: str
            if sales_month <= 0:
                status = "no_sales"
            else:
                stock_cover = stock_qty / sales_month if sales_month > 0 else None
                status = self._status_from_stock_cover(stock_cover)

            inv = InventoryRow(
                product_id=meta.get("product_id"),
                external_id=ext_id,
                article=meta.get("article"),
                barcode=meta.get("barcode"),
                nomenclature=nomenclature,
                color=row_color,
                category=row_category,
                brand=row_brand,
                collection=row_collection,
                price_cents=price_cents,
                is_core_assortment=is_core_assortment,
                supports_brand_concept=supports_brand_concept,
                sold_qty=sold_qty,
                revenue=revenue,
                checks_count=checks_count,
                stock_qty=stock_qty,
                sales_month=sales_month,
                stock_cover=stock_cover,
                status=status,
            )
            if category and (inv.category or "").strip() != category.strip():
                continue
            if brand and (inv.brand or "").strip() != brand.strip():
                continue
            if collection and (inv.collection or "").strip() != collection.strip():
                continue
            if color and inv.color.strip() != color.strip():
                continue

            rows.append(inv)

        rows.sort(key=lambda r: (r.status, -(r.stock_cover or 0.0), r.nomenclature))
        return rows

    def _status_from_stock_cover(self, stock_cover: Optional[float]) -> str:
        if stock_cover is None:
            return "unknown"
        if stock_cover < 1:
            return "critical_stock"
        if stock_cover < 2:
            return "reorder"
        if 2 <= stock_cover <= 3:
            return "normal"
        if 3 < stock_cover <= 6:
            return "overstock"
        return "slow_moving"

    async def _load_sales_map(self, start_dt: datetime, end_dt: datetime, store_id: Optional[str]) -> Dict[str, Dict[str, Any]]:
        conditions = [
            SalesRecord.sale_date >= start_dt,
            SalesRecord.sale_date < end_dt,
            sales_record_eligible_product_filter(SalesRecord, func, and_),
        ]
        if store_id:
            conditions.append(SalesRecord.store_id == store_id)

        stmt = (
            select(
                SalesRecord.product_id.label("product_id"),
                func.sum(SalesRecord.quantity).label("sold_qty"),
                func.sum(SalesRecord.revenue).label("revenue"),
                func.count(func.distinct(func.coalesce(SalesRecord.document_id, SalesRecord.external_id))).label("checks_count"),
                func.max(SalesRecord.product_name).label("product_name"),
            )
            .where(and_(*conditions), SalesRecord.product_id.isnot(None))
            .group_by(SalesRecord.product_id)
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        out: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            pid = str(r.product_id)
            out[pid] = {
                "sold_qty": float(r.sold_qty or 0.0),
                "revenue": float(r.revenue or 0.0),
                "checks_count": int(r.checks_count or 0),
                "product_name": r.product_name,
            }
        return out

    async def _load_stock_map(self, store_id: Optional[str]) -> Dict[str, float]:
        conditions = [Product.external_id.isnot(None), product_eligible_filter(Product, func, and_)]
        if store_id:
            conditions.append(ProductStock.store_id == store_id)

        stmt = (
            select(Product.external_id, func.sum(ProductStock.available_quantity).label("stock_qty"))
            .select_from(ProductStock)
            .join(Product, ProductStock.product_id == Product.id)
            .where(and_(*conditions))
            .group_by(Product.external_id)
        )

        result = await self.db.execute(stmt)
        rows = result.all()
        out: Dict[str, float] = {}
        for ext_id, stock_qty in rows:
            if not ext_id:
                continue
            out[str(ext_id)] = float(stock_qty or 0.0)
        return out

    async def _load_product_meta_map(self, external_ids: set[str]) -> Dict[str, Dict[str, Any]]:
        if not external_ids:
            return {}

        stmt = select(
            Product.id,
            Product.external_id,
            Product.article,
            Product.barcode,
            Product.name,
            Product.category,
            Product.brand,
            Product.price,
            Product.is_core_assortment,
            Product.supports_brand_concept,
            Product.specifications,
        ).where(Product.external_id.in_(list(external_ids)), product_eligible_filter(Product, func, and_))

        result = await self.db.execute(stmt)
        rows = result.all()

        out: Dict[str, Dict[str, Any]] = {}
        for product_id, ext_id, article, barcode, name, category, brand, price, is_core_assortment, supports_brand_concept, specs in rows:
            if not ext_id:
                continue
            color, collection = self._extract_color_collection(specs)
            out[str(ext_id)] = {
                "product_id": str(product_id),
                "article": article,
                "barcode": barcode,
                "nomenclature": name,
                "category": category,
                "brand": brand,
                "collection": collection,
                "color": color,
                "price_cents": int(price) if price is not None else None,
                "is_core_assortment": bool(is_core_assortment) if is_core_assortment is not None else False,
                "supports_brand_concept": bool(supports_brand_concept) if supports_brand_concept is not None else False,
            }
        return out

    def _extract_color_collection(self, specs: Any) -> Tuple[Optional[str], Optional[str]]:
        if not isinstance(specs, dict):
            return None, None
        color = None
        for k in ("Цвет", "Color", "цвет", "color"):
            if k in specs and isinstance(specs.get(k), str) and specs.get(k).strip():
                color = specs.get(k).strip()
                break
        collection = None
        for k in ("Коллекция", "Collection", "коллекция", "collection"):
            if k in specs and isinstance(specs.get(k), str) and specs.get(k).strip():
                collection = specs.get(k).strip()
                break
        return color, collection

    async def _resolve_store_id(self, store_id: Optional[str]) -> Optional[str]:
        if not store_id:
            return None
        value = str(store_id).strip()
        if not value:
            return None
        store_uuid = None
        try:
            import uuid as _uuid

            store_uuid = _uuid.UUID(value)
        except Exception:
            store_uuid = None

        conditions = [Store.external_id == value]
        if store_uuid is not None:
            conditions.append(Store.id == store_uuid)

        stmt = select(Store).where(or_(*conditions)).limit(1)
        result = await self.db.execute(stmt)
        store = result.scalar_one_or_none()
        if store and store.external_id:
            return str(store.external_id)
        return value
