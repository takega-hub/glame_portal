import json
import logging
from typing import Any, Dict, List, Optional

from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_agent import BaseAgent
from app.services.inventory_control_service import InventoryControlService, InventoryRow

logger = logging.getLogger(__name__)


class InventoryProcurementAgent(BaseAgent):
    SYSTEM_PROMPT = """You are an inventory control agent integrated into a marketing analytics platform.

Your task is to analyze product sales and stock levels and provide inventory management recommendations.

Rules:
1. Never invent product names.
2. Use values exactly as provided in dataset.
3. Return structured tables only (JSON objects/arrays), no prose paragraphs.
4. If you add explanations, add them as a column in the table.
"""

    def __init__(self, db: AsyncSession):
        super().__init__()
        self.db = db
        self.inventory = InventoryControlService(db)

    async def build_reorder_table(
        self,
        analysis_period_days: int = 90,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        store_id: Optional[str] = None,
        category: Optional[str] = None,
        color: Optional[str] = None,
        brand: Optional[str] = None,
        collection: Optional[str] = None,
        annotate_limit: int = 30,
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

        table = self._build_reorder_rows(rows)
        table.sort(key=lambda r: float(r.get("order_qty") or 0.0), reverse=True)

        if annotate_limit > 0:
            table = await self._annotate_top(table, limit=annotate_limit)

        return {"rows": table, "total": len(table)}

    def _optimal_stock(self, sales_month: float) -> float:
        return float(sales_month) * 3.0

    def _order_qty(self, sales_month: float, stock_qty: float) -> float:
        qty = self._optimal_stock(sales_month) - float(stock_qty or 0.0)
        return float(qty) if qty > 0 else 0.0

    def _build_reorder_rows(self, rows: List[InventoryRow]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for r in rows:
            order_qty = self._order_qty(r.sales_month, r.stock_qty)
            if order_qty <= 0:
                continue
            optimal_stock = self._optimal_stock(r.sales_month)
            order_amount = None
            if r.price_cents is not None:
                order_amount = order_qty * (float(r.price_cents) / 100.0)
            out.append(
                {
                    "nomenclature": r.nomenclature,
                    "color": r.color,
                    "stock_qty": r.stock_qty,
                    "sales_month": r.sales_month,
                    "optimal_stock": optimal_stock,
                    "order_qty": order_qty,
                    "order_amount": order_amount,
                    "status": r.status,
                }
            )
        return out

    async def _annotate_top(self, rows: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        top = rows[: max(0, limit)]
        if not top:
            return rows

        system_prompt = await self.get_active_system_prompt(self.db, "inventory-procurement-agent", self.SYSTEM_PROMPT)
        prompt = (
            "Add a short reason for ordering for each row. "
            "Return ONLY a JSON array with the same length and ordering. "
            "Each element must include keys: nomenclature, color, comment. "
            "comment must be <= 12 words, no new product names.\n\n"
            f"DATA:\n{json.dumps(top, ensure_ascii=False)}"
        )

        try:
            raw = await self.generate_response(prompt=prompt, system_prompt=system_prompt, temperature=0.2, max_tokens=1200)
            parsed = json.loads(raw)
            if not isinstance(parsed, list) or len(parsed) != len(top):
                return rows
            for i, item in enumerate(parsed):
                if isinstance(item, dict) and isinstance(item.get("comment"), str):
                    rows[i]["comment"] = item["comment"]
            return rows
        except Exception as e:
            logger.warning(f"InventoryProcurementAgent annotate failed: {e}")
            return rows
