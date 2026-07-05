import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi.testclient import TestClient
from sqlalchemy import select, func, cast, Integer, and_

from app.main import app
from app.database.connection import AsyncSessionLocal
from app.models.customer_segment import CustomerSegment
from app.models.user import User


class AutoSegmentFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    @staticmethod
    async def _pick_auto_segment():
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(CustomerSegment).where(
                    CustomerSegment.is_auto_generated == True,
                    CustomerSegment.is_active == True,
                )
            )
            return res.scalars().first()

    @staticmethod
    async def _count_by_auto_rules(rules: dict) -> int:
        conditions = []
        # min_purchases
        try:
            mp = int(rules.get("min_purchases", 0))
            if mp > 0:
                conditions.append(User.total_purchases >= mp)
        except Exception:
            pass
        # min_total in rubles -> total_spent in kopecks
        try:
            mt = int(rules.get("min_total", 0))
            if mt > 0:
                conditions.append(User.total_spent >= mt * 100)
        except Exception:
            pass
        # max_recency_days
        try:
            rd = int(rules.get("max_recency_days", 0))
            if rd > 0:
                cutoff = datetime.now(timezone.utc) - timedelta(days=rd)
                conditions.append(User.last_purchase_date >= cutoff)
        except Exception:
            pass
        # rfm_min_score (best-effort)
        try:
            rfm_min = int(rules.get("rfm_min_score", 0))
            if rfm_min > 0:
                r = cast(User.rfm_score['r_score'].astext, Integer)
                f = cast(User.rfm_score['f_score'].astext, Integer)
                m = cast(User.rfm_score['m_score'].astext, Integer)
                conditions.append((r + f + m) >= rfm_min)
        except Exception:
            pass
        async with AsyncSessionLocal() as db:
            base = select(User.id).distinct()
            if conditions:
                base = base.where(and_(*conditions))
            subq = base.subquery()
            result = await db.execute(select(func.count()).select_from(subq))
            return int(result.scalar() or 0)

    def test_auto_segment_filter_applies(self):
        import asyncio

        seg = asyncio.get_event_loop().run_until_complete(self._pick_auto_segment())
        if not seg:
            self.skipTest("No auto-generated segment found")
        name = seg.name
        rules = seg.rules or {}
        expected = asyncio.get_event_loop().run_until_complete(self._count_by_auto_rules(rules))

        q = quote(name)
        resp = self.client.get(f"/api/admin/customers?segment={q}")
        self.assertEqual(resp.status_code, 200, msg=resp.text)
        data = resp.json()
        self.assertIn("total", data)
        self.assertEqual(data["total"], expected)


if __name__ == "__main__":
    unittest.main()

