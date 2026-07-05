import unittest
import uuid
import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.database.connection import AsyncSessionLocal
from app.models.customer_segment import CustomerSegment
from app.models.user_segment import UserSegment
from app.models.user import User


class DeleteAISegmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    @staticmethod
    async def _create_ai_segment_with_assignment():
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(User).where(User.is_customer == True).limit(1))
            user = res.scalars().first()
            if not user:
                return None

            seg_id = uuid.uuid4()
            segment = CustomerSegment(
                id=seg_id,
                name=f"AI тестовый сегмент {seg_id}",
                description="Тестовый AI-сегмент для проверки удаления",
                rules={"logic": "AND", "filters": []},
                customer_count=1,
                is_active=True,
                is_auto_generated=True,
            )
            db.add(segment)
            await db.flush()

            link = UserSegment(
                user_id=user.id,
                segment_id=seg_id,
                assigned_by="ai",
                confidence_score=0.8,
            )
            db.add(link)
            await db.commit()

            return seg_id

    @staticmethod
    async def _load_segment_and_links(seg_id):
        async with AsyncSessionLocal() as db:
            seg_res = await db.execute(
                select(CustomerSegment).where(CustomerSegment.id == seg_id)
            )
            seg = seg_res.scalar_one_or_none()

            link_res = await db.execute(
                select(UserSegment).where(UserSegment.segment_id == seg_id)
            )
            link = link_res.scalar_one_or_none()
            return seg, link

    def test_delete_ai_segment_with_user_links(self):
        seg_id = asyncio.get_event_loop().run_until_complete(
            self._create_ai_segment_with_assignment()
        )
        if not seg_id:
            self.skipTest("Нет покупателей в БД для привязки сегмента")

        resp = self.client.delete(f"/api/customer-segmentation/segments/{seg_id}")
        self.assertIn(resp.status_code, (200, 204), msg=resp.text)

        seg, link = asyncio.get_event_loop().run_until_complete(
            self._load_segment_and_links(seg_id)
        )
        self.assertIsNone(seg)
        self.assertIsNone(link)


if __name__ == "__main__":
    unittest.main()

