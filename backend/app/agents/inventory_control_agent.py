import logging
from typing import Any, Dict, List, Optional

from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_agent import BaseAgent
from app.services.inventory_control_service import InventoryControlService, InventoryRow

logger = logging.getLogger(__name__)


class InventoryControlAgent(BaseAgent):
    SYSTEM_PROMPT = """You are an inventory control agent integrated into a marketing analytics platform.

Your task is to analyze product sales and stock levels and provide inventory management recommendations.

Rules:
1. Merge sales and stock datasets using keys: Номенклатура, Цвет.
2. Calculate sales_month, stock_cover, optimal_stock, order_qty.
3. Return structured tables only.
4. Never invent product names.
"""

    def __init__(self, db: AsyncSession):
        super().__init__()
        self.db = db
        self.inventory = InventoryControlService(db)

    async def build_report(
        self,
        analysis_period_days: int = 90,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        store_id: Optional[str] = None,
        category: Optional[str] = None,
        color: Optional[str] = None,
        brand: Optional[str] = None,
        collection: Optional[str] = None,
        limit: int = 5000,
    ) -> Dict[str, Any]:
        rows = await self.inventory.build_inventory_rows(
            analysis_period_days=analysis_period_days,
            store_id=store_id,
            start_dt=start_dt,
            end_dt=end_dt,
            category=category,
            color=color,
            brand=brand,
            collection=collection,
        )
        payload = [
            {
                "nomenclature": r.nomenclature,
                "color": r.color,
                "category": r.category,
                "sold_qty": r.sold_qty,
                "stock_qty": r.stock_qty,
                "sales_month": r.sales_month,
                "stock_cover": r.stock_cover,
                "status": r.status,
                "is_core_assortment": r.is_core_assortment,
                "supports_brand_concept": r.supports_brand_concept,
            }
            for r in rows[:limit]
        ]
        return {"rows": payload, "total": len(rows)}

    def _optimal_stock(self, sales_month: float) -> float:
        return float(sales_month) * 3.0

    def _order_qty(self, sales_month: float, stock_qty: float) -> float:
        qty = self._optimal_stock(sales_month) - float(stock_qty or 0.0)
        return float(qty) if qty > 0 else 0.0

    async def build_reorder_recommendations(
        self,
        analysis_period_days: int = 90,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        store_id: Optional[str] = None,
        category: Optional[str] = None,
        color: Optional[str] = None,
        brand: Optional[str] = None,
        collection: Optional[str] = None,
        limit: int = 5000,
    ) -> Dict[str, Any]:
        rows = await self.inventory.build_inventory_rows(
            analysis_period_days=analysis_period_days,
            store_id=store_id,
            start_dt=start_dt,
            end_dt=end_dt,
            category=category,
            color=color,
            brand=brand,
            collection=collection,
        )

        out: List[Dict[str, Any]] = []
        for r in rows:
            order_qty = self._order_qty(r.sales_month, r.stock_qty)
            if order_qty <= 0:
                continue
            optimal_stock = self._optimal_stock(r.sales_month)
            out.append(
                {
                    "nomenclature": r.nomenclature,
                    "color": r.color,
                    "stock_qty": r.stock_qty,
                    "sales_month": r.sales_month,
                    "optimal_stock": optimal_stock,
                    "order_qty": order_qty,
                    "status": r.status,
                }
            )
        out.sort(key=lambda r: float(r.get("order_qty") or 0.0), reverse=True)
        return {"rows": out[:limit], "total": len(out)}
