from statistics import median
from typing import Any, Dict, List, Optional

from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_agent import BaseAgent
from app.services.inventory_control_service import InventoryControlService


class MerchandisingAgent(BaseAgent):
    SYSTEM_PROMPT = """You are a merchandising optimization agent.

Return merchandising recommendations as a structured table only.
Do not invent product names.
"""

    def __init__(self, db: AsyncSession):
        super().__init__()
        self.db = db
        self.inventory = InventoryControlService(db)

    async def build_merchandising(
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
        sales_vals = [r.sales_month for r in rows if r.sales_month > 0]
        med = float(median(sales_vals)) if sales_vals else 0.0

        out: List[Dict[str, Any]] = []
        for r in rows:
            recs: List[str] = []
            if r.sales_month > med and r.stock_qty > 3:
                recs.append("DISPLAY")

            cat = (r.category or "").lower()
            if (("серьг" in cat) or ("кольц" in cat) or ("earring" in cat) or ("ring" in cat)) and r.sales_month > 0.5:
                recs.append("CHECKOUT")

            if r.stock_cover is not None and r.stock_cover > 4 and r.sales_month > 0.2:
                recs.append("SELLING PRIORITY")

            if r.sales_month < 0.2 and r.stock_qty > 0:
                recs.append("REMOVE")

            if not recs:
                continue

            out.append(
                {
                    "nomenclature": r.nomenclature,
                    "color": r.color,
                    "category": r.category,
                    "sales_month": r.sales_month,
                    "stock_qty": r.stock_qty,
                    "stock_cover": r.stock_cover,
                    "recommendations": recs,
                }
            )

        return {"rows": out[:limit], "total": len(out), "median_sales_month": med}
