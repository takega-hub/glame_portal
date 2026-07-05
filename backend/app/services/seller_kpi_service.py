"""Seller KPI and shift schedule service for GLAME staff dashboard.

Read-only KPI calculations come from local 1C sales records. Monthly seller plans and
shift schedule are stored locally and can be imported from a Yandex Disk Excel file.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.sales_record_filters import ACCESSORY_PRODUCT_TERMS, ANALYTICS_ELIGIBLE_PRODUCT_SQL


SELLER_KEY_EXPR = "COALESCE(raw_data->>'Продавец_Key', raw_data->>'Сотрудник_Key', raw_data->>'Кассир_Key', raw_data->>'Ответственный_Key', raw_data->>'Менеджер_Key', raw_data->>'Продавец')"
SELLER_NAME_EXPR = "COALESCE(raw_data->>'Продавец', raw_data->>'Сотрудник', raw_data->>'Кассир', raw_data->>'Ответственный', raw_data->>'Менеджер')"
SELLER_DISPLAY_NAME_EXPR = """
COALESCE(
    raw_data->>'Продавец',
    raw_data->>'Сотрудник',
    raw_data->>'Кассир',
    raw_data->>'Ответственный',
    raw_data->>'Менеджер',
    CASE COALESCE(raw_data->>'Продавец_Key', raw_data->>'Сотрудник_Key', raw_data->>'Кассир_Key', raw_data->>'Ответственный_Key', raw_data->>'Менеджер_Key', raw_data->>'Продавец')
        WHEN '6ded351c-4a43-11f1-9b6c-fa163e4cc04e' THEN 'Максимычева Евгения'
        WHEN '4a1f26ca-a92d-11f0-9b8f-fa163e4cc04e' THEN 'Уразгильдеева Екатерина'
        WHEN '1d5f839e-ba5a-11f0-836e-fa163e4cc04e' THEN 'Рогалевич Ирина'
        WHEN 'eee9caf0-293b-11f1-83c6-fa163e4cc04e' THEN 'Бешлиева Аджере'
        WHEN '4d189eb8-4ee8-11f1-9b97-fa163e4cc04e' THEN 'Орешников Анатолий'
    END
)
"""
STORE_EXPR = "COALESCE(s.name, sr.store_id)"
KPI_ELIGIBLE_PRODUCT_SQL = ANALYTICS_ELIGIBLE_PRODUCT_SQL
KPI_EXCLUDED_PRODUCT_TERMS = ACCESSORY_PRODUCT_TERMS
KNOWN_SELLER_NAMES_BY_EXTERNAL_ID = {
    # 1C Catalog_Сотрудники Ref_Key -> short display name used in GLAME roster/KPI.
    "6ded351c-4a43-11f1-9b6c-fa163e4cc04e": "Максимычева Евгения",
    "4a1f26ca-a92d-11f0-9b8f-fa163e4cc04e": "Уразгильдеева Екатерина",
    "1d5f839e-ba5a-11f0-836e-fa163e4cc04e": "Рогалевич Ирина",
    "eee9caf0-293b-11f1-83c6-fa163e4cc04e": "Бешлиева Аджере",
    "4d189eb8-4ee8-11f1-9b97-fa163e4cc04e": "Орешников Анатолий",
}
KNOWN_SELLER_EXTERNAL_IDS_BY_NORMALIZED_NAME = {
    "максимычева евгения": "6ded351c-4a43-11f1-9b6c-fa163e4cc04e",
    "уразгильдеева екатерина": "4a1f26ca-a92d-11f0-9b8f-fa163e4cc04e",
    "рогалевич ирина": "1d5f839e-ba5a-11f0-836e-fa163e4cc04e",
    "бешлиева аджере": "eee9caf0-293b-11f1-83c6-fa163e4cc04e",
    "орешников анатолий": "4d189eb8-4ee8-11f1-9b97-fa163e4cc04e",
}
ZERO_GUID = "00000000-0000-0000-0000-000000000000"

YALTA_ASSORTMENT_GUIDANCE_JUNE_2026 = [
    {"assortment_block": "IS", "current_stock": 1740000, "incoming": 0, "available_to_sell": 1740000, "share": 0.2724, "sales_guidance": 776181, "stock_after_guidance": 963819, "comment": "Ключевой ассортиментный блок: поддерживать регулярное предложение, не продавать бренд под ноль."},
    {"assortment_block": "Antura", "current_stock": 511920, "incoming": 300000, "available_to_sell": 811920, "share": 0.1271, "sales_guidance": 362182, "stock_after_guidance": 449738, "comment": "Ожидается поступление: важно активно вводить в предложения, а не ждать остаточного спроса."},
    {"assortment_block": "Raganella", "current_stock": 292630, "incoming": 0, "available_to_sell": 292630, "share": 0.0458, "sales_guidance": 130537, "stock_after_guidance": 162093, "comment": "Премиальный блок для расширения выбора и ухода от перекоса в легкие группы."},
    {"assortment_block": "SALE", "current_stock": 73830, "incoming": 0, "available_to_sell": 73830, "share": 0.0116, "sales_guidance": 32934, "stock_after_guidance": 40896, "comment": "SALE не должен становиться главным способом выполнения плана."},
    {"assortment_block": "UNOde50/Men", "current_stock": 185980, "incoming": 0, "available_to_sell": 185980, "share": 0.0291, "sales_guidance": 82962, "stock_after_guidance": 103018, "comment": "Поддерживать мужские и характерные позиции как отдельный повод к продаже."},
    {"assortment_block": "Kalliope", "current_stock": 71440, "incoming": 100000, "available_to_sell": 171440, "share": 0.0268, "sales_guidance": 76476, "stock_after_guidance": 94964, "comment": "Малая премиальная группа: показывать как точечное усиление образа."},
    {"assortment_block": "Claudio Canzian", "current_stock": 31770, "incoming": 0, "available_to_sell": 31770, "share": 0.0050, "sales_guidance": 14172, "stock_after_guidance": 17598, "comment": "Небольшой премиальный блок: не игнорировать при подборе образов."},
    {"assortment_block": "Остальное", "current_stock": 2580190, "incoming": 500000, "available_to_sell": 3080190, "share": 0.4822, "sales_guidance": 1374014, "stock_after_guidance": 1706176, "comment": "Широкая база ассортимента: использовать для комплектации и закрытия разных поводов."},
]
YALTA_ASSORTMENT_GUIDANCE_MONTH = "2026-06"
YALTA_ASSORTMENT_GUIDANCE_STORE = "Ялта, Набережная 18"
YALTA_ASSORTMENT_GUIDANCE_TOTAL = 2849458



class SellerKPIService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_tables(self) -> None:
        await self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS seller_monthly_plans (
                id VARCHAR(64) PRIMARY KEY,
                seller_external_id VARCHAR(255) NULL,
                seller_name VARCHAR(255) NOT NULL,
                store_id VARCHAR(255) NULL,
                store_name VARCHAR(255) NULL,
                month DATE NOT NULL,
                revenue_plan NUMERIC(14, 2) NOT NULL DEFAULT 0,
                checks_plan INTEGER NULL,
                items_plan NUMERIC(14, 2) NULL,
                source VARCHAR(64) NOT NULL DEFAULT 'manual',
                raw_data JSONB NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NULL,
                UNIQUE (seller_external_id, seller_name, store_id, store_name, month)
            );
        """))
        await self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS seller_shift_schedules (
                id VARCHAR(64) PRIMARY KEY,
                shift_date DATE NOT NULL,
                seller_external_id VARCHAR(255) NULL,
                seller_name VARCHAR(255) NOT NULL,
                store_id VARCHAR(255) NULL,
                store_name VARCHAR(255) NULL,
                starts_at TIME NULL,
                ends_at TIME NULL,
                note TEXT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NULL
            );
        """))
        await self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS seller_kpi_target_plans (
                id VARCHAR(64) PRIMARY KEY,
                month DATE NOT NULL,
                scope_type VARCHAR(32) NOT NULL DEFAULT 'global',
                scope_key VARCHAR(255) NOT NULL DEFAULT 'all',
                metric_key VARCHAR(64) NOT NULL,
                plan_value NUMERIC(18, 6) NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NULL,
                UNIQUE (month, scope_type, scope_key, metric_key)
            );
        """))
        await self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS seller_kpi_assortment_guidance (
                id VARCHAR(64) PRIMARY KEY,
                store_id VARCHAR(255) NULL,
                store_name VARCHAR(255) NOT NULL,
                month DATE NOT NULL,
                assortment_block VARCHAR(255) NOT NULL,
                current_stock NUMERIC(18, 2) NOT NULL DEFAULT 0,
                incoming NUMERIC(18, 2) NOT NULL DEFAULT 0,
                available_to_sell NUMERIC(18, 2) NOT NULL DEFAULT 0,
                share NUMERIC(12, 6) NOT NULL DEFAULT 0,
                sales_guidance NUMERIC(18, 2) NOT NULL DEFAULT 0,
                stock_after_guidance NUMERIC(18, 2) NOT NULL DEFAULT 0,
                comment TEXT NULL,
                soft_guidance BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NULL,
                UNIQUE (store_name, month, assortment_block)
            );
        """))
        # Do not run ALTER TABLE from request-time ensure_tables().
        # It takes AccessExclusiveLock and concurrent KPI page loads can deadlock.
        # Precision migrations must be applied once via deploy/migration script, not on every read.
        await self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS seller_kpi_daily_snapshots (
                id VARCHAR(64) PRIMARY KEY,
                snapshot_date DATE NOT NULL,
                month DATE NOT NULL,
                scope VARCHAR(32) NOT NULL DEFAULT 'all',
                rows JSONB NOT NULL,
                totals JSONB NOT NULL,
                stores JSONB NOT NULL,
                sellers JSONB NOT NULL,
                insights JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NULL,
                UNIQUE (snapshot_date, month, scope)
            );
        """))
        await self.db.execute(text("CREATE INDEX IF NOT EXISTS ix_seller_monthly_plans_month ON seller_monthly_plans(month);"))
        await self.db.execute(text("CREATE INDEX IF NOT EXISTS ix_seller_shift_schedules_date ON seller_shift_schedules(shift_date);"))
        await self.db.execute(text("CREATE INDEX IF NOT EXISTS ix_seller_kpi_target_plans_month ON seller_kpi_target_plans(month);"))
        await self.db.execute(text("CREATE INDEX IF NOT EXISTS ix_seller_kpi_assortment_guidance_month_store ON seller_kpi_assortment_guidance(month, store_name);"))
        await self.db.execute(text("CREATE INDEX IF NOT EXISTS ix_seller_kpi_daily_snapshots_month ON seller_kpi_daily_snapshots(month, snapshot_date);"))
        await self.db.commit()

    @staticmethod
    def month_range(month: Optional[str] = None) -> tuple[date, datetime, datetime]:
        if month:
            month_date = datetime.strptime(month[:7], "%Y-%m").date().replace(day=1)
        else:
            today = date.today()
            month_date = today.replace(day=1)
        if month_date.month == 12:
            next_month = month_date.replace(year=month_date.year + 1, month=1)
        else:
            next_month = month_date.replace(month=month_date.month + 1)
        return month_date, datetime.combine(month_date, time.min), datetime.combine(next_month, time.min)

    @staticmethod
    def period_range(start_date: Optional[str], end_date: Optional[str]) -> tuple[date, date]:
        today = date.today()
        start = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else today.replace(day=1)
        end = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today
        return start, end

    async def sales_by_seller(self, start_dt: datetime, end_dt: datetime, seller_external_id: Optional[str] = None, seller_name: Optional[str] = None) -> List[Dict[str, Any]]:
        where = ["sr.sale_date >= :start_dt", "sr.sale_date < :end_dt"]
        params: Dict[str, Any] = {"start_dt": start_dt, "end_dt": end_dt}
        if seller_external_id:
            where.append(f"{SELLER_KEY_EXPR} = :seller_external_id")
            params["seller_external_id"] = seller_external_id
        elif seller_name:
            where.append(f"LOWER({SELLER_DISPLAY_NAME_EXPR}) = LOWER(:seller_name)")
            params["seller_name"] = seller_name

        result = await self.db.execute(text(f"""
            SELECT
                {SELLER_KEY_EXPR} AS seller_external_id,
                {SELLER_DISPLAY_NAME_EXPR} AS seller_name,
                sr.store_id AS store_id,
                {STORE_EXPR} AS store_name,
                SUM(CASE WHEN {KPI_ELIGIBLE_PRODUCT_SQL} THEN sr.revenue ELSE 0 END) AS revenue,
                COUNT(DISTINCT CASE WHEN {KPI_ELIGIBLE_PRODUCT_SQL} THEN sr.document_id ELSE NULL END) AS checks,
                SUM(CASE WHEN {KPI_ELIGIBLE_PRODUCT_SQL} THEN sr.quantity ELSE 0 END) AS items_sold
            FROM sales_records sr
            LEFT JOIN stores s ON s.external_id = sr.store_id
            LEFT JOIN products p ON p.external_id = sr.product_id
            WHERE {' AND '.join(where)}
            GROUP BY 1, 2, 3, 4
            HAVING SUM(CASE WHEN {KPI_ELIGIBLE_PRODUCT_SQL} THEN sr.revenue ELSE 0 END) <> 0
                OR SUM(CASE WHEN {KPI_ELIGIBLE_PRODUCT_SQL} THEN sr.quantity ELSE 0 END) <> 0
            ORDER BY revenue DESC NULLS LAST
        """), params)
        return [dict(row._mapping) for row in result.fetchall()]

    async def plans_for_month(self, month: date) -> List[Dict[str, Any]]:
        await self.ensure_tables()
        result = await self.db.execute(text("""
            SELECT id::text, seller_external_id, seller_name, store_id, store_name, month,
                   revenue_plan::float AS revenue_plan, checks_plan, items_plan::float AS items_plan, source
            FROM seller_monthly_plans
            WHERE month = :month
            ORDER BY store_name NULLS LAST, seller_name
        """), {"month": month})
        return [dict(row._mapping) for row in result.fetchall()]

    @staticmethod
    def _normalize_seller_identity(value: Optional[str]) -> str:
        return " ".join((value or "").strip().lower().replace("ё", "е").split())

    @classmethod
    def _seller_identity_candidates(cls, current_user: User) -> Dict[str, set[str]]:
        preferences = getattr(current_user, "preferences", None) or {}
        if not isinstance(preferences, dict):
            preferences = {}
        names = {
            cls._normalize_seller_identity(getattr(current_user, "full_name", None)),
            cls._normalize_seller_identity(preferences.get("seller_name")),
            cls._normalize_seller_identity(preferences.get("staff_name")),
            cls._normalize_seller_identity(preferences.get("onec_seller_name")),
        }
        email = (getattr(current_user, "email", None) or "").split("@")[0].replace(".", " ").replace("_", " ").replace("-", " ")
        names.add(cls._normalize_seller_identity(email))
        names.discard("")
        external_ids = {
            str(preferences.get("seller_external_id") or "").strip(),
            str(preferences.get("onec_seller_id") or "").strip(),
            str(preferences.get("employee_external_id") or "").strip(),
        }
        external_ids.discard("")
        external_ids.discard(ZERO_GUID)
        return {"names": names, "external_ids": external_ids}

    @classmethod
    def _matches_seller_identity(cls, row: Dict[str, Any], current_user: User) -> bool:
        candidates = cls._seller_identity_candidates(current_user)
        row_external_id = str(row.get("seller_external_id") or "").strip()
        if row_external_id and row_external_id in candidates["external_ids"]:
            return True
        row_name = cls._normalize_seller_identity(row.get("seller_name"))
        if not row_name:
            return False
        return any(row_name == candidate or row_name in candidate or candidate in row_name for candidate in candidates["names"])

    async def kpi_overview(self, current_user: User, month: Optional[str] = None, store_name: Optional[str] = None) -> Dict[str, Any]:
        month_date, start_dt, end_dt = self.month_range(month)
        role = (getattr(current_user, "role", None) or "").lower()
        is_admin_view = role in {"admin", "manager"}

        sales = await self.sales_by_seller(start_dt, end_dt)
        history_seller_sales = await self._history_seller_kpi_values(month_date, store_name=store_name if is_admin_view else None)
        if history_seller_sales:
            current_store_keys = {(row.get("store_name") or row.get("store_id") or "").strip().lower() for row in sales}
            # 1C sales_records is the operational source of truth. Imported ЕО seller
            # sheets are only a historical fallback for periods/stores where the platform
            # has no synchronized 1C rows at all; do not mask current platform facts.
            sales.extend([
                row for row in history_seller_sales
                if (row.get("store_name") or row.get("store_id") or "").strip().lower() not in current_store_keys
            ])
        for sale in sales:
            seller_id = (sale.get("seller_external_id") or "").strip()
            if not sale.get("seller_name") and seller_id in KNOWN_SELLER_NAMES_BY_EXTERNAL_ID:
                sale["seller_name"] = KNOWN_SELLER_NAMES_BY_EXTERNAL_ID[seller_id]
            elif not sale.get("seller_name") and (not seller_id or seller_id == ZERO_GUID):
                sale["seller_name"] = "Не сопоставлено с продавцом"
        plans = await self.plans_for_month(month_date)
        shift_stats = await self._shift_stats_by_seller(start_dt.date(), (end_dt - timedelta(days=1)).date(), store_name=store_name if is_admin_view else None)
        shift_stats_for_plan = shift_stats
        if not shift_stats_for_plan:
            # On the first days of a new month the store plan may already exist while
            # the current month schedule/sales rows are still empty. Keep the seller
            # plan/fact table useful by using the latest previous schedule as the
            # roster/hour-share source, then apply the requested month store targets.
            shift_stats_for_plan = await self._latest_shift_stats_by_seller_before_month(month_date, store_name=store_name if is_admin_view else None)

        if not is_admin_view:
            sales = [row for row in sales if self._matches_seller_identity(row, current_user)]
            plans = [row for row in plans if self._matches_seller_identity(row, current_user)]
            shift_stats = [row for row in shift_stats if self._matches_seller_identity(row, current_user)]
        elif store_name:
            store_filter = store_name.strip().lower()
            sales = [row for row in sales if (row.get("store_name") or "").strip().lower() == store_filter]
            plans = [row for row in plans if (row.get("store_name") or "").strip().lower() == store_filter]

        plan_by_key: Dict[str, Dict[str, Any]] = {}
        for plan in await self._formula_seller_plans(month_date, shift_stats_for_plan):
            key = self._seller_key(plan.get("seller_external_id"), plan.get("seller_name"), plan.get("store_id"), plan.get("store_name"))
            plan_by_key[key] = plan
        for plan in plans:
            key = self._seller_key(plan.get("seller_external_id"), plan.get("seller_name"), plan.get("store_id"), plan.get("store_name"))
            if float(plan.get("revenue_plan") or 0) > 0 or plan.get("checks_plan") is not None or plan.get("items_plan") is not None:
                plan_by_key[key] = plan

        rows: Dict[str, Dict[str, Any]] = {}
        for sale in sales:
            key = self._seller_key(sale.get("seller_external_id"), sale.get("seller_name"), sale.get("store_id"), sale.get("store_name"))
            rows[key] = {
                **sale,
                "revenue": float(sale.get("revenue") or 0),
                "checks": int(sale.get("checks") or 0),
                "items_sold": float(sale.get("items_sold") or 0),
                "revenue_plan": 0.0,
                "checks_plan": None,
                "completion_percent": None,
            }

        for key, plan in plan_by_key.items():
            row = rows.setdefault(key, {
                "seller_external_id": plan.get("seller_external_id"),
                "seller_name": plan.get("seller_name"),
                "store_id": plan.get("store_id"),
                "store_name": plan.get("store_name"),
                "revenue": 0.0,
                "checks": 0,
                "items_sold": 0.0,
            })
            row["revenue_plan"] = float(plan.get("revenue_plan") or 0)
            row["checks_plan"] = plan.get("checks_plan")
            row["items_plan"] = plan.get("items_plan")
            for optional_key in (
                "shifts_plan",
                "hours_plan",
                "avg_check_plan",
                "avg_item_price_plan",
                "items_per_check_plan",
                "avg_sales_per_shift_plan",
                "traffic_plan",
                "revenue_per_visitor_plan",
                "conversion_plan",
                "plan_source",
            ):
                if optional_key in plan:
                    row[optional_key] = plan.get(optional_key)
            if row["revenue_plan"]:
                row["completion_percent"] = round(row["revenue"] / row["revenue_plan"] * 100, 1)

        seller_rows = sorted(rows.values(), key=lambda r: r.get("revenue", 0), reverse=True)
        totals = {
            "revenue": round(sum(float(r.get("revenue") or 0) for r in seller_rows), 2),
            "revenue_plan": round(sum(float(r.get("revenue_plan") or 0) for r in seller_rows), 2),
            "checks": sum(int(r.get("checks") or 0) for r in seller_rows),
        }
        totals["completion_percent"] = round(totals["revenue"] / totals["revenue_plan"] * 100, 1) if totals["revenue_plan"] else None

        store_rows: Dict[str, Dict[str, Any]] = {}
        for row in seller_rows:
            display_store_name = row.get("store_name") or "Без магазина"
            store_key = display_store_name.strip().lower() if display_store_name else (row.get("store_id") or "Без магазина")
            store = store_rows.setdefault(store_key, {
                "store_id": row.get("store_id"),
                "store_name": display_store_name,
                "revenue": 0.0,
                "revenue_plan": 0.0,
                "checks": 0,
            })
            if not store.get("store_id") and row.get("store_id"):
                store["store_id"] = row.get("store_id")
            if store.get("store_name") == "Без магазина" and row.get("store_name"):
                store["store_name"] = row.get("store_name")
            store["revenue"] += float(row.get("revenue") or 0)
            store["revenue_plan"] += float(row.get("revenue_plan") or 0)
            store["checks"] += int(row.get("checks") or 0)
        for store in store_rows.values():
            store["revenue"] = round(store["revenue"], 2)
            store["revenue_plan"] = round(store["revenue_plan"], 2)
            store["completion_percent"] = round(store["revenue"] / store["revenue_plan"] * 100, 1) if store["revenue_plan"] else None

        return {
            "month": month_date.isoformat(),
            "scope": "all" if is_admin_view else "self",
            "totals": totals,
            "sellers": seller_rows,
            "stores": sorted(store_rows.values(), key=lambda r: r.get("revenue", 0), reverse=True),
            "seller_field_status": "ok" if any(r.get("seller_name") or r.get("seller_external_id") for r in seller_rows) else "missing_in_sales_records",
        }

    async def shifts(self, start_date: Optional[str], end_date: Optional[str], store_name: Optional[str] = None) -> Dict[str, Any]:
        await self.ensure_tables()
        start, end = self.period_range(start_date, end_date)
        where_store = "AND LOWER(COALESCE(store_name, '')) = LOWER(:store_name)" if store_name else ""
        result = await self.db.execute(text(f"""
            SELECT id::text, shift_date, seller_external_id, seller_name, store_id, store_name,
                   starts_at, ends_at, note
            FROM seller_shift_schedules
            WHERE shift_date BETWEEN :start_date AND :end_date
            {where_store}
            ORDER BY shift_date, store_name NULLS LAST, starts_at NULLS LAST, seller_name
        """), {"start_date": start, "end_date": end, "store_name": store_name})
        rows = [dict(row._mapping) for row in result.fetchall()]
        for row in rows:
            for key in ("shift_date", "starts_at", "ends_at"):
                if row.get(key) is not None:
                    row[key] = str(row[key])
        return {"start_date": start.isoformat(), "end_date": end.isoformat(), "shifts": rows}

    async def upsert_shift(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await self.ensure_tables()
        shift_id = payload.get("id")
        params = {
            "shift_date": payload.get("shift_date"),
            "seller_external_id": payload.get("seller_external_id"),
            "seller_name": payload.get("seller_name") or "Без имени",
            "store_id": payload.get("store_id"),
            "store_name": payload.get("store_name"),
            "starts_at": payload.get("starts_at"),
            "ends_at": payload.get("ends_at"),
            "note": payload.get("note"),
        }
        if shift_id:
            params["id"] = shift_id
            await self.db.execute(text("""
                UPDATE seller_shift_schedules
                SET shift_date=:shift_date, seller_external_id=:seller_external_id, seller_name=:seller_name,
                    store_id=:store_id, store_name=:store_name, starts_at=:starts_at, ends_at=:ends_at,
                    note=:note, updated_at=NOW()
                WHERE id=:id
            """), params)
        else:
            params["id"] = str(uuid4())
            await self.db.execute(text("""
                INSERT INTO seller_shift_schedules (id, shift_date, seller_external_id, seller_name, store_id, store_name, starts_at, ends_at, note)
                VALUES (:id, :shift_date, :seller_external_id, :seller_name, :store_id, :store_name, :starts_at, :ends_at, :note)
            """), params)
        await self.db.commit()
        return {"success": True}

    async def delete_shift(self, shift_id: str) -> Dict[str, Any]:
        await self.ensure_tables()
        await self.db.execute(text("DELETE FROM seller_shift_schedules WHERE id=:id"), {"id": shift_id})
        await self.db.commit()
        return {"success": True}

    async def import_shift_rows(self, parsed: Dict[str, Any], *, dry_run: bool = True, replace_existing: bool = False) -> Dict[str, Any]:
        """Import parsed Excel schedule rows into seller_shift_schedules.

        Dry-run returns preview only. Apply mode removes previous Excel-imported
        rows for the same store/month before inserting new rows; manual shifts are
        preserved unless replace_existing=True.
        """
        shifts = parsed.get("shifts") or []
        if not isinstance(shifts, list):
            raise ValueError("shifts должен быть массивом")
        period_month = datetime.strptime(str(parsed.get("period_month"))[:7], "%Y-%m").date().replace(day=1)
        next_month = period_month.replace(year=period_month.year + 1, month=1) if period_month.month == 12 else period_month.replace(month=period_month.month + 1)
        store_name = (parsed.get("store_name") or "").strip()
        if not store_name:
            raise ValueError("Укажите магазин для импорта графика")
        preview = shifts[:20]
        if dry_run:
            return {"success": True, "dry_run": True, "parsed": len(shifts), "saved": 0, "period_month": period_month.isoformat()[:7], "store_name": store_name, "preview": preview, "stats": parsed.get("stats") or {}}

        await self.ensure_tables()
        delete_where = "shift_date >= :start_date AND shift_date < :end_date AND LOWER(COALESCE(store_name, '')) = LOWER(:store_name)"
        params: Dict[str, Any] = {"start_date": period_month, "end_date": next_month, "store_name": store_name}
        if not replace_existing:
            delete_where += " AND COALESCE(note, '') LIKE 'Импорт из Excel %'"
        deleted = await self.db.execute(text(f"DELETE FROM seller_shift_schedules WHERE {delete_where}"), params)
        saved = 0
        for row in shifts:
            seller_name = (row.get("seller_name") or "").strip()
            if not seller_name:
                continue
            normalized_name = self._normalize_seller_name(seller_name)
            await self.db.execute(text("""
                INSERT INTO seller_shift_schedules
                    (id, shift_date, seller_external_id, seller_name, store_id, store_name, starts_at, ends_at, note)
                VALUES (:id, :shift_date, :seller_external_id, :seller_name, :store_id, :store_name, :starts_at, :ends_at, :note)
            """), {
                "id": str(uuid4()),
                "shift_date": row.get("shift_date"),
                "seller_external_id": row.get("seller_external_id") or KNOWN_SELLER_EXTERNAL_IDS_BY_NORMALIZED_NAME.get(normalized_name),
                "seller_name": seller_name,
                "store_id": row.get("store_id"),
                "store_name": store_name,
                "starts_at": row.get("starts_at"),
                "ends_at": row.get("ends_at"),
                "note": row.get("note"),
            })
            saved += 1
        await self.db.commit()
        return {
            "success": True,
            "dry_run": False,
            "parsed": len(shifts),
            "saved": saved,
            "deleted_previous": getattr(deleted, "rowcount", None),
            "period_month": period_month.isoformat()[:7],
            "store_name": store_name,
            "stats": parsed.get("stats") or {},
            "preview": preview,
        }

    async def dashboard(self, current_user: User, month: Optional[str] = None) -> Dict[str, Any]:
        """All-store management KPI dashboard for admin/manager."""
        month_date, start_dt, end_dt = self.month_range(month)
        overview = await self.kpi_overview(current_user=current_user, month=month, store_name=None)
        seller_rows = overview.get("sellers", [])
        store_names = sorted({
            row.get("store_name") for row in seller_rows if row.get("store_name")
        } | {"ТРК Центрум", "Ялта, Набережная 18", "Меганом"})

        days_in_month = ((month_date.replace(year=month_date.year + 1, month=1) if month_date.month == 12 else month_date.replace(month=month_date.month + 1)) - month_date).days
        today = date.today()
        if today.year == month_date.year and today.month == month_date.month:
            elapsed_days = max(1, min(today.day, days_in_month))
        elif today >= end_dt.date():
            elapsed_days = days_in_month
        else:
            elapsed_days = 1

        metric_matrix: List[Dict[str, Any]] = []
        dashboard_stores: List[Dict[str, Any]] = []
        all_metric_totals: Dict[str, Dict[str, float]] = {}
        for store in store_names:
            store_sellers = [row for row in seller_rows if (row.get("store_name") or "").strip().lower() == store.strip().lower()]
            if not store_sellers and store == "Меганом":
                # Keep a visible empty store only if it has plan/fact later; otherwise skip in MVP data.
                continue
            store_targets = await self._target_metric_plans(month_date, store_name=store)
            store_target_sources = await self._target_metric_plan_sources(month_date, store_name=store)
            revenue_plan_source_row = next((row for row in store_target_sources if row.get("metric_key") == "revenue"), None)
            shifts_count = await self._shift_count(start_dt.date(), (end_dt - timedelta(days=1)).date(), store_name=store)
            store_facts = await self._sales_fact_totals(start_dt, end_dt, store_name=store)
            revenue = float(store_facts["revenue"] or 0)
            seller_revenue_plan = sum(float(row.get("revenue_plan") or 0) for row in store_sellers)
            revenue_plan = float(store_targets.get("revenue") or 0) or seller_revenue_plan
            revenue_plan_source = "target_metric_plan" if float(store_targets.get("revenue") or 0) > 0 else "seller_monthly_plans_sum" if seller_revenue_plan > 0 else None
            revenue_plan_matching_status = "matched_confirmed" if revenue_plan > 0 else "missing_or_unconfirmed"
            checks = int(store_facts["checks"] or 0)
            items = float(store_facts["items_sold"] or 0)
            forecast_revenue = revenue / elapsed_days * days_in_month if elapsed_days else None
            completion_percent = revenue / revenue_plan * 100 if revenue_plan else None
            forecast_percent = forecast_revenue / revenue_plan * 100 if forecast_revenue is not None and revenue_plan else None
            risk_level = "critical" if forecast_percent is not None and forecast_percent < 75 else "warning" if forecast_percent is not None and forecast_percent < 100 else "ok"
            store_row = {
                "store_name": store,
                "store_id": next((row.get("store_id") for row in store_sellers if row.get("store_id")), None),
                "revenue": round(revenue, 2),
                "revenue_plan": round(revenue_plan, 2),
                "revenue_plan_source": revenue_plan_source,
                "revenue_plan_period": month_date.isoformat()[:7],
                "revenue_plan_store": store,
                "revenue_plan_matching_status": revenue_plan_matching_status,
                "revenue_plan_source_detail": revenue_plan_source_row,
                "completion_percent": round(completion_percent, 2) if completion_percent is not None else None,
                "forecast_revenue": round(forecast_revenue, 2) if forecast_revenue is not None else None,
                "forecast_percent": round(forecast_percent, 2) if forecast_percent is not None else None,
                "checks": checks,
                "items_sold": round(items, 2),
                "shifts_count": shifts_count,
                "avg_check": round(revenue / checks, 2) if checks else None,
                "avg_item_price": round(revenue / items, 2) if items else None,
                "items_per_check": round(items / checks, 2) if checks else None,
                "avg_sales_per_shift": round(revenue / shifts_count, 2) if shifts_count else None,
                "sellers_count": len([row for row in store_sellers if row.get("seller_name") or row.get("seller_external_id")]),
                "risk_level": risk_level,
            }
            dashboard_stores.append(store_row)

            metrics: Dict[str, Dict[str, Any]] = {}
            metric_facts = {
                "revenue": revenue,
                "items_count": items,
                "checks_count": checks,
                "avg_check": store_row["avg_check"],
                "avg_item_price": store_row["avg_item_price"],
                "items_per_check": store_row["items_per_check"],
                "shifts_count": shifts_count,
                "avg_sales_per_shift": store_row["avg_sales_per_shift"],
            }
            for metric in self._target_metric_defs():
                key = metric["key"]
                fact = metric_facts.get(key)
                plan = store_targets.get(key)
                percent = fact / plan * 100 if isinstance(fact, (int, float)) and plan else None
                metrics[key] = {"fact": round(fact, 2) if isinstance(fact, (int, float)) else None, "plan": round(plan, 2) if isinstance(plan, (int, float)) else None, "percent": round(percent, 2) if percent is not None else None}
                if isinstance(fact, (int, float)) or isinstance(plan, (int, float)):
                    bucket = all_metric_totals.setdefault(key, {"fact": 0.0, "plan": 0.0})
                    bucket["fact"] += float(fact or 0)
                    bucket["plan"] += float(plan or 0)
            metric_matrix.append({"store_name": store, "metrics": metrics})

        dashboard_stores.sort(key=lambda row: row.get("revenue") or 0, reverse=True)
        totals = {
            "revenue": round(sum(float(row.get("revenue") or 0) for row in dashboard_stores), 2),
            "revenue_plan": round(sum(float(row.get("revenue_plan") or 0) for row in dashboard_stores), 2),
            "checks": sum(int(row.get("checks") or 0) for row in dashboard_stores),
            "items_sold": round(sum(float(row.get("items_sold") or 0) for row in dashboard_stores), 2),
            "shifts_count": sum(int(row.get("shifts_count") or 0) for row in dashboard_stores),
        }
        totals["completion_percent"] = round(totals["revenue"] / totals["revenue_plan"] * 100, 2) if totals["revenue_plan"] else None
        totals["forecast_revenue"] = round(totals["revenue"] / elapsed_days * days_in_month, 2) if elapsed_days else None
        totals["forecast_percent"] = round(totals["forecast_revenue"] / totals["revenue_plan"] * 100, 2) if totals.get("forecast_revenue") and totals["revenue_plan"] else None
        totals["avg_check"] = round(totals["revenue"] / totals["checks"], 2) if totals["checks"] else None
        totals["avg_item_price"] = round(totals["revenue"] / totals["items_sold"], 2) if totals["items_sold"] else None
        totals["items_per_check"] = round(totals["items_sold"] / totals["checks"], 2) if totals["checks"] else None
        totals["avg_sales_per_shift"] = round(totals["revenue"] / totals["shifts_count"], 2) if totals["shifts_count"] else None

        metric_totals = {}
        for key, values in all_metric_totals.items():
            metric_totals[key] = {
                "fact": round(values["fact"], 2),
                "plan": round(values["plan"], 2) if values["plan"] else None,
                "percent": round(values["fact"] / values["plan"] * 100, 2) if values["plan"] else None,
            }

        unmatched = [row for row in seller_rows if not row.get("seller_name") or (row.get("seller_name") or "").lower() in {"без имени", "не сопоставлено с продавцом"}]
        normalized_store_names = [(row.get("store_name") or "").strip().lower() for row in overview.get("stores", [])]
        duplicate_store_rows = len(normalized_store_names) - len(set(normalized_store_names))
        insights = self._build_insights(
            [{"key": key, "label": key, "editable_plan": True, **value} for key, value in metric_totals.items()],
            dashboard_stores,
            seller_rows,
        )
        for store in dashboard_stores:
            if store.get("forecast_percent") is not None and store["forecast_percent"] < 100:
                insights.insert(0, {
                    "type": "forecast_risk",
                    "severity": "critical" if store["forecast_percent"] < 75 else "warning",
                    "title": f"{store['store_name']}: риск невыполнения плана",
                    "text": f"Прогноз {store['forecast_percent']}% при текущем темпе. Проверьте средний чек, конверсию, длину чека и распределение смен.",
                })
        plan_warnings = [
            {
                "code": "store_plan_missing_or_unconfirmed",
                "store_name": store.get("store_name"),
                "period": month_date.isoformat()[:7],
                "message": f"План магазина {store.get('store_name')} за {month_date.isoformat()[:7]} не загружен или не подтвержден; выполнение плана нельзя использовать для управленческих выводов.",
            }
            for store in dashboard_stores
            if store.get("revenue_plan_matching_status") != "matched_confirmed"
        ]
        return {
            "month": month_date.isoformat(),
            "elapsed_days": elapsed_days,
            "days_in_month": days_in_month,
            "totals": totals,
            "stores": dashboard_stores,
            "sellers": seller_rows,
            "metric_totals": metric_totals,
            "metric_matrix": metric_matrix,
            "insights": insights[:10],
            "data_quality": {
                "unmatched_sellers": len(unmatched),
                "duplicate_store_rows": max(0, duplicate_store_rows),
                "seller_field_status": overview.get("seller_field_status"),
                "plan_warnings": plan_warnings,
            },
        }

    async def _ensure_history_tables(self) -> None:
        """Historical ЕО plan/fact staging tables for archive analysis."""
        await self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS seller_kpi_store_plan_fact_imports (
                id VARCHAR(64) PRIMARY KEY,
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
            );
        """))
        await self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS seller_kpi_store_plan_fact_rows (
                id VARCHAR(64) PRIMARY KEY,
                import_id VARCHAR(64) NOT NULL REFERENCES seller_kpi_store_plan_fact_imports(id) ON DELETE CASCADE,
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
            );
        """))
        for table_sql in [
            """
            CREATE TABLE IF NOT EXISTS seller_kpi_store_plan_fact_daily_rows (
                id VARCHAR(64) PRIMARY KEY,
                import_id VARCHAR(64) NOT NULL REFERENCES seller_kpi_store_plan_fact_imports(id) ON DELETE CASCADE,
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
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS seller_kpi_store_plan_fact_summary_rows (
                id VARCHAR(64) PRIMARY KEY,
                import_id VARCHAR(64) NOT NULL REFERENCES seller_kpi_store_plan_fact_imports(id) ON DELETE CASCADE,
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
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS seller_kpi_store_plan_fact_schedule_rows (
                id VARCHAR(64) PRIMARY KEY,
                import_id VARCHAR(64) NOT NULL REFERENCES seller_kpi_store_plan_fact_imports(id) ON DELETE CASCADE,
                store_name TEXT NOT NULL,
                period_month DATE NOT NULL,
                source_sheet TEXT NOT NULL,
                row_number INTEGER NOT NULL,
                raw_row JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (import_id, source_sheet, row_number)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS seller_kpi_store_plan_fact_sheet_rows (
                id VARCHAR(64) PRIMARY KEY,
                import_id VARCHAR(64) NOT NULL REFERENCES seller_kpi_store_plan_fact_imports(id) ON DELETE CASCADE,
                store_name TEXT NOT NULL,
                period_month DATE NOT NULL,
                source_sheet TEXT NOT NULL,
                row_number INTEGER NOT NULL,
                raw_row JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (import_id, source_sheet, row_number)
            );
            """,
        ]:
            await self.db.execute(text(table_sql))
        await self.db.execute(text("CREATE INDEX IF NOT EXISTS ix_seller_kpi_history_rows_lookup ON seller_kpi_store_plan_fact_rows(store_name, period_month, metric_key);"))
        await self.db.execute(text("CREATE INDEX IF NOT EXISTS ix_seller_kpi_history_imports_period ON seller_kpi_store_plan_fact_imports(store_name, period_month);"))
        await self.db.commit()

    async def import_plan_fact_history(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Import parsed historical ЕО rows with provenance. Admin-only API wrapper."""
        await self.ensure_tables()
        await self._ensure_history_tables()
        imports = payload.get("imports") or []
        if not isinstance(imports, list):
            raise ValueError("imports должен быть массивом")
        stats = {"imports": 0, "metric_rows": 0, "daily_rows": 0, "summary_rows": 0, "schedule_rows": 0, "raw_rows": 0, "target_plans": 0}
        allowed = {metric["key"] for metric in self._target_metric_defs()}
        for item in imports:
            store_name = (item.get("store_name") or "").strip()
            store_slug = (item.get("store_slug") or "").strip()
            period_month = datetime.strptime(str(item.get("period_month"))[:7], "%Y-%m").date().replace(day=1)
            source_file = item.get("source_file") or "unknown.xlsx"
            source_sheet = item.get("source_sheet")
            source_hash = item.get("source_hash") or str(uuid4())
            metadata = item.get("raw_metadata") or {}
            import_id = str(uuid4())
            result = await self.db.execute(text("""
                INSERT INTO seller_kpi_store_plan_fact_imports
                    (id, store_name, store_slug, period_month, source_file, source_sheet, source_hash, import_status, raw_metadata, updated_at)
                VALUES (:id, :store_name, :store_slug, :period_month, :source_file, :source_sheet, :source_hash, 'parsed', CAST(:raw_metadata AS jsonb), NOW())
                ON CONFLICT (store_name, period_month, source_hash)
                DO UPDATE SET source_file=EXCLUDED.source_file, source_sheet=EXCLUDED.source_sheet,
                              import_status='parsed', raw_metadata=EXCLUDED.raw_metadata, updated_at=NOW()
                RETURNING id
            """), {
                "id": import_id,
                "store_name": store_name,
                "store_slug": store_slug,
                "period_month": period_month,
                "source_file": source_file,
                "source_sheet": source_sheet,
                "source_hash": source_hash,
                "raw_metadata": json.dumps(metadata, ensure_ascii=False),
            })
            import_id = str(result.scalar_one())
            for table in [
                "seller_kpi_store_plan_fact_rows",
                "seller_kpi_store_plan_fact_daily_rows",
                "seller_kpi_store_plan_fact_summary_rows",
                "seller_kpi_store_plan_fact_schedule_rows",
                "seller_kpi_store_plan_fact_sheet_rows",
            ]:
                await self.db.execute(text(f"DELETE FROM {table} WHERE import_id=:import_id"), {"import_id": import_id})
            for row in item.get("metric_rows") or []:
                metric_key = row.get("metric_key")
                await self.db.execute(text("""
                    INSERT INTO seller_kpi_store_plan_fact_rows
                        (id, import_id, store_name, period_month, metric_key, metric_label, plan_value, fact_value,
                         completion_percent, forecast_value, forecast_percent, deviation_value, last_year_fact_value,
                         lfl_deviation_value, raw_row)
                    VALUES (:id, :import_id, :store_name, :period_month, :metric_key, :metric_label, :plan_value, :fact_value,
                            :completion_percent, :forecast_value, :forecast_percent, :deviation_value, :last_year_fact_value,
                            :lfl_deviation_value, CAST(:raw_row AS jsonb))
                """), {**row, "id": str(uuid4()), "import_id": import_id, "store_name": store_name, "period_month": period_month, "raw_row": json.dumps(row.get("raw_row") or {}, ensure_ascii=False)})
                stats["metric_rows"] += 1
                if metric_key in allowed and row.get("plan_value") is not None:
                    await self.db.execute(text("""
                        INSERT INTO seller_kpi_target_plans (id, month, scope_type, scope_key, metric_key, plan_value, updated_at)
                        VALUES (:id, :month, 'store', :scope_key, :metric_key, :plan_value, NOW())
                        ON CONFLICT (month, scope_type, scope_key, metric_key)
                        DO UPDATE SET plan_value=EXCLUDED.plan_value, updated_at=NOW()
                    """), {"id": str(uuid4()), "month": period_month, "scope_key": store_name, "metric_key": metric_key, "plan_value": row.get("plan_value")})
                    stats["target_plans"] += 1
            for row in item.get("daily_rows") or []:
                await self.db.execute(text("""
                    INSERT INTO seller_kpi_store_plan_fact_daily_rows
                        (id, import_id, store_name, period_month, sale_date, seller_names, weekday, revenue, items_count,
                         avg_item_price, checks_count, avg_check, traffic, items_per_check, conversion, raw_row)
                    VALUES (:id, :import_id, :store_name, :period_month, :sale_date, :seller_names, :weekday, :revenue, :items_count,
                            :avg_item_price, :checks_count, :avg_check, :traffic, :items_per_check, :conversion, CAST(:raw_row AS jsonb))
                """), {**row, "id": str(uuid4()), "import_id": import_id, "store_name": store_name, "period_month": period_month, "raw_row": json.dumps(row.get("raw_row") or {}, ensure_ascii=False)})
                stats["daily_rows"] += 1
            for table_key, table_name, extra_fields in [
                ("summary_rows", "seller_kpi_store_plan_fact_summary_rows", ["metric_key", "metric_label", "headers"]),
                ("schedule_rows", "seller_kpi_store_plan_fact_schedule_rows", []),
                ("raw_rows", "seller_kpi_store_plan_fact_sheet_rows", []),
            ]:
                for row in item.get(table_key) or []:
                    params = {**row, "id": str(uuid4()), "import_id": import_id, "store_name": store_name, "period_month": period_month,
                              "headers": json.dumps(row.get("headers") or {}, ensure_ascii=False),
                              "raw_row": json.dumps(row.get("raw_row") or {}, ensure_ascii=False)}
                    if table_key == "summary_rows":
                        await self.db.execute(text(f"""
                            INSERT INTO {table_name}
                                (id, import_id, store_name, period_month, source_sheet, row_number, metric_key, metric_label, headers, raw_row)
                            VALUES (:id, :import_id, :store_name, :period_month, :source_sheet, :row_number, :metric_key, :metric_label, CAST(:headers AS jsonb), CAST(:raw_row AS jsonb))
                        """), params)
                    else:
                        await self.db.execute(text(f"""
                            INSERT INTO {table_name}
                                (id, import_id, store_name, period_month, source_sheet, row_number, raw_row)
                            VALUES (:id, :import_id, :store_name, :period_month, :source_sheet, :row_number, CAST(:raw_row AS jsonb))
                        """), params)
                    stats[table_key] += 1
            stats["imports"] += 1
        await self.db.commit()
        return {"success": True, "stats": stats}

    async def _history_metric_values(self, month: date, store_name: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        if not store_name:
            return {}
        await self._ensure_history_tables()
        result = await self.db.execute(text("""
            SELECT DISTINCT ON (r.metric_key)
                r.metric_key,
                r.plan_value::float AS plan_value,
                r.fact_value::float AS fact_value,
                r.completion_percent::float AS completion_percent,
                r.forecast_value::float AS forecast_value,
                r.forecast_percent::float AS forecast_percent,
                r.deviation_value::float AS deviation_value,
                r.last_year_fact_value::float AS last_year_fact_value,
                r.lfl_deviation_value::float AS lfl_deviation_value,
                i.source_file,
                i.source_sheet
            FROM seller_kpi_store_plan_fact_rows r
            JOIN seller_kpi_store_plan_fact_imports i ON i.id = r.import_id
            WHERE r.period_month = :month AND LOWER(r.store_name) = LOWER(:store_name)
            ORDER BY r.metric_key, i.updated_at DESC NULLS LAST, i.created_at DESC
        """), {"month": month, "store_name": store_name})
        return {row._mapping["metric_key"]: dict(row._mapping) for row in result.fetchall()}

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(str(value).replace("\xa0", " ").replace(" ", "").replace(",", "."))
        except Exception:
            return None

    @staticmethod
    def _history_cell(raw_row: Any, index: int) -> Optional[str]:
        if not isinstance(raw_row, dict):
            return None
        value = raw_row.get(str(index), raw_row.get(index))
        return str(value).strip() if value not in (None, "") else None

    @classmethod
    def _history_metric_key(cls, label: Any) -> Optional[str]:
        value = str(label or "").lower().replace("ё", "е")
        if ("выруч" in value and "вошед" in value) or "на вошедшего" in value:
            return "revenue_per_visitor"
        if "выруч" in value or "оборот" in value or value.strip() == "продажи":
            return "revenue"
        if "кол-во изделий" in value or "количество изделий" in value:
            return "items_count"
        if "средний чек" in value:
            return "avg_check"
        if "средняя стоимость" in value:
            return "avg_item_price"
        if "длина чека" in value or "изделий в чеке" in value:
            return "items_per_check"
        if "кол-во чек" in value or "количество чек" in value or value.strip() == "чеки":
            return "checks_count"
        if "кол-во смен" in value or value.strip() == "смены":
            return "shifts_count"
        if "средние продажи" in value:
            return "avg_sales_per_shift"
        if "трафик" in value or "вошедш" in value:
            return "traffic"
        if "конверсия" in value:
            return "conversion"
        return None

    async def _history_seller_kpi_values(self, month: date, store_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Personal seller facts parsed from imported ЕО seller sheets.

        Store-level archive rows are used by target_indicators(). Personal pages need the
        named seller sheets (e.g. `Бешлиева`) because current sales_records may contain
        only a partial 1C sync. The raw sheet rows are already stored in DB, so this
        method parses them read-time without requiring a re-import.
        """
        await self._ensure_history_tables()
        where = ["i.period_month = :month"]
        params: Dict[str, Any] = {"month": month}
        if store_name:
            where.append("LOWER(i.store_name) = LOWER(:store_name)")
            params["store_name"] = store_name
        result = await self.db.execute(text(f"""
            SELECT i.store_name, i.source_file, r.source_sheet, r.row_number, r.raw_row
            FROM seller_kpi_store_plan_fact_sheet_rows r
            JOIN seller_kpi_store_plan_fact_imports i ON i.id = r.import_id
            WHERE {' AND '.join(where)}
              AND LOWER(r.source_sheet) NOT LIKE 'вед-ть%'
              AND LOWER(r.source_sheet) NOT IN ('центрум', 'ялта, ленина, 18', 'сводная', 'св. по пок.', 'справочник магазинов', 'план на день', 'график', 'конкурс')
            ORDER BY i.store_name, i.source_file, r.source_sheet, r.row_number
        """), params)
        grouped: Dict[tuple[str, str, str], List[Dict[str, Any]]] = {}
        for row in result.fetchall():
            item = dict(row._mapping)
            grouped.setdefault((item["store_name"], item["source_file"], item["source_sheet"]), []).append(item)

        parsed_rows: List[Dict[str, Any]] = []
        for (sheet_store_name, source_file, source_sheet), rows in grouped.items():
            raw_rows = [row.get("raw_row") for row in rows]
            header_index = None
            cols: Dict[str, int] = {}
            for idx, raw in enumerate(raw_rows):
                values = [str(value).strip().lower() for value in (raw or {}).values()]
                if "показатель" in values and "факт" in values:
                    header_index = idx
                    for key, value in (raw or {}).items():
                        text_value = str(value).strip().lower()
                        try:
                            col = int(key)
                        except Exception:
                            continue
                        if text_value == "показатель":
                            cols["label"] = col
                        elif text_value == "план":
                            cols["plan"] = col
                        elif text_value == "факт":
                            cols["fact"] = col
                    break
            if header_index is None or "label" not in cols or "fact" not in cols:
                continue

            sheet_hint = self._normalize_seller_name(source_sheet.replace("Вед-ть", ""))
            seller_name = None
            for raw in raw_rows[:header_index]:
                for value in (raw or {}).values():
                    text_value = str(value or "").strip()
                    normalized = self._normalize_seller_name(text_value)
                    if normalized and (normalized == sheet_hint or normalized.startswith(sheet_hint) or sheet_hint.startswith(normalized)):
                        seller_name = text_value
            seller_name = seller_name or source_sheet
            normalized_name = self._normalize_seller_name(seller_name)
            seller_external_id = KNOWN_SELLER_EXTERNAL_IDS_BY_NORMALIZED_NAME.get(normalized_name)
            facts: Dict[str, float] = {}
            plans: Dict[str, float] = {}
            for raw in raw_rows[header_index + 1:]:
                row_text = " ".join(str(v) for v in (raw or {}).values())
                if "Факт продаж за месяц" in row_text:
                    break
                metric_key = self._history_metric_key(self._history_cell(raw, cols["label"]))
                if not metric_key:
                    continue
                fact_value = self._to_float(self._history_cell(raw, cols["fact"]))
                plan_value = self._to_float(self._history_cell(raw, cols.get("plan", -1)))
                if fact_value is not None:
                    facts[metric_key] = fact_value
                if plan_value is not None:
                    plans[metric_key] = plan_value
            if not any(key in facts for key in ("revenue", "checks_count", "items_count")):
                continue
            revenue = float(facts.get("revenue") or 0)
            checks = int(round(float(facts.get("checks_count") or 0)))
            items_sold = float(facts.get("items_count") or 0)
            parsed_rows.append({
                "seller_external_id": seller_external_id,
                "seller_name": seller_name,
                "store_id": None,
                "store_name": sheet_store_name,
                "revenue": revenue,
                "checks": checks,
                "items_sold": items_sold,
                "archive_source_file": source_file,
                "archive_source_sheet": source_sheet,
                "archive_facts": facts,
                "archive_plans": plans,
            })
        return parsed_rows

    async def _agent_store_plan_draft(self, month: date, store_name: Optional[str] = None) -> Dict[str, float]:
        """Initial store plan draft from archive history: previous-year same month + last 3 months."""
        if not store_name:
            return {}
        await self._ensure_history_tables()
        # Previous-year comparable month.
        previous_year_month = month.replace(year=month.year - 1)
        # Last 3 fully completed/imported months before requested month.
        if month.month <= 3:
            start_month = date(month.year - 1, month.month + 9, 1)
        else:
            start_month = date(month.year, month.month - 3, 1)
        result = await self.db.execute(text("""
            SELECT metric_key,
                   AVG(CASE WHEN period_month >= :start_month AND period_month < :month THEN fact_value END)::float AS recent_avg_fact,
                   MAX(CASE WHEN period_month = :previous_year_month THEN fact_value END)::float AS previous_year_fact
            FROM seller_kpi_store_plan_fact_rows
            WHERE LOWER(store_name) = LOWER(:store_name)
              AND (period_month = :previous_year_month OR (period_month >= :start_month AND period_month < :month))
              AND fact_value IS NOT NULL
            GROUP BY metric_key
        """), {"store_name": store_name, "month": month, "start_month": start_month, "previous_year_month": previous_year_month})
        draft: Dict[str, float] = {}
        for row in result.fetchall():
            item = dict(row._mapping)
            key = item.get("metric_key")
            recent = item.get("recent_avg_fact")
            previous_year = item.get("previous_year_fact")
            if key in {"revenue", "items_count", "checks_count", "traffic"}:
                candidates = [float(v) for v in [recent, previous_year] if v is not None]
                if candidates:
                    draft[key] = max(candidates)
            elif key in {"avg_check", "avg_item_price", "items_per_check", "conversion", "shifts_count"}:
                value = recent if recent is not None else previous_year
                if value is not None:
                    draft[key] = float(value)
        if draft.get("revenue") and draft.get("traffic") and "revenue_per_visitor" not in draft:
            draft["revenue_per_visitor"] = draft["revenue"] / draft["traffic"]
        if draft.get("revenue") and draft.get("shifts_count") and "avg_sales_per_shift" not in draft:
            draft["avg_sales_per_shift"] = draft["revenue"] / draft["shifts_count"]
        return draft

    async def target_indicators(self, current_user: User, month: Optional[str] = None, store_name: Optional[str] = None) -> Dict[str, Any]:
        """Monthly KPI target table: plan is manual/agent-editable, facts can come from 1C or imported ЕО history."""
        month_date, start_dt, end_dt = self.month_range(month)
        overview = await self.kpi_overview(current_user=current_user, month=month, store_name=store_name)
        plans = await self._target_metric_plans(month_date, store_name=store_name)
        history = await self._history_metric_values(month_date, store_name=store_name)
        agent_draft_plans = await self._agent_store_plan_draft(month_date, store_name=store_name)
        use_agent_draft = not history

        seller_rows = overview.get("sellers", [])
        totals = overview.get("totals", {})
        revenue_plan_fallback = float(totals.get("revenue_plan") or 0)
        checks_plan_fallback = sum(float(row.get("checks_plan") or 0) for row in seller_rows if row.get("checks_plan") is not None)
        items_plan_fallback = sum(float(row.get("items_plan") or 0) for row in seller_rows if row.get("items_plan") is not None)

        sales_facts = await self._sales_fact_totals(start_dt, end_dt, store_name=store_name)
        revenue = float(sales_facts["revenue"] or 0)
        checks = int(sales_facts["checks"] or 0)
        items = float(sales_facts["items_sold"] or 0)
        shifts_count = await self._shift_count(start_dt.date(), (end_dt - timedelta(days=1)).date(), store_name=store_name)
        facts = {
            "revenue": sales_facts["revenue"],
            "items_count": items,
            "avg_check": revenue / checks if checks else None,
            "avg_item_price": revenue / items if items else None,
            "items_per_check": items / checks if checks else None,
            "checks_count": checks,
            "shifts_count": shifts_count,
            "avg_sales_per_shift": revenue / shifts_count if shifts_count else None,
            "lag_lead": None,
            "traffic": None,
            "revenue_per_visitor": None,
            "conversion": None,
        }
        fallback_plans = {
            "revenue": revenue_plan_fallback,
            "items_count": items_plan_fallback or None,
            "checks_count": checks_plan_fallback or None,
        }

        today = date.today()
        days_in_month = ((month_date.replace(year=month_date.year + 1, month=1) if month_date.month == 12 else month_date.replace(month=month_date.month + 1)) - month_date).days
        if today.year == month_date.year and today.month == month_date.month:
            elapsed_days = max(1, min(today.day, days_in_month))
        elif today >= end_dt.date():
            elapsed_days = days_in_month
        else:
            elapsed_days = 1

        rows = []
        for metric in self._target_metric_defs():
            key = metric["key"]
            history_row = history.get(key) or {}
            fact = history_row.get("fact_value") if history_row.get("fact_value") is not None else facts.get(key)
            plan = plans.get(key)
            if plan is None:
                plan = history_row.get("plan_value") if history_row.get("plan_value") is not None else (agent_draft_plans.get(key) if use_agent_draft else fallback_plans.get(key))
            forecast = history_row.get("forecast_value") if history_row.get("forecast_value") is not None else (fact / elapsed_days * days_in_month if isinstance(fact, (int, float)) else None)
            percent = (history_row.get("completion_percent") * 100) if isinstance(history_row.get("completion_percent"), (int, float)) and abs(history_row.get("completion_percent")) <= 10 else history_row.get("completion_percent")
            if percent is None:
                percent = fact / plan * 100 if isinstance(fact, (int, float)) and plan else None
            forecast_percent = (history_row.get("forecast_percent") * 100) if isinstance(history_row.get("forecast_percent"), (int, float)) and abs(history_row.get("forecast_percent")) <= 10 else history_row.get("forecast_percent")
            if forecast_percent is None:
                forecast_percent = forecast / plan * 100 if isinstance(forecast, (int, float)) and plan else None
            deviation = history_row.get("deviation_value") if history_row.get("deviation_value") is not None else (fact - plan if isinstance(fact, (int, float)) and plan is not None else None)
            if key == "lag_lead":
                revenue_history = history.get("revenue") or {}
                revenue_plan = plans.get("revenue") or revenue_history.get("plan_value") or (agent_draft_plans.get("revenue") if use_agent_draft else None) or revenue_plan_fallback
                revenue_fact = revenue_history.get("fact_value") if revenue_history.get("fact_value") is not None else revenue
                fact = history_row.get("fact_value") if history_row.get("fact_value") is not None else (revenue_fact - revenue_plan if revenue_plan else None)
                forecast = history_row.get("forecast_value") if history_row.get("forecast_value") is not None else fact
                deviation = history_row.get("deviation_value") if history_row.get("deviation_value") is not None else fact
                percent = None
                forecast_percent = None
            last_year_fact = history_row.get("last_year_fact_value")
            if last_year_fact is None and store_name:
                previous_year = month_date.replace(year=month_date.year - 1)
                previous_history = await self._history_metric_values(previous_year, store_name=store_name)
                last_year_fact = (previous_history.get(key) or {}).get("fact_value")
            lfl_deviation = history_row.get("lfl_deviation_value")
            if lfl_deviation is None and isinstance(fact, (int, float)) and isinstance(last_year_fact, (int, float)):
                lfl_deviation = fact - last_year_fact
            rows.append({
                **metric,
                "plan": round(plan, 2) if isinstance(plan, (int, float)) else None,
                "fact": round(fact, 2) if isinstance(fact, (int, float)) else None,
                "percent": round(percent, 2) if percent is not None else None,
                "forecast": round(forecast, 2) if isinstance(forecast, (int, float)) else None,
                "forecast_percent": round(forecast_percent, 2) if forecast_percent is not None else None,
                "deviation": round(deviation, 2) if isinstance(deviation, (int, float)) else None,
                "last_year_fact": round(last_year_fact, 2) if isinstance(last_year_fact, (int, float)) else None,
                "lfl_deviation": round(lfl_deviation, 2) if isinstance(lfl_deviation, (int, float)) else None,
                "data_source": "archive_eo" if history_row else ("agent_history_draft" if use_agent_draft and key in agent_draft_plans and plans.get(key) is None else "1c_current"),
                "source_file": history_row.get("source_file"),
            })

        insights = self._build_insights(rows, overview.get("stores", []), seller_rows)
        await self._save_daily_snapshot(month_date, overview.get("scope") or "all", rows, overview, insights)

        return {
            "month": month_date.isoformat(),
            "scope": overview.get("scope"),
            "elapsed_days": elapsed_days,
            "days_in_month": days_in_month,
            "rows": rows,
            "insights": insights,
            "note": "План заполняет только администратор. Управляющий видит план-факт, графики и аналитику без права изменения плана. Факт пересчитывается из чеков 1С и графика смен.",
        }

    async def save_target_plans(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await self.ensure_tables()
        raw_month = payload.get("month")
        month_date = self.month_range(str(raw_month) if raw_month else None)[0]
        store_name = (payload.get("store_name") or "").strip()
        scope_type = "store" if store_name else "global"
        scope_key = store_name or "all"
        metrics = payload.get("metrics") or {}
        if not isinstance(metrics, dict):
            raise ValueError("metrics должен быть объектом: {metric_key: plan}")
        allowed = {metric["key"] for metric in self._target_metric_defs()}
        saved = 0
        for key, value in metrics.items():
            if key not in allowed or value in (None, ""):
                continue
            await self.db.execute(text("""
                INSERT INTO seller_kpi_target_plans (id, month, scope_type, scope_key, metric_key, plan_value, updated_at)
                VALUES (:id, :month, :scope_type, :scope_key, :metric_key, :plan_value, NOW())
                ON CONFLICT (month, scope_type, scope_key, metric_key)
                DO UPDATE SET plan_value=EXCLUDED.plan_value, updated_at=NOW()
            """), {"id": str(uuid4()), "month": month_date, "scope_type": scope_type, "scope_key": scope_key, "metric_key": key, "plan_value": float(value)})
            saved += 1
        await self.db.commit()
        return {"success": True, "saved": saved, "month": month_date.isoformat()}

    async def _sales_fact_totals(self, start_dt: datetime, end_dt: datetime, store_name: Optional[str] = None) -> Dict[str, float]:
        """Store sales facts from synchronized 1C sales records.

        Revenue, checks and item quantities all use the shared accessory exclusion
        policy. Raw 1C rows still keep packaging/certificates, but KPI facts and
        averages must not count supplementary products.
        """
        where = ["sr.sale_date >= :start_dt", "sr.sale_date < :end_dt"]
        params: Dict[str, Any] = {"start_dt": start_dt, "end_dt": end_dt}
        if store_name:
            where.append("LOWER(COALESCE(s.name, sr.store_id)) = LOWER(:store_name)")
            params["store_name"] = store_name

        result = await self.db.execute(text(f"""
            SELECT
                COALESCE(SUM(CASE WHEN {ANALYTICS_ELIGIBLE_PRODUCT_SQL} THEN sr.revenue ELSE 0 END), 0)::float AS revenue,
                COALESCE(SUM(CASE WHEN {ANALYTICS_ELIGIBLE_PRODUCT_SQL} THEN sr.quantity ELSE 0 END), 0)::float AS items_sold,
                COUNT(DISTINCT CASE WHEN {ANALYTICS_ELIGIBLE_PRODUCT_SQL} THEN sr.document_id ELSE NULL END)::int AS checks
            FROM sales_records sr
            LEFT JOIN stores s ON s.external_id = sr.store_id
            LEFT JOIN products p ON p.external_id = sr.product_id
            WHERE {' AND '.join(where)}
        """), params)
        row = result.first()
        if not row:
            return {"revenue": 0.0, "items_sold": 0.0, "checks": 0}
        data = dict(row._mapping)
        return {
            "revenue": float(data.get("revenue") or 0),
            "items_sold": float(data.get("items_sold") or 0),
            "checks": int(data.get("checks") or 0),
        }


    async def _seed_default_assortment_guidance(self, month: date, store_name: Optional[str]) -> None:
        if month.isoformat()[:7] != YALTA_ASSORTMENT_GUIDANCE_MONTH:
            return
        if store_name and store_name.strip().lower() != YALTA_ASSORTMENT_GUIDANCE_STORE.lower():
            return
        result = await self.db.execute(text("""
            SELECT COUNT(*) FROM seller_kpi_assortment_guidance
            WHERE month=:month AND LOWER(store_name)=LOWER(:store_name)
        """), {"month": month, "store_name": YALTA_ASSORTMENT_GUIDANCE_STORE})
        if int(result.scalar() or 0) > 0:
            return
        for row in YALTA_ASSORTMENT_GUIDANCE_JUNE_2026:
            await self.db.execute(text("""
                INSERT INTO seller_kpi_assortment_guidance
                    (id, store_name, month, assortment_block, current_stock, incoming, available_to_sell,
                     share, sales_guidance, stock_after_guidance, comment, soft_guidance, updated_at)
                VALUES (:id, :store_name, :month, :assortment_block, :current_stock, :incoming, :available_to_sell,
                        :share, :sales_guidance, :stock_after_guidance, :comment, TRUE, NOW())
                ON CONFLICT (store_name, month, assortment_block)
                DO NOTHING
            """), {**row, "id": str(uuid4()), "store_name": YALTA_ASSORTMENT_GUIDANCE_STORE, "month": month})
        await self.db.commit()

    async def save_assortment_guidance(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await self.ensure_tables()
        month_date = self.month_range(str(payload.get("month") or YALTA_ASSORTMENT_GUIDANCE_MONTH))[0]
        store_name = (payload.get("store_name") or "").strip()
        if not store_name:
            raise ValueError("store_name обязателен для ассортиментного ориентира")
        rows = payload.get("rows") or []
        if not isinstance(rows, list):
            raise ValueError("rows должен быть массивом ассортиментных блоков")
        saved = 0
        for row in rows:
            if not isinstance(row, dict) or not (row.get("assortment_block") or "").strip():
                continue
            current_stock = float(row.get("current_stock") or 0)
            incoming = float(row.get("incoming") or 0)
            available_to_sell = float(row.get("available_to_sell") or (current_stock + incoming))
            sales_guidance = float(row.get("sales_guidance") or 0)
            share = float(row.get("share") or 0)
            if not share and payload.get("store_revenue_plan"):
                share = sales_guidance / float(payload.get("store_revenue_plan") or 1)
            stock_after_guidance = float(row.get("stock_after_guidance") or (available_to_sell - sales_guidance))
            await self.db.execute(text("""
                INSERT INTO seller_kpi_assortment_guidance
                    (id, store_id, store_name, month, assortment_block, current_stock, incoming, available_to_sell,
                     share, sales_guidance, stock_after_guidance, comment, soft_guidance, updated_at)
                VALUES (:id, :store_id, :store_name, :month, :assortment_block, :current_stock, :incoming, :available_to_sell,
                        :share, :sales_guidance, :stock_after_guidance, :comment, :soft_guidance, NOW())
                ON CONFLICT (store_name, month, assortment_block)
                DO UPDATE SET store_id=EXCLUDED.store_id, current_stock=EXCLUDED.current_stock, incoming=EXCLUDED.incoming,
                    available_to_sell=EXCLUDED.available_to_sell, share=EXCLUDED.share, sales_guidance=EXCLUDED.sales_guidance,
                    stock_after_guidance=EXCLUDED.stock_after_guidance, comment=EXCLUDED.comment,
                    soft_guidance=EXCLUDED.soft_guidance, updated_at=NOW()
            """), {
                "id": str(uuid4()),
                "store_id": row.get("store_id") or payload.get("store_id"),
                "store_name": store_name,
                "month": month_date,
                "assortment_block": str(row.get("assortment_block") or "").strip(),
                "current_stock": current_stock,
                "incoming": incoming,
                "available_to_sell": available_to_sell,
                "share": share,
                "sales_guidance": sales_guidance,
                "stock_after_guidance": stock_after_guidance,
                "comment": row.get("comment"),
                "soft_guidance": bool(row.get("soft_guidance", True)),
            })
            saved += 1
        await self.db.commit()
        return {"success": True, "saved": saved, "month": month_date.isoformat(), "store_name": store_name}

    async def _assortment_sales_facts(self, start_dt: datetime, end_dt: datetime, store_name: Optional[str]) -> Dict[str, float]:
        where = ["sr.sale_date >= :start_dt", "sr.sale_date < :end_dt"]
        params: Dict[str, Any] = {"start_dt": start_dt, "end_dt": end_dt}
        if store_name:
            where.append("LOWER(COALESCE(s.name, sr.store_id)) = LOWER(:store_name)")
            params["store_name"] = store_name
        result = await self.db.execute(text(f"""
            SELECT
                CASE
                    WHEN LOWER(COALESCE(p.brand, sr.product_brand, sr.product_name, '')) LIKE '%antura%' THEN 'Antura'
                    WHEN LOWER(COALESCE(p.brand, sr.product_brand, sr.product_name, '')) LIKE '%raganella%' THEN 'Raganella'
                    WHEN LOWER(COALESCE(p.brand, sr.product_brand, sr.product_name, '')) LIKE '%kalliope%' THEN 'Kalliope'
                    WHEN LOWER(COALESCE(p.brand, sr.product_brand, sr.product_name, '')) LIKE '%claudio%' THEN 'Claudio Canzian'
                    WHEN LOWER(COALESCE(p.brand, sr.product_brand, sr.product_name, '')) LIKE '%uno%' OR LOWER(COALESCE(p.category, sr.product_category, sr.product_name, '')) LIKE '%men%' THEN 'UNOde50/Men'
                    WHEN LOWER(COALESCE(p.category, sr.product_category, sr.product_name, '')) LIKE '%sale%' OR LOWER(COALESCE(p.brand, sr.product_brand, sr.product_name, '')) LIKE '%sale%' THEN 'SALE'
                    WHEN LOWER(COALESCE(p.brand, sr.product_brand, sr.product_name, '')) IN ('is', 'i s') OR LOWER(COALESCE(p.brand, sr.product_brand, sr.product_name, '')) LIKE 'is %' THEN 'IS'
                    ELSE 'Остальное'
                END AS assortment_block,
                COALESCE(SUM(CASE WHEN {ANALYTICS_ELIGIBLE_PRODUCT_SQL} THEN sr.revenue ELSE 0 END), 0)::float AS revenue
            FROM sales_records sr
            LEFT JOIN stores s ON s.external_id = sr.store_id
            LEFT JOIN products p ON p.external_id = sr.product_id
            WHERE {' AND '.join(where)}
            GROUP BY 1
        """), params)
        return {row._mapping["assortment_block"]: float(row._mapping["revenue"] or 0) for row in result.fetchall()}

    async def assortment_guidance(self, current_user: User, month: Optional[str] = None, store_name: Optional[str] = None, seller_personal_plan: Optional[float] = None) -> Dict[str, Any]:
        await self.ensure_tables()
        month_date, start_dt, end_dt = self.month_range(month)
        await self._seed_default_assortment_guidance(month_date, store_name)
        if not store_name and month_date.isoformat()[:7] == YALTA_ASSORTMENT_GUIDANCE_MONTH:
            store_name = YALTA_ASSORTMENT_GUIDANCE_STORE
        where_sql = "month=:month"
        params: Dict[str, Any] = {"month": month_date}
        if store_name:
            where_sql += " AND LOWER(store_name)=LOWER(:store_name)"
            params["store_name"] = store_name

        result = await self.db.execute(text(f"""
            SELECT id, store_id, store_name, month, assortment_block,
                   current_stock::float AS current_stock, incoming::float AS incoming,
                   available_to_sell::float AS available_to_sell, share::float AS share,
                   sales_guidance::float AS sales_guidance, stock_after_guidance::float AS stock_after_guidance,
                   comment, soft_guidance, updated_at, created_at
            FROM seller_kpi_assortment_guidance
            WHERE {where_sql}
            ORDER BY sales_guidance DESC, assortment_block
        """), params)
        fact_by_block = await self._assortment_sales_facts(start_dt, end_dt, store_name)
        personal_plan = float(seller_personal_plan or 0)
        # seller_personal_plan and personal_sales_guidance use the explicit formula: personal_plan * share.
        rows: List[Dict[str, Any]] = []
        for db_row in result.fetchall():
            item = dict(db_row._mapping)
            item["month"] = item["month"].isoformat()
            for key in ("updated_at", "created_at"):
                if item.get(key) is not None:
                    item[key] = item[key].isoformat()
            fact = fact_by_block.get(item["assortment_block"], 0.0)
            plan = float(item.get("sales_guidance") or 0)
            share = float(item.get("share") or 0)
            item["fact_sales"] = round(fact, 2)
            item["completion_percent"] = round(fact / plan * 100, 2) if plan else None
            item["personal_sales_guidance"] = round(personal_plan * share, 2) if personal_plan else None
            rows.append(item)
        sum_sales_guidance = round(sum(float(row.get("sales_guidance") or 0) for row in rows), 2)
        diagnostics = self._build_assortment_diagnostics(rows)
        return {
            "month": month_date.isoformat(),
            "store_name": store_name,
            "seller_personal_plan": personal_plan or None,
            "sum_sales_guidance": sum_sales_guidance,
            "soft_guidance": True,
            "explanation": "Ассортиментный ориентир — не жёсткая квота, а структура плана: продавать весь ассортимент и не продавать бренды под ноль.",
            "rows": rows,
            "diagnostics": diagnostics,
        }

    @staticmethod
    def _build_assortment_diagnostics(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        diagnostics: List[Dict[str, Any]] = []
        for row in rows:
            fact = float(row.get("fact_sales") or 0)
            plan = float(row.get("sales_guidance") or 0)
            percent = row.get("completion_percent")
            block = row.get("assortment_block")
            if block == "SALE" and percent is not None and percent > 140:
                diagnostics.append({"type": "sale_skew", "severity": "warning", "title": "Слишком большой перекос в SALE", "text": "SALE помогает закрывать спрос, но не должен заменять продажу основного ассортимента."})
            elif plan > 0 and fact == 0 and block not in {"SALE"}:
                diagnostics.append({"type": "zero_block", "severity": "info", "title": f"Нет продаж в блоке {block}", "text": "Проверьте, предлагает ли продавец этот блок и не продает ли бренды под ноль."})
            elif percent is not None and percent < 50 and block in {"IS", "Antura", "Raganella", "Kalliope", "Claudio Canzian"}:
                diagnostics.append({"type": "premium_gap", "severity": "info", "title": f"Слабое движение {block}", "text": "Мягко усилить показ блока в подборках и комплектах, без превращения ориентира в штрафной KPI."})
        if not diagnostics:
            diagnostics.append({"type": "balanced", "severity": "success", "title": "Критичных ассортиментных перекосов не видно", "text": "Продолжайте сравнивать факт по блокам с мягким ориентиром."})
        return diagnostics[:8]

    async def product_diagnostics(self, month: Optional[str] = None, store_name: Optional[str] = None) -> Dict[str, Any]:
        """Read-only diagnostics for product rows included/excluded from seller KPI item facts."""
        month_date, start_dt, end_dt = self.month_range(month)
        where = ["sr.sale_date >= :start_dt", "sr.sale_date < :end_dt"]
        params: Dict[str, Any] = {"start_dt": start_dt, "end_dt": end_dt}
        if store_name:
            where.append(f"LOWER({STORE_EXPR}) = LOWER(:store_name)")
            params["store_name"] = store_name
        result = await self.db.execute(text(f"""
            SELECT
                COALESCE(sr.product_name, sr.raw_data->>'Номенклатура', sr.raw_data->>'product_name', 'Без названия') AS product_name,
                COALESCE(sr.product_category, sr.raw_data->>'Категория', sr.raw_data->>'category') AS product_category,
                sr.product_article,
                CASE WHEN {KPI_ELIGIBLE_PRODUCT_SQL} THEN false ELSE true END AS excluded_from_kpi,
                SUM(sr.quantity)::float AS quantity,
                SUM(sr.revenue)::float AS revenue,
                COUNT(DISTINCT sr.document_id) AS checks
            FROM sales_records sr
            LEFT JOIN stores s ON s.external_id = sr.store_id
            LEFT JOIN products p ON p.external_id = sr.product_id
            WHERE {' AND '.join(where)}
            GROUP BY 1, 2, 3, 4
            ORDER BY excluded_from_kpi DESC, quantity DESC NULLS LAST, revenue DESC NULLS LAST
            LIMIT 80
        """), params)
        rows = [dict(row._mapping) for row in result.fetchall()]
        totals = {
            "excluded_quantity": round(sum(float(row.get("quantity") or 0) for row in rows if row.get("excluded_from_kpi")), 2),
            "included_quantity": round(sum(float(row.get("quantity") or 0) for row in rows if not row.get("excluded_from_kpi")), 2),
            "excluded_revenue": round(sum(float(row.get("revenue") or 0) for row in rows if row.get("excluded_from_kpi")), 2),
            "included_revenue": round(sum(float(row.get("revenue") or 0) for row in rows if not row.get("excluded_from_kpi")), 2),
        }
        return {"month": month_date.isoformat(), "store_name": store_name, "terms": list(KPI_EXCLUDED_PRODUCT_TERMS), "totals": totals, "rows": rows}

    async def plan_months(self, limit: int = 24) -> Dict[str, Any]:
        await self.ensure_tables()
        await self._ensure_history_tables()
        result = await self.db.execute(text("""
            SELECT month, SUM(metrics_count) AS metrics_count, MAX(updated_at) AS updated_at, BOOL_OR(has_archive) AS has_archive
            FROM (
                SELECT month, COUNT(*) AS metrics_count, MAX(updated_at) AS updated_at, false AS has_archive
                FROM seller_kpi_target_plans
                GROUP BY month
                UNION ALL
                SELECT period_month AS month, COUNT(*) AS metrics_count, MAX(COALESCE(updated_at, created_at)) AS updated_at, true AS has_archive
                FROM seller_kpi_store_plan_fact_imports
                GROUP BY period_month
            ) months_union
            GROUP BY month
            ORDER BY month DESC
            LIMIT :limit
        """), {"limit": limit})
        months = []
        for row in result.fetchall():
            item = dict(row._mapping)
            item["month"] = item["month"].isoformat()
            item["updated_at"] = item["updated_at"].isoformat() if item.get("updated_at") else None
            months.append(item)
        return {"months": months}

    async def snapshot_history(self, month: Optional[str] = None, limit: int = 90) -> Dict[str, Any]:
        await self.ensure_tables()
        params: Dict[str, Any] = {"limit": limit}
        where = ""
        if month:
            month_date = self.month_range(month)[0]
            where = "WHERE month=:month"
            params["month"] = month_date
        result = await self.db.execute(text(f"""
            SELECT id, snapshot_date, month, scope, rows, totals, stores, sellers, insights, updated_at, created_at
            FROM seller_kpi_daily_snapshots
            {where}
            ORDER BY snapshot_date DESC, updated_at DESC NULLS LAST, created_at DESC
            LIMIT :limit
        """), params)
        snapshots = []
        for row in result.fetchall():
            item = dict(row._mapping)
            item["snapshot_date"] = item["snapshot_date"].isoformat()
            item["month"] = item["month"].isoformat()
            item["created_at"] = item["created_at"].isoformat() if item.get("created_at") else None
            item["updated_at"] = item["updated_at"].isoformat() if item.get("updated_at") else None
            snapshots.append(item)
        return {"snapshots": snapshots}

    async def _save_daily_snapshot(self, month: date, scope: str, rows: List[Dict[str, Any]], overview: Dict[str, Any], insights: List[Dict[str, Any]]) -> None:
        await self.ensure_tables()
        await self.db.execute(text("""
            INSERT INTO seller_kpi_daily_snapshots (id, snapshot_date, month, scope, rows, totals, stores, sellers, insights, updated_at)
            VALUES (:id, :snapshot_date, :month, :scope, CAST(:rows AS JSONB), CAST(:totals AS JSONB), CAST(:stores AS JSONB), CAST(:sellers AS JSONB), CAST(:insights AS JSONB), NOW())
            ON CONFLICT (snapshot_date, month, scope)
            DO UPDATE SET rows=EXCLUDED.rows, totals=EXCLUDED.totals, stores=EXCLUDED.stores, sellers=EXCLUDED.sellers, insights=EXCLUDED.insights, updated_at=NOW()
        """), {
            "id": str(uuid4()),
            "snapshot_date": date.today(),
            "month": month,
            "scope": scope,
            "rows": json.dumps(rows, ensure_ascii=False, default=str),
            "totals": json.dumps(overview.get("totals", {}), ensure_ascii=False, default=str),
            "stores": json.dumps(overview.get("stores", []), ensure_ascii=False, default=str),
            "sellers": json.dumps(overview.get("sellers", []), ensure_ascii=False, default=str),
            "insights": json.dumps(insights, ensure_ascii=False, default=str),
        })
        await self.db.commit()

    @staticmethod
    def _build_insights(rows: List[Dict[str, Any]], stores: List[Dict[str, Any]], sellers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        insights: List[Dict[str, Any]] = []
        weak = [row for row in rows if row.get("editable_plan") and row.get("plan") and row.get("percent") is not None and row.get("percent") < 90]
        for row in sorted(weak, key=lambda item: item.get("percent") or 0)[:4]:
            insights.append({
                "type": "metric_gap",
                "severity": "critical" if (row.get("percent") or 0) < 70 else "warning",
                "title": f"{row.get('label')} ниже плана",
                "text": f"Факт {row.get('percent')}% от плана. Управленцу стоит разобрать причины и поставить короткую задачу на неделю.",
                "metric_key": row.get("key"),
            })
        for store in sorted([s for s in stores if s.get("completion_percent") is not None], key=lambda item: item.get("completion_percent") or 0)[:3]:
            if (store.get("completion_percent") or 0) < 90:
                insights.append({
                    "type": "store_gap",
                    "severity": "warning",
                    "title": f"Магазин {store.get('store_name')} отстает",
                    "text": f"Выполнение {store.get('completion_percent')}%. Проверьте трафик, конверсию, средний чек и распределение смен.",
                    "store_id": store.get("store_id"),
                })
        for seller in sorted([s for s in sellers if s.get("completion_percent") is not None], key=lambda item: item.get("completion_percent") or 0)[:5]:
            if (seller.get("completion_percent") or 0) < 85:
                insights.append({
                    "type": "seller_gap",
                    "severity": "info",
                    "title": f"{seller.get('seller_name') or 'Продавец'} ниже личного плана",
                    "text": f"Выполнение {seller.get('completion_percent')}%. Рекомендация: пересмотреть сценарии допродажи, работу с сомнениями и среднюю стоимость изделия.",
                    "seller_external_id": seller.get("seller_external_id"),
                })
        if not insights:
            insights.append({
                "type": "positive",
                "severity": "success",
                "title": "Критичных отклонений нет",
                "text": "Продолжайте ежедневно смотреть прогноз, средний чек, конверсию и выполнение по магазинам.",
            })
        return insights[:8]

    async def _target_metric_plans(self, month: date, store_name: Optional[str] = None) -> Dict[str, float]:
        await self.ensure_tables()
        scope_type = "store" if store_name else "global"
        scope_key = store_name or "all"
        result = await self.db.execute(text("""
            SELECT metric_key, plan_value::float AS plan_value
            FROM seller_kpi_target_plans
            WHERE month=:month AND scope_type=:scope_type AND scope_key=:scope_key
        """), {"month": month, "scope_type": scope_type, "scope_key": scope_key})
        return {row._mapping["metric_key"]: float(row._mapping["plan_value"] or 0) for row in result.fetchall()}

    async def _target_metric_plan_sources(self, month: date, store_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return explicit plan provenance for dashboard warnings and human audit.

        Every store-level plan row carries period, store and matching status so Ялта
        and ТРК Центрум plans cannot be confused in the management dashboard.
        """
        await self.ensure_tables()
        scope_type = "store" if store_name else "global"
        scope_key = store_name or "all"
        result = await self.db.execute(text("""
            SELECT metric_key, plan_value::float AS plan_value, updated_at, created_at
            FROM seller_kpi_target_plans
            WHERE month=:month AND scope_type=:scope_type AND scope_key=:scope_key
        """), {"month": month, "scope_type": scope_type, "scope_key": scope_key})
        rows = []
        for row in result.fetchall():
            item = dict(row._mapping)
            item["source"] = "target_metric_plan"
            item["period"] = month.isoformat()[:7]
            item["store"] = store_name or "all"
            item["matching_status"] = "matched_confirmed" if float(item.get("plan_value") or 0) > 0 else "missing_or_unconfirmed"
            for key in ("updated_at", "created_at"):
                if item.get(key) is not None:
                    item[key] = item[key].isoformat()
            rows.append(item)
        return rows

    async def _shift_stats_by_seller(self, start: date, end: date, store_name: Optional[str] = None) -> List[Dict[str, Any]]:
        await self.ensure_tables()
        where = ["shift_date BETWEEN :start_date AND :end_date"]
        params: Dict[str, Any] = {"start_date": start, "end_date": end}
        if store_name:
            where.append("LOWER(COALESCE(store_name, '')) = LOWER(:store_name)")
            params["store_name"] = store_name
        result = await self.db.execute(text(f"""
            SELECT
                seller_external_id,
                seller_name,
                store_id,
                store_name,
                COUNT(*)::int AS shifts_count,
                COALESCE(SUM(
                    CASE
                        WHEN starts_at IS NULL OR ends_at IS NULL THEN 0
                        WHEN ends_at >= starts_at THEN EXTRACT(EPOCH FROM ((shift_date + ends_at) - (shift_date + starts_at))) / 3600.0
                        ELSE EXTRACT(EPOCH FROM ((shift_date + ends_at + INTERVAL '1 day') - (shift_date + starts_at))) / 3600.0
                    END
                ), 0)::float AS hours_count
            FROM seller_shift_schedules
            WHERE {' AND '.join(where)}
            GROUP BY seller_external_id, seller_name, store_id, store_name
        """), params)
        return [dict(row._mapping) for row in result.fetchall()]

    async def _latest_shift_stats_by_seller_before_month(self, month: date, store_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Use the latest previous schedule month as roster/hour-share fallback.

        This keeps personal plan rows visible when a new month has store targets but
        no current schedule/sales yet (common on day 1). The requested month still
        supplies the store plan; previous schedule is only used for seller roster and
        hour proportions.
        """
        await self.ensure_tables()
        where = ["shift_date < :month_start"]
        params: Dict[str, Any] = {"month_start": month}
        if store_name:
            where.append("LOWER(COALESCE(store_name, '')) = LOWER(:store_name)")
            params["store_name"] = store_name
        latest_result = await self.db.execute(text(f"""
            SELECT date_trunc('month', MAX(shift_date))::date AS fallback_month
            FROM seller_shift_schedules
            WHERE {' AND '.join(where)}
        """), params)
        fallback_month = latest_result.scalar()
        if not fallback_month:
            return []
        if fallback_month.month == 12:
            next_month = fallback_month.replace(year=fallback_month.year + 1, month=1)
        else:
            next_month = fallback_month.replace(month=fallback_month.month + 1)
        return await self._shift_stats_by_seller(fallback_month, next_month - timedelta(days=1), store_name=store_name)

    async def _formula_seller_plans(self, month: date, shift_stats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Compute personal seller plans using the Excel rule: store plan × seller hours / total store hours."""
        if not shift_stats:
            return []
        total_hours_by_store: Dict[str, float] = {}
        for row in shift_stats:
            store_key = (row.get("store_name") or row.get("store_id") or "").strip()
            if not store_key:
                continue
            total_hours_by_store[store_key] = total_hours_by_store.get(store_key, 0.0) + float(row.get("hours_count") or 0)

        target_cache: Dict[str, Dict[str, float]] = {}
        computed: List[Dict[str, Any]] = []
        for row in shift_stats:
            store_name = (row.get("store_name") or "").strip()
            store_key = store_name or (row.get("store_id") or "").strip()
            seller_name = row.get("seller_name")
            seller_external_id = row.get("seller_external_id") or KNOWN_SELLER_EXTERNAL_IDS_BY_NORMALIZED_NAME.get(self._normalize_seller_name(seller_name))
            seller_hours = float(row.get("hours_count") or 0)
            total_hours = total_hours_by_store.get(store_key) or 0
            if not store_name or seller_hours <= 0 or total_hours <= 0:
                continue
            if store_name not in target_cache:
                target_cache[store_name] = await self._target_metric_plans(month, store_name=store_name)
            store_targets = target_cache[store_name]
            store_revenue_plan = float(store_targets.get("revenue") or 0)
            if store_revenue_plan <= 0:
                continue
            ratio = seller_hours / total_hours
            revenue_plan = store_revenue_plan * ratio
            avg_item_price_plan = float(store_targets.get("avg_item_price") or 0) or None
            items_per_check_plan = float(store_targets.get("items_per_check") or 0) or None
            avg_check_plan = float(store_targets.get("avg_check") or 0) or (
                avg_item_price_plan * items_per_check_plan if avg_item_price_plan and items_per_check_plan else None
            )
            items_plan = revenue_plan / avg_item_price_plan if avg_item_price_plan else None
            checks_plan = items_plan / items_per_check_plan if items_plan is not None and items_per_check_plan else None
            traffic_plan = (float(store_targets.get("traffic") or 0) * ratio) if store_targets.get("traffic") is not None else None
            revenue_per_visitor_plan = revenue_plan / traffic_plan if traffic_plan else float(store_targets.get("revenue_per_visitor") or 0) or None
            conversion_plan = float(store_targets.get("conversion") or 0) or None
            computed.append({
                "seller_external_id": seller_external_id,
                "seller_name": seller_name,
                "store_id": row.get("store_id"),
                "store_name": store_name,
                "month": month,
                "revenue_plan": revenue_plan,
                "checks_plan": checks_plan,
                "items_plan": items_plan,
                "shifts_plan": int(row.get("shifts_count") or 0),
                "hours_plan": seller_hours,
                "avg_check_plan": avg_check_plan,
                "avg_item_price_plan": avg_item_price_plan,
                "items_per_check_plan": items_per_check_plan,
                "avg_sales_per_shift_plan": float(store_targets.get("avg_sales_per_shift") or 0) or None,
                "traffic_plan": traffic_plan,
                "revenue_per_visitor_plan": revenue_per_visitor_plan,
                "conversion_plan": conversion_plan,
                "source": "excel_formula",
                "plan_source": "excel_formula_hours_share",
            })
        return computed

    async def _shift_count(self, start: date, end: date, store_name: Optional[str] = None) -> int:
        await self.ensure_tables()
        where = ["shift_date BETWEEN :start_date AND :end_date"]
        params: Dict[str, Any] = {"start_date": start, "end_date": end}
        if store_name:
            where.append("LOWER(COALESCE(store_name, '')) = LOWER(:store_name)")
            params["store_name"] = store_name
        result = await self.db.execute(text(f"""
            SELECT COUNT(*) AS count
            FROM seller_shift_schedules
            WHERE {' AND '.join(where)}
        """), params)
        return int(result.scalar() or 0)

    @staticmethod
    def _target_metric_defs() -> List[Dict[str, Any]]:
        return [
            {"key": "revenue", "label": "Выручка", "format": "money", "editable_plan": True},
            {"key": "items_count", "label": "Кол-во изделий", "format": "number", "editable_plan": True},
            {"key": "avg_check", "label": "Средний чек", "format": "money", "editable_plan": True},
            {"key": "avg_item_price", "label": "Средняя стоимость изделия", "format": "money", "editable_plan": True},
            {"key": "items_per_check", "label": "Длина чека", "format": "decimal", "editable_plan": True},
            {"key": "checks_count", "label": "Кол-во чеков", "format": "number", "editable_plan": True},
            {"key": "shifts_count", "label": "Кол-во смен", "format": "number", "editable_plan": True},
            {"key": "avg_sales_per_shift", "label": "Средние продажи в смену", "format": "money", "editable_plan": True},
            {"key": "lag_lead", "label": "Отставание/Перевыполнение", "format": "money", "editable_plan": False},
            {"key": "traffic", "label": "Трафик", "format": "number", "editable_plan": True},
            {"key": "revenue_per_visitor", "label": "Выручка на вошедшего", "format": "money", "editable_plan": True},
            {"key": "conversion", "label": "Конверсия", "format": "percent", "editable_plan": True},
        ]

    @staticmethod
    def _normalize_seller_name(seller_name: Optional[str]) -> str:
        parts = [part for part in (seller_name or "").strip().lower().replace("ё", "е").split() if part]
        if len(parts) >= 2:
            return " ".join(parts[:2])
        return " ".join(parts)

    @classmethod
    def _seller_key(cls, seller_external_id: Optional[str], seller_name: Optional[str], store_id: Optional[str], store_name: Optional[str]) -> str:
        normalized_name = cls._normalize_seller_name(seller_name)
        normalized_store = (store_name or store_id or "").strip().lower()
        seller_id = (seller_external_id or "").strip()
        if normalized_name:
            return "|".join(["name", normalized_name, normalized_store])
        if seller_id and seller_id != ZERO_GUID:
            return "|".join(["id", seller_id, normalized_store])
        return "|".join(["unmatched", seller_id or ZERO_GUID, normalized_store])
