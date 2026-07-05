from typing import Any, Dict, List, Optional

from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_agent import BaseAgent
from app.services.inventory_control_service import InventoryControlService


class PricingAgent(BaseAgent):
    SYSTEM_PROMPT = """You are a pricing optimization agent.

Return structured pricing table only. Do not invent product names.
For core assortment / brand concept products, prefer bundle/relocation/selling priority before discount.
"""

    def __init__(self, db: AsyncSession):
        super().__init__()
        self.db = db
        self.inventory = InventoryControlService(db)

    def _status(self, sales_month: float, stock_cover: Optional[float], protected: bool) -> str:
        if sales_month <= 0:
            return "HOLD PRICE"
        if stock_cover is None:
            return "HOLD PRICE"
        if sales_month > 0.7 and stock_cover <= 3:
            return "NO DISCOUNT"
        if sales_month > 0.2 and 3 < stock_cover <= 6:
            return "BUNDLE INSTEAD OF DISCOUNT" if protected else "LIGHT DISCOUNT"
        if sales_month <= 0.2 and stock_cover > 6:
            return "BUNDLE INSTEAD OF DISCOUNT" if protected else "HEAVY DISCOUNT"
        return "HOLD PRICE"

    async def build_pricing_report(
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
            protected = bool(r.is_core_assortment or r.supports_brand_concept)
            out.append(
                {
                    "nomenclature": r.nomenclature,
                    "color": r.color,
                    "sales_month": r.sales_month,
                    "stock_qty": r.stock_qty,
                    "stock_cover": r.stock_cover,
                    "pricing_status": self._status(r.sales_month, r.stock_cover, protected=protected),
                    "is_core_assortment": r.is_core_assortment,
                    "supports_brand_concept": r.supports_brand_concept,
                }
            )
        return {"rows": out[:limit], "total": len(out)}
