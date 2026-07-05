from typing import Any, Dict, List, Optional

from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_agent import BaseAgent
from app.services.inventory_control_service import InventoryControlService


class ClearanceAgent(BaseAgent):
    SYSTEM_PROMPT = """You are an inventory optimization agent.

Your task is to detect slow moving inventory and propose warehouse clearance actions.

Rules:
If sales_month = 0 and stock_cover > 12 -> WRITE_OFF candidate
If sales_month > 0 and stock_cover > 6 -> PROMO candidate
If sales_month > 0 and stock_cover > 5 -> BUNDLE candidate

Never recommend removing products that belong to core assortment or support brand concept.
Return structured tables only.
"""

    def __init__(self, db: AsyncSession):
        super().__init__()
        self.db = db
        self.inventory = InventoryControlService(db)

    async def build_clearance(
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
            if r.stock_qty <= 0:
                continue

            protected = bool(r.is_core_assortment or r.supports_brand_concept)
            recommendation = None
            reason = None

            if r.sales_month <= 0:
                if r.stock_cover is not None and r.stock_cover > 12:
                    recommendation = "WRITE_OFF"
                    reason = "sales_month = 0 AND stock_cover > 12"
                else:
                    recommendation = "RELOCATION"
                    reason = "sales_month = 0"
            else:
                if r.stock_cover is not None and r.stock_cover > 6:
                    recommendation = "PROMO"
                    reason = "sales_month > 0 AND stock_cover > 6"
                elif r.stock_cover is not None and r.stock_cover > 5:
                    recommendation = "BUNDLE"
                    reason = "sales_month > 0 AND stock_cover > 5"

            if protected and recommendation in ("WRITE_OFF", "PROMO"):
                if recommendation == "WRITE_OFF":
                    recommendation = "RELOCATION"
                    reason = "protected_product: prefer relocation before write_off"
                else:
                    recommendation = "BUNDLE"
                    reason = "protected_product: prefer bundle before promo"

            if recommendation:
                out.append(
                    {
                        "nomenclature": r.nomenclature,
                        "color": r.color,
                        "stock_qty": r.stock_qty,
                        "sales_month": r.sales_month,
                        "stock_cover": r.stock_cover,
                        "recommendation": recommendation,
                        "reason": reason,
                        "is_core_assortment": r.is_core_assortment,
                        "supports_brand_concept": r.supports_brand_concept,
                    }
                )

        out.sort(key=lambda x: (x.get("recommendation") or "", -(float(x.get("stock_cover") or 0.0))))
        return {"rows": out[:limit], "total": len(out)}
