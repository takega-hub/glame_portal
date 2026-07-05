from typing import Any, Dict, List, Optional

from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_agent import BaseAgent
from app.services.inventory_control_service import InventoryControlService


class MarketingInventoryAgent(BaseAgent):
    SYSTEM_PROMPT = """You are a marketing inventory optimization agent.

Connect marketing campaigns with inventory management.
Return structured tables only. Never invent product names.
"""

    def __init__(self, db: AsyncSession):
        super().__init__()
        self.db = db
        self.inventory = InventoryControlService(db)

    def _group(self, sales_month: float, stock_cover: Optional[float]) -> Optional[str]:
        if sales_month > 0.7 and stock_cover is not None and stock_cover <= 2:
            return "PROTECT_PRODUCTS"
        if sales_month > 0.5 and stock_cover is not None and stock_cover <= 3:
            return "GROWTH_PRODUCTS"
        if stock_cover is not None and stock_cover > 6:
            return "PROMO_PRODUCTS"
        if stock_cover is not None and stock_cover > 4 and sales_month > 0.2:
            return "INVENTORY_RELIEF"
        return None

    def _channel(self, group: str) -> Optional[str]:
        if group == "GROWTH_PRODUCTS":
            return "Instagram"
        if group == "INVENTORY_RELIEF":
            return "Email / SMS"
        if group == "PROMO_PRODUCTS":
            return "Promotions"
        return None

    async def build_marketing_link(
        self,
        analysis_period_days: int = 90,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        store_id: Optional[str] = None,
        limit: int = 5000,
    ) -> Dict[str, Any]:
        rows = await self.inventory.build_inventory_rows(
            analysis_period_days=analysis_period_days, store_id=store_id, start_dt=start_dt, end_dt=end_dt
        )
        out: List[Dict[str, Any]] = []
        for r in rows:
            group = self._group(r.sales_month, r.stock_cover)
            if not group:
                continue
            out.append(
                {
                    "product_id": r.product_id,
                    "external_id_1c": r.external_id,
                    "article": r.article,
                    "barcode": r.barcode,
                    "nomenclature": r.nomenclature,
                    "brand": r.brand,
                    "category": r.category,
                    "price": r.price_cents,
                    "color": r.color,
                    "sales_month": r.sales_month,
                    "stock_qty": r.stock_qty,
                    "stock_cover": r.stock_cover,
                    "group": group,
                    "recommended_channel": self._channel(group),
                }
            )
        out.sort(key=lambda x: (x.get("group") or "", -(float(x.get("sales_month") or 0.0)), float(x.get("stock_cover") or 0.0)))
        return {"rows": out[:limit], "total": len(out)}
