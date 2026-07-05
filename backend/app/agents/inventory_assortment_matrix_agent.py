import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_agent import BaseAgent
from app.models.inventory_target_category import InventoryTargetCategory
from app.models.sales_record import SalesRecord
from app.models.store import Store
from app.services.inventory_control_service import InventoryControlService
from app.services.sales_record_filters import sales_record_eligible_product_filter


class AssortmentMatrixAgent(BaseAgent):
    SYSTEM_PROMPT = """You are an assortment matrix management agent.

Your task is to analyze assortment structure and ensure that inventory composition follows the target assortment matrix.
Return structured tables only. Do not invent product names.
For seller/store diagnostics, do not blame a seller when there was no stock or the sale is not attributed to a seller.
"""

    YALTA_PLAN_URL = "https://disk.yandex.ru/d/w9ahxGKuAN_Hag"
    YALTA_STORE_ID = "3daee4e4-a2ab-11f0-96fc-fa163e4cc04e"
    CENTRUM_STORE_IDS = {"centrum", "центрум", "6c3a8322-a2ab-11f0-96fc-fa163e4cc04e"}
    ONLINE_SALES_STORE_LABEL = "Сайт и приложение"
    ONLINE_SALES_STORE_IDS = {"e1a2eace-fdc8-11ef-8c0c-fa163e4cc04e"}
    ONLINE_SALES_STORE_TERMS = {"основной склад"}

    def __init__(self, db: AsyncSession):
        super().__init__()
        self.db = db
        self.inventory = InventoryControlService(db)

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run the assortment matrix analysis through the existing agent runtime."""
        params = dict(input_data or {})
        return await self.build_assortment(**params)

    async def build_assortment(
        self,
        analysis_period_days: int = 90,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        store_id: Optional[str] = None,
        seller_id: Optional[str] = None,
        seller_name: Optional[str] = None,
        brand: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        resolved_start, resolved_end, resolved_days = self._resolve_period(analysis_period_days, start_dt, end_dt)
        resolved_store_id = await self.inventory._resolve_store_id(store_id)
        rows = await self.inventory.build_inventory_rows(
            analysis_period_days=resolved_days,
            store_id=resolved_store_id,
            start_dt=resolved_start,
            end_dt=resolved_end,
            brand=brand,
            category=category,
        )

        targets_result = await self.db.execute(
            select(InventoryTargetCategory).where(InventoryTargetCategory.is_active == True)
        )
        targets = targets_result.scalars().all()
        target_map: Dict[str, float] = {}
        for t in targets:
            if t.category and isinstance(t.target_share, (int, float)):
                target_map[str(t.category).strip()] = float(t.target_share)

        out_rows, total_sales, total_stock = self._build_category_matrix(rows, target_map)
        color_distribution, top10_sales_share, global_warnings = self._build_assortment_quality(rows, total_sales)

        sales_diagnostics = await self.sales_effectiveness_matrix(
            analysis_period_days=resolved_days,
            start_dt=resolved_start,
            end_dt=resolved_end,
            store_id=resolved_store_id,
            seller_id=seller_id,
            seller_name=seller_name,
            brand=brand,
            category=category,
            inventory_rows=rows,
            limit=limit,
        )

        plan_sources = sales_diagnostics.get("plan_sources") or []
        plan_source = self._build_plan_source(
            start_dt=resolved_start,
            store_id=resolved_store_id or store_id,
            plan_sources=plan_sources,
        )
        warnings = self._dedupe(
            list(global_warnings or [])
            + list(sales_diagnostics.get("warnings") or [])
            + list(plan_source.get("warnings") or [])
        )

        return {
            "rows": out_rows,
            "total_sales": total_sales,
            "total_stock": total_stock,
            "color_distribution": color_distribution,
            "top10_sales_share": top10_sales_share,
            "sales_diagnostics": sales_diagnostics,
            "sales_effectiveness_matrix": sales_diagnostics,
            "plan_source": plan_source,
            "plan_sources": plan_sources,
            "warnings": warnings or None,
        }

    async def build_sales_effectiveness_matrix(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """Backward-compatible alias for the dashboard/service layer."""
        return await self.sales_effectiveness_matrix(*args, **kwargs)

    async def sales_effectiveness_matrix(
        self,
        analysis_period_days: int = 90,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        store_id: Optional[str] = None,
        seller_id: Optional[str] = None,
        seller_name: Optional[str] = None,
        brand: Optional[str] = None,
        category: Optional[str] = None,
        inventory_rows: Optional[List[Any]] = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        """Aggregate store/seller/brand/category/product diagnostics from 1C sales rows.

        This is deliberately implemented inside the existing AI Assortment agent. Seller
        attribution is conservative: rows without seller_id/name stay in a data-quality
        warning bucket and never produce seller-personal conclusions as facts.
        """
        resolved_start, resolved_end, resolved_days = self._resolve_period(analysis_period_days, start_dt, end_dt)
        if inventory_rows is None:
            inventory_rows = await self.inventory.build_inventory_rows(
                analysis_period_days=resolved_days,
                store_id=store_id,
                start_dt=resolved_start,
                end_dt=resolved_end,
                brand=brand,
                category=category,
            )

        sales_rows = await self._load_sales_detail_rows(
            start_dt=resolved_start,
            end_dt=resolved_end,
            store_id=store_id,
            seller_id=seller_id,
            seller_name=seller_name,
            brand=brand,
            category=category,
        )
        sales_rows = self._normalize_sales_detail_rows(sales_rows)
        plan_sources = await self._load_plan_sources(
            start_dt=resolved_start,
            end_dt=resolved_end,
            store_id=store_id,
            seller_id=seller_id,
        )
        plan_sources = self._normalize_plan_sources(plan_sources)

        stores = self._aggregate_sales_rows(sales_rows, ["store_id", "store_name"])
        sellers = self._annotate_seller_rows(
            self._aggregate_sales_rows(sales_rows, ["seller_id", "seller_external_id", "seller_name", "store_id", "store_name"])
        )
        brands = self._merge_sales_and_stock_blocks(
            self._aggregate_sales_rows(sales_rows, ["brand"]),
            self._aggregate_inventory_rows(inventory_rows, ["brand"]),
            ["brand"],
        )
        categories = self._merge_sales_and_stock_blocks(
            self._aggregate_sales_rows(sales_rows, ["category"]),
            self._aggregate_inventory_rows(inventory_rows, ["category"]),
            ["category"],
        )
        positions = self._build_position_rows(sales_rows, inventory_rows, limit=limit, use_detailed_sales=True)
        data_quality = self._build_sales_data_quality(sales_rows=sales_rows, plan_sources=plan_sources)
        diagnostics = self._build_sales_diagnostics(
            sales_rows=sales_rows,
            inventory_rows=inventory_rows,
            seller_scope_warning=None if seller_id else "seller_id_missing_personal_conclusions_blocked",
        )
        warnings: List[str] = []
        warnings.extend(data_quality.get("warnings") or [])
        if diagnostics.get("seller_personal_conclusions", {}).get("warning"):
            warnings.append(diagnostics["seller_personal_conclusions"]["warning"])

        return {
            "period": {
                "start_date": resolved_start.date().isoformat(),
                "end_date": (resolved_end.date() - timedelta(days=1)).isoformat(),
                "analysis_period_days": resolved_days,
            },
            "filters": {
                "store_id": store_id,
                "seller_id": seller_id,
                "seller_name": seller_name,
                "brand": brand,
                "category": category,
            },
            "summary": self._summary_from_sales_rows(sales_rows),
            "stores": stores,
            "sellers": sellers,
            "brands": brands,
            "categories": categories,
            "positions": positions,
            "diagnostics": diagnostics,
            "data_quality": data_quality,
            "plan_sources": plan_sources,
            "warnings": self._dedupe(warnings) or None,
        }

    def _resolve_period(
        self,
        analysis_period_days: int,
        start_dt: Optional[datetime],
        end_dt: Optional[datetime],
    ) -> Tuple[datetime, datetime, int]:
        if start_dt is not None and end_dt is not None:
            days = max(1, int((end_dt - start_dt).total_seconds() // 86400))
            return start_dt, end_dt, days
        if analysis_period_days < 1:
            analysis_period_days = 1
        today = datetime.utcnow().date()
        start_date = today - timedelta(days=analysis_period_days - 1)
        return (
            datetime.combine(start_date, datetime.min.time()),
            datetime.combine(today + timedelta(days=1), datetime.min.time()),
            analysis_period_days,
        )

    async def _load_sales_detail_rows(
        self,
        start_dt: datetime,
        end_dt: datetime,
        store_id: Optional[str],
        seller_id: Optional[str],
        seller_name: Optional[str],
        brand: Optional[str],
        category: Optional[str],
    ) -> List[Dict[str, Any]]:
        conditions = [
            SalesRecord.sale_date >= start_dt,
            SalesRecord.sale_date < end_dt,
            sales_record_eligible_product_filter(SalesRecord, func, and_),
        ]
        if store_id:
            conditions.append(SalesRecord.store_id == store_id)
        if brand:
            conditions.append(SalesRecord.product_brand == brand)
        if category:
            conditions.append(SalesRecord.product_category == category)

        stmt = select(
            SalesRecord.store_id,
            SalesRecord.product_id,
            SalesRecord.product_name,
            SalesRecord.product_article,
            SalesRecord.product_brand,
            SalesRecord.product_category,
            SalesRecord.quantity,
            SalesRecord.revenue,
            SalesRecord.document_id,
            SalesRecord.external_id,
            SalesRecord.raw_data,
        ).where(and_(*conditions))
        result = await self.db.execute(stmt)
        rows = result.all()
        store_names = await self._load_store_names({str(r.store_id) for r in rows if r.store_id})

        out: List[Dict[str, Any]] = []
        for row in rows:
            seller_key, extracted_seller_name, seller_external_id = self._extract_seller(row.raw_data)
            if seller_id and seller_key != seller_id and seller_external_id != seller_id:
                continue
            if seller_name and (extracted_seller_name or "").strip().lower() != seller_name.strip().lower():
                continue
            store_key = str(row.store_id or "—")
            store_name = self._normalize_store_name(store_key, store_names.get(store_key) or store_key)
            normalized_seller_id = seller_key or "unmatched"
            normalized_seller_name = extracted_seller_name or "Не сопоставлено с продавцом"
            out.append(
                {
                    "store_id": store_key,
                    "store_name": store_name,
                    "seller_id": normalized_seller_id,
                    "seller_external_id": seller_external_id or normalized_seller_id,
                    "seller_name": normalized_seller_name,
                    "brand": str(row.product_brand or "—").strip() or "—",
                    "category": str(row.product_category or "—").strip() or "—",
                    "product_id": str(row.product_id) if row.product_id else None,
                    "article": row.product_article,
                    "nomenclature": row.product_name,
                    "sold_qty": float(row.quantity or 0.0),
                    "revenue": float(row.revenue or 0.0),
                    "check_id": str(row.document_id or row.external_id or ""),
                    "seller_attributed": bool(seller_key or extracted_seller_name),
                }
            )
        return out

    async def _load_plan_sources(
        self,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        store_id: Optional[str] = None,
        seller_id: Optional[str] = None,
        period_start: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        period = period_start or (start_dt.date() if start_dt is not None else datetime.utcnow().date())
        month_start = period.replace(day=1)
        where = ["month = :month_start"]
        params: Dict[str, Any] = {"month_start": month_start}
        if store_id:
            where.append("store_id = :store_id")
            params["store_id"] = store_id
        if seller_id:
            where.append("seller_external_id = :seller_id")
            params["seller_id"] = seller_id
        stmt = text(f"""
            SELECT seller_external_id, seller_name, store_id, store_name, month,
                   revenue_plan, checks_plan, items_plan, source, raw_data
            FROM seller_monthly_plans
            WHERE {' AND '.join(where)}
            ORDER BY store_name NULLS LAST, seller_name NULLS LAST
        """)
        try:
            result = await self.db.execute(stmt, params)
            fetched = result.fetchall()
        except Exception:
            return [{"warning": "seller_monthly_plans_missing", "period": month_start.isoformat()}]
        rows: List[Dict[str, Any]] = []
        for row in fetched:
            mapping = getattr(row, "_mapping", row)
            rows.append(dict(mapping))
        return rows

    def _normalize_plan_sources(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for row in rows or []:
            item = dict(row)
            raw = item.get("raw_data") or {}
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    raw = {}
            if not isinstance(raw, dict):
                raw = {}
            item["raw_data"] = raw
            item["source_file"] = item.get("source_file") or raw.get("source_file") or raw.get("file_name") or raw.get("filename")
            item["source_url"] = item.get("source_url") or raw.get("source_url") or raw.get("url")
            item["period"] = self._json_safe_date(item.get("period") or item.get("month"))
            item["storage"] = item.get("storage") or "platform_db"
            item["import_source"] = item.get("import_source") or item.get("source") or raw.get("source") or "platform_manual"
            item["import_status"] = item.get("import_status") or raw.get("import_status") or "confirmed_in_platform_db"
            item["source_store_warning"] = item.get("source_store_warning") or self._plan_source_warning(item)
            normalized.append(item)
        return normalized

    async def _load_store_names(self, store_ids: set[str]) -> Dict[str, str]:
        if not store_ids:
            return {}
        result = await self.db.execute(select(Store.external_id, Store.name).where(Store.external_id.in_(list(store_ids))))
        return {
            str(external_id): self._normalize_store_name(str(external_id), name)
            for external_id, name in result.all()
            if external_id and name
        }

    def _normalize_sales_detail_rows(self, sales_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        empty_seller_markers = {"", "unmatched", "none", "null", "—", "00000000-0000-0000-0000-000000000000"}
        for row in sales_rows or []:
            item = dict(row)
            seller_id = str(item.get("seller_id") or item.get("seller_external_id") or "").strip()
            seller_name = str(item.get("seller_name") or "").strip()
            seller_external_id = str(item.get("seller_external_id") or seller_id or "").strip()
            if seller_id.lower() in empty_seller_markers and seller_external_id.lower() in empty_seller_markers:
                seller_id = "unmatched"
                seller_external_id = "unmatched"
            seller_attributed = bool(item.get("seller_attributed")) or bool(seller_id and seller_id != "unmatched") or bool(
                seller_name and seller_name != "Не сопоставлено с продавцом"
            )
            if not seller_id:
                seller_id = "unmatched"
            if not item.get("seller_external_id") or str(item.get("seller_external_id")).strip().lower() in empty_seller_markers:
                item["seller_external_id"] = seller_external_id or seller_id
            if not seller_name:
                seller_name = "Не сопоставлено с продавцом"
            item["seller_id"] = seller_id
            item["seller_name"] = seller_name
            item["seller_attributed"] = seller_attributed and seller_id != "unmatched" and str(item.get("seller_external_id") or "").strip().lower() not in empty_seller_markers
            item["store_id"] = item.get("store_id") or "—"
            item["store_name"] = self._normalize_store_name(item.get("store_id"), item.get("store_name") or item.get("store_id") or "—")
            item["brand"] = item.get("brand") or "—"
            item["category"] = item.get("category") or "—"
            item["sold_qty"] = float(item.get("sold_qty") or item.get("quantity") or 0.0)
            item["revenue"] = float(item.get("revenue") or 0.0)
            item["check_id"] = item.get("check_id") or item.get("document_id") or item.get("external_id") or ""
            normalized.append(item)
        return normalized

    def _build_category_matrix(self, rows: List[Any], target_map: Dict[str, float]) -> Tuple[List[Dict[str, Any]], float, float]:
        by_category: Dict[str, Dict[str, Any]] = {}
        total_sales = 0.0
        total_stock = 0.0
        for r in rows:
            cat = (getattr(r, "category", None) or "—").strip() or "—"
            sold_qty = float(getattr(r, "sold_qty", 0.0) or 0.0)
            stock_qty = float(getattr(r, "stock_qty", 0.0) or 0.0)
            total_sales += sold_qty
            total_stock += stock_qty
            entry = by_category.setdefault(cat, {"category": cat, "sold_qty": 0.0, "stock_qty": 0.0})
            entry["sold_qty"] += sold_qty
            entry["stock_qty"] += stock_qty

        out_rows: List[Dict[str, Any]] = []
        for cat, entry in by_category.items():
            share_sales = (entry["sold_qty"] / total_sales) if total_sales > 0 else None
            share_stock = (entry["stock_qty"] / total_stock) if total_stock > 0 else None
            target_share = target_map.get(cat)
            deviation = (share_stock - target_share) if (share_stock is not None and target_share is not None) else None
            warnings: List[str] = []
            if share_stock is not None and target_share is not None and abs(share_stock - target_share) > 0.10:
                warnings.append("target_deviation_gt_10pct")
            recommendation = None
            if deviation is not None:
                if deviation > 0.10:
                    recommendation = "reduce_stock_share"
                elif deviation < -0.10:
                    recommendation = "increase_stock_share"
            out_rows.append(
                {
                    "category": cat,
                    "sold_qty": entry["sold_qty"],
                    "stock_qty": entry["stock_qty"],
                    "category_share_sales": share_sales,
                    "category_share_stock": share_stock,
                    "target_share": target_share,
                    "deviation": deviation,
                    "recommendation": recommendation,
                    "warnings": warnings or None,
                }
            )
        out_rows.sort(key=lambda r: float(r.get("category_share_stock") or 0.0), reverse=True)
        return out_rows, total_sales, total_stock

    def _build_assortment_quality(self, rows: List[Any], total_sales: float) -> Tuple[List[Dict[str, Any]], Optional[float], List[str]]:
        color_totals: Dict[str, float] = {}
        for r in rows:
            sold_qty = float(getattr(r, "sold_qty", 0.0) or 0.0)
            if sold_qty <= 0:
                continue
            color = (getattr(r, "color", None) or "—").strip() or "—"
            color_totals[color] = color_totals.get(color, 0.0) + sold_qty
        color_distribution = [
            {"color": color, "sold_qty": qty, "color_share": (qty / total_sales) if total_sales > 0 else None}
            for color, qty in color_totals.items()
        ]
        color_distribution.sort(key=lambda x: float(x.get("color_share") or 0.0), reverse=True)
        top10_sales_share = None
        if total_sales > 0:
            top10 = sorted([float(getattr(r, "sold_qty", 0.0) or 0.0) for r in rows], reverse=True)[:10]
            top10_sales_share = (sum(top10) / total_sales) if top10 else None
        warnings: List[str] = []
        if color_distribution and color_distribution[0].get("color_share") is not None and float(color_distribution[0]["color_share"]) > 0.75:
            warnings.append("color_share_gt_75pct")
        if top10_sales_share is not None and top10_sales_share > 0.6:
            warnings.append("top10_sales_share_gt_60pct")
        return color_distribution, top10_sales_share, warnings

    def _aggregate_sales_rows(self, sales_rows: List[Dict[str, Any]], keys: List[str]) -> List[Dict[str, Any]]:
        grouped: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        for row in sales_rows:
            key = tuple(row.get(k) or "—" for k in keys)
            entry = grouped.setdefault(key, {k: row.get(k) or "—" for k in keys})
            self._add_metrics(entry, row.get("revenue"), row.get("sold_qty"), row.get("check_id"))
        return self._sorted_metric_rows(grouped.values())

    def _annotate_seller_rows(self, seller_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add safe seller-attribution metadata without inventing personal conclusions.

        This method is intentionally conservative: unmatched rows stay in the
        unmatched bucket, known 1C IDs can receive a display name, and dashboards
        get a per-row attribution warning instead of a false seller diagnosis.
        """
        try:
            from app.services.seller_kpi_service import KNOWN_SELLER_NAMES_BY_EXTERNAL_ID, ZERO_GUID
        except Exception:
            KNOWN_SELLER_NAMES_BY_EXTERNAL_ID = {}
            ZERO_GUID = "00000000-0000-0000-0000-000000000000"

        out: List[Dict[str, Any]] = []
        for row in seller_rows or []:
            item = dict(row)
            seller_id = str(item.get("seller_id") or "").strip()
            seller_external_id = str(item.get("seller_external_id") or seller_id or "").strip()
            seller_name = str(item.get("seller_name") or "").strip()
            is_unmatched = self._is_unmatched_seller_row(
                {
                    "seller_id": seller_id,
                    "seller_external_id": seller_external_id,
                    "seller_name": seller_name,
                    "seller_attributed": None,
                }
            ) or seller_id == ZERO_GUID or seller_external_id == ZERO_GUID
            if is_unmatched:
                item["seller_id"] = "unmatched"
                item["seller_external_id"] = "unmatched"
                item["seller_name"] = "Не сопоставлено с продавцом"
                item["seller_attributed"] = False
                item["personal_output_blocked"] = True
                item["warning"] = "seller_not_attributed_personal_output_blocked"
                item["warnings"] = self._dedupe(
                    list(item.get("warnings") or [])
                    + ["seller_attribution_missing", "seller_not_attributed_personal_output_blocked"]
                )
            else:
                if not seller_name and seller_external_id in KNOWN_SELLER_NAMES_BY_EXTERNAL_ID:
                    item["seller_name"] = KNOWN_SELLER_NAMES_BY_EXTERNAL_ID[seller_external_id]
                item["seller_attributed"] = True
                item["personal_output_blocked"] = False
            out.append(item)
        return out

    def _aggregate_inventory_rows(self, inventory_rows: List[Any], keys: List[str]) -> List[Dict[str, Any]]:
        grouped: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        for row in inventory_rows or []:
            item = {
                "brand": getattr(row, "brand", None) or "—",
                "category": getattr(row, "category", None) or "—",
                "stock_qty": float(getattr(row, "stock_qty", 0.0) or 0.0),
                "sold_qty": float(getattr(row, "sold_qty", 0.0) or 0.0),
                "revenue": float(getattr(row, "revenue", 0.0) or 0.0),
            }
            key = tuple(item.get(k) or "—" for k in keys)
            entry = grouped.setdefault(key, {k: item.get(k) or "—" for k in keys})
            entry["stock_qty"] = float(entry.get("stock_qty") or 0.0) + item["stock_qty"]
            entry["inventory_sold_qty"] = float(entry.get("inventory_sold_qty") or 0.0) + item["sold_qty"]
            entry["inventory_revenue"] = float(entry.get("inventory_revenue") or 0.0) + item["revenue"]
        return list(grouped.values())

    def _merge_sales_and_stock_blocks(self, sales: List[Dict[str, Any]], stock: List[Dict[str, Any]], keys: List[str]) -> List[Dict[str, Any]]:
        merged: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        for row in stock:
            key = tuple(row.get(k) or "—" for k in keys)
            merged[key] = dict(row)
        for row in sales:
            key = tuple(row.get(k) or "—" for k in keys)
            entry = merged.setdefault(key, {k: row.get(k) or "—" for k in keys})
            entry["revenue"] = float(row.get("revenue") or 0.0)
            entry["sold_qty"] = float(row.get("sold_qty") or 0.0)
            entry["checks_count"] = int(row.get("checks_count") or 0)
        out = list(merged.values())
        out.sort(key=lambda x: float(x.get("revenue") or x.get("inventory_revenue") or 0.0), reverse=True)
        return out

    def _build_inventory_sales_blocks(self, inventory_rows: List[Any], limit: int = 200) -> Dict[str, Any]:
        """Compatibility helper for tests/service callers that need position diagnostics from inventory rows only."""
        return {"positions": self._build_position_rows([], inventory_rows or [], limit=limit)}

    def _build_position_rows(
        self,
        sales_rows: List[Dict[str, Any]],
        inventory_rows: List[Any],
        limit: int,
        use_detailed_sales: bool = False,
    ) -> List[Dict[str, Any]]:
        positions: Dict[str, Dict[str, Any]] = {}
        for row in inventory_rows or []:
            key = str(getattr(row, "external_id", None) or getattr(row, "article", None) or getattr(row, "nomenclature", None) or "—")
            inventory_sold_qty = float(getattr(row, "sold_qty", 0.0) or 0.0)
            inventory_revenue = float(getattr(row, "revenue", 0.0) or 0.0)
            stock_qty = float(getattr(row, "stock_qty", 0.0) or 0.0)
            stock_cover = getattr(row, "stock_cover", None)
            positions[key] = {
                "product_id": getattr(row, "product_id", None),
                "external_id": getattr(row, "external_id", None),
                "article": getattr(row, "article", None),
                "nomenclature": getattr(row, "nomenclature", None),
                "product_name": getattr(row, "nomenclature", None),
                "brand": getattr(row, "brand", None),
                "category": getattr(row, "category", None),
                "stock_qty": stock_qty,
                "sold_qty": 0.0 if use_detailed_sales else inventory_sold_qty,
                "revenue": 0.0 if use_detailed_sales else inventory_revenue,
                "inventory_sold_qty": inventory_sold_qty,
                "inventory_revenue": inventory_revenue,
                "stock_cover": stock_cover,
                "status": getattr(row, "status", None),
                "diagnosis": self._position_diagnosis(
                    stock_qty,
                    0.0 if use_detailed_sales else inventory_sold_qty,
                    stock_cover,
                ),
            }
        for row in sales_rows:
            key = str(row.get("product_id") or row.get("article") or row.get("nomenclature") or "—")
            entry = positions.setdefault(
                key,
                {
                    "product_id": row.get("product_id"),
                    "article": row.get("article"),
                    "nomenclature": row.get("nomenclature"),
                    "product_name": row.get("nomenclature"),
                    "brand": row.get("brand"),
                    "category": row.get("category"),
                    "stock_qty": 0.0,
                    "sold_qty": 0.0,
                    "revenue": 0.0,
                    "inventory_sold_qty": 0.0,
                    "inventory_revenue": 0.0,
                    "stock_cover": None,
                    "diagnosis": "no_stock_sales_exist",
                },
            )
            entry["sold_qty"] = float(entry.get("sold_qty") or 0.0) + float(row.get("sold_qty") or 0.0)
            entry["revenue"] = float(entry.get("revenue") or 0.0) + float(row.get("revenue") or 0.0)
        for entry in positions.values():
            entry["diagnosis"] = self._position_diagnosis(
                float(entry.get("stock_qty") or 0.0),
                float(entry.get("sold_qty") or 0.0),
                entry.get("stock_cover"),
            )
        out = list(positions.values())
        out.sort(key=lambda x: (x.get("diagnosis") != "stock_without_sales", -float(x.get("revenue") or 0.0), -float(x.get("stock_qty") or 0.0)))
        return out[:limit]

    def _position_diagnosis(self, stock_qty: float, sold_qty: float, stock_cover: Any) -> str:
        if stock_qty <= 0 and sold_qty > 0:
            return "no_stock_sales_exist"
        if stock_qty > 0 and sold_qty <= 0:
            return "stock_without_sales"
        if stock_cover is not None:
            try:
                cover = float(stock_cover)
                if cover > 6:
                    return "slow_or_overstock"
                if cover < 1:
                    return "stockout_risk"
            except Exception:
                pass
        return "balanced_or_unknown"

    def _build_sales_data_quality(self, sales_rows: List[Dict[str, Any]], plan_sources: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_revenue = sum(float(r.get("revenue") or 0.0) for r in sales_rows)
        total_qty = sum(float(r.get("sold_qty") or 0.0) for r in sales_rows)
        unmatched_revenue = sum(float(r.get("revenue") or 0.0) for r in sales_rows if self._is_unmatched_seller_row(r))
        unmatched_qty = sum(float(r.get("sold_qty") or 0.0) for r in sales_rows if self._is_unmatched_seller_row(r))
        unmatched_revenue_share = (unmatched_revenue / total_revenue) if total_revenue > 0 else None
        unmatched_qty_share = (unmatched_qty / total_qty) if total_qty > 0 else None
        warnings: List[str] = []
        if unmatched_revenue_share is not None and unmatched_revenue_share > 0:
            warnings.append("unmatched_seller_sales_present")
            warnings.append("seller_attribution_missing")
        if unmatched_revenue_share is not None and unmatched_revenue_share >= 0.10:
            warnings.append("unmatched_seller_share_gte_10pct")
        if any(row.get("warning") == "seller_monthly_plans_missing" for row in plan_sources):
            warnings.append("seller_monthly_plans_missing")
        if any(row.get("source_store_warning") for row in plan_sources):
            warnings.extend([row["source_store_warning"] for row in plan_sources if row.get("source_store_warning")])
        return {
            "total_revenue": total_revenue,
            "total_qty": total_qty,
            "unmatched_revenue": unmatched_revenue,
            "unmatched_qty": unmatched_qty,
            "unattributed_seller_revenue": unmatched_revenue,
            "unattributed_seller_share": unmatched_revenue_share,
            "unmatched_revenue_share": unmatched_revenue_share,
            "unmatched_qty_share": unmatched_qty_share,
            "warnings": self._dedupe(warnings),
        }

    def _build_sales_diagnostics(
        self,
        sales_rows: List[Dict[str, Any]],
        seller_scope_warning: Optional[str] = None,
        inventory_rows: Optional[List[Any]] = None,
        inventory_blocks: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if inventory_rows is None and inventory_blocks is not None:
            inventory_rows = inventory_blocks.get("positions") or []
        positions = self._build_position_rows(sales_rows, inventory_rows or [], limit=200, use_detailed_sales=True)
        stock_without_sales = [p for p in positions if p.get("diagnosis") == "stock_without_sales"][:50]
        low_stock_with_sales = [p for p in positions if p.get("diagnosis") in {"no_stock_sales_exist", "stockout_risk"}][:50]

        out: Dict[str, Any] = {
            "stock_without_sales": stock_without_sales,
            "low_or_no_stock_with_sales": low_stock_with_sales,
            "reason_classes": [
                "no_stock",
                "weak_merchandising",
                "product_problem",
                "seller_skill_gap",
                "seller_not_attributed",
            ],
        }
        if seller_scope_warning:
            out["seller_personal_conclusions"] = {"blocked": True, "warning": seller_scope_warning}
        else:
            out["seller_personal_conclusions"] = {"blocked": False, "seller_gaps": self._build_seller_gap_rows(sales_rows)}
        return out


    def _build_seller_gap_rows(self, sales_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        categories = {r.get("category") or "—" for r in sales_rows if float(r.get("sold_qty") or 0.0) > 0}
        seller_categories: Dict[str, set[str]] = {}
        for row in sales_rows:
            if not row.get("seller_attributed") or row.get("seller_id") == "unmatched":
                continue
            seller = row.get("seller_name") or row.get("seller_id") or "—"
            seller_categories.setdefault(seller, set()).add(row.get("category") or "—")
        gaps = []
        for seller, cats in seller_categories.items():
            missing = sorted(categories - cats)
            if missing:
                gaps.append({"seller_name": seller, "missing_sold_categories": missing[:10], "diagnosis": "possible_seller_skill_gap_or_shift_assortment_gap"})
        return gaps[:50]

    @staticmethod
    def _is_unmatched_seller_row(row: Dict[str, Any]) -> bool:
        seller_id = str(row.get("seller_id") or "").strip().lower()
        seller_external_id = str(row.get("seller_external_id") or "").strip().lower()
        seller_name = str(row.get("seller_name") or "").strip().lower()
        empty_markers = {"", "unmatched", "none", "null", "—", "00000000-0000-0000-0000-000000000000"}
        if row.get("seller_attributed") is False:
            return True
        if seller_id in empty_markers and seller_external_id in empty_markers:
            return True
        if seller_name in empty_markers or seller_name == "не сопоставлено с продавцом":
            return True
        return False

    def _summary_from_sales_rows(self, sales_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        checks = {str(r.get("check_id")) for r in sales_rows if r.get("check_id")}
        return {
            "revenue": sum(float(r.get("revenue") or 0.0) for r in sales_rows),
            "sold_qty": sum(float(r.get("sold_qty") or 0.0) for r in sales_rows),
            "checks_count": len(checks),
        }

    def _extract_seller(self, raw_data: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        if isinstance(raw_data, str):
            try:
                raw_data = json.loads(raw_data)
            except Exception:
                raw_data = {}
        if not isinstance(raw_data, dict):
            return None, None, None
        seller_id = self._first_raw(
            raw_data,
            "seller_id",
            "sellerId",
            "seller_key",
            "Продавец_Key",
            "ПродавецKey",
            "ПродавецСсылка",
            "Кассир_Key",
            "Менеджер_Key",
            "Ответственный_Key",
        )
        seller_external_id = self._first_raw(
            raw_data,
            "seller_external_id",
            "sellerExternalId",
            "seller_code",
            "sellerCode",
            "ПродавецКод",
            "КассирКод",
            "МагнитныйКод",
            "ШтрихКод",
        )
        seller_name = self._first_raw(
            raw_data,
            "seller_name",
            "sellerName",
            "Продавец",
            "Кассир",
            "Менеджер",
            "Ответственный",
            "Сотрудник",
        )
        key = str(seller_id or seller_external_id or "").strip()
        external_id = str(seller_external_id or key or "").strip()
        name = str(seller_name or "").strip()

        # Reuse the seller/KPI service's known 1C seller-name map when raw sales rows
        # carry only a seller key. This keeps assortment diagnostics aligned with the
        # seller dashboard without hard-failing isolated agent unit tests.
        if key and not name:
            try:
                from app.services.seller_kpi_service import KNOWN_SELLER_NAMES_BY_EXTERNAL_ID, ZERO_GUID
            except Exception:
                KNOWN_SELLER_NAMES_BY_EXTERNAL_ID = {}
                ZERO_GUID = "00000000-0000-0000-0000-000000000000"
            if key != ZERO_GUID:
                name = str(KNOWN_SELLER_NAMES_BY_EXTERNAL_ID.get(key) or "").strip()

        return (
            key or None,
            name or None,
            external_id or None,
        )

    def _first_raw(self, raw_data: Dict[str, Any], *keys: str) -> Optional[Any]:
        for key in keys:
            value = raw_data.get(key)
            if isinstance(value, dict):
                value = value.get("Ref_Key") or value.get("Key") or value.get("Code") or value.get("Description") or value.get("name")
            if value not in (None, ""):
                return value
        # Some 1C payloads put seller fields into nested document/record objects.
        for value in raw_data.values():
            if isinstance(value, dict):
                nested = self._first_raw(value, *keys)
                if nested not in (None, ""):
                    return nested
        return None

    @classmethod
    def _normalize_store_name(cls, store_id: Any, store_name: Any) -> str:
        store_id_norm = str(store_id or "").strip().lower()
        store_name_norm = str(store_name or "").strip().lower()
        if store_id_norm in cls.ONLINE_SALES_STORE_IDS or any(term in store_name_norm for term in cls.ONLINE_SALES_STORE_TERMS):
            return cls.ONLINE_SALES_STORE_LABEL
        return str(store_name or store_id or "—").strip() or "—"

    @staticmethod
    def _has_meaningful_metrics(item: Dict[str, Any]) -> bool:
        return (
            abs(float(item.get("revenue") or 0.0)) > 0
            or abs(float(item.get("sold_qty") or 0.0)) > 0
            or int(item.get("checks_count") or 0) > 0
            or abs(float(item.get("stock_qty") or 0.0)) > 0
            or abs(float(item.get("inventory_revenue") or 0.0)) > 0
            or abs(float(item.get("inventory_sold_qty") or 0.0)) > 0
        )

    @staticmethod
    def _add_metrics(entry: Dict[str, Any], revenue: Any, qty: Any, check_id: Any) -> None:
        entry["revenue"] = float(entry.get("revenue") or 0.0) + float(revenue or 0.0)
        entry["sold_qty"] = float(entry.get("sold_qty") or 0.0) + float(qty or 0.0)
        checks = entry.setdefault("_checks", set())
        if check_id:
            checks.add(str(check_id))

    @staticmethod
    def _sorted_metric_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            checks = item.pop("_checks", set())
            item["checks_count"] = len(checks)
            if not AssortmentMatrixAgent._has_meaningful_metrics(item):
                continue
            out.append(item)
        out.sort(key=lambda x: float(x.get("revenue") or 0.0), reverse=True)
        return out

    def _build_plan_source(
        self,
        start_dt: Optional[datetime],
        store_id: Optional[str],
        plan_sources: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        warnings: List[str] = []
        normalized_store = str(store_id or "").strip().lower()
        period = start_dt.strftime("%Y-%m") if start_dt is not None else None

        usable_sources = [row for row in (plan_sources or []) if not row.get("warning")]
        selected: Optional[Dict[str, Any]] = None
        if usable_sources:
            if store_id:
                selected = next(
                    (
                        row
                        for row in usable_sources
                        if str(row.get("store_id") or "").strip().lower() == normalized_store
                        or str(row.get("store_name") or "").strip().lower() == normalized_store
                    ),
                    None,
                )
            selected = selected or usable_sources[0]

        if selected:
            source_warning = selected.get("source_store_warning")
            if source_warning:
                warnings.append(source_warning)
            return {
                "source_system": "platform_db",
                "storage": "seller_monthly_plans",
                "source_url": selected.get("source_url"),
                "source_file": selected.get("source_file"),
                "store_name": selected.get("store_name"),
                "store_id": selected.get("store_id"),
                "period": self._json_safe_date(selected.get("period") or selected.get("month") or period),
                "import_status": selected.get("import_status") or "confirmed_in_platform_db",
                "import_source": selected.get("import_source") or selected.get("source") or "platform_manual",
                "warnings": self._dedupe(warnings),
            }

        if store_id:
            warnings.append("store_plan_source_not_confirmed")
            if normalized_store in self.CENTRUM_STORE_IDS or "центр" in normalized_store or "centrum" in normalized_store:
                warnings.append("centrum_plan_source_not_confirmed")
        else:
            warnings.append("seller_monthly_plans_missing")
        return {
            "source_system": "platform_db",
            "storage": "seller_monthly_plans",
            "source_url": None,
            "source_file": None,
            "store_name": None,
            "store_id": store_id,
            "period": period,
            "import_status": "not_confirmed",
            "import_source": None,
            "warnings": self._dedupe(warnings),
        }

    @staticmethod
    def _plan_source_warning(row: Dict[str, Any]) -> Optional[str]:
        raw_text = json.dumps(row.get("raw_data") or {}, ensure_ascii=False).lower()
        source_url = str(row.get("source_url") or "").lower()
        source_file = str(row.get("source_file") or "").lower()
        store_name = str(row.get("store_name") or row.get("store_id") or "").lower()
        source_blob = " ".join([raw_text, source_url, source_file])
        yalta_source = "w9ahxgkuan_hag" in source_blob or "yalta" in source_blob or "ялт" in source_blob
        centrum_store = "центр" in store_name or "centrum" in store_name
        if yalta_source and centrum_store:
            return "yalta_plan_source_must_not_be_applied_to_centrum"
        return None

    @staticmethod
    def _json_safe_date(value: Any) -> Any:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return value

    @staticmethod
    def _dedupe(values: Iterable[Optional[str]]) -> List[str]:
        out: List[str] = []
        for value in values:
            if value and value not in out:
                out.append(value)
        return out

