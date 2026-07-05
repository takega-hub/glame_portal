import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from uuid import uuid4

from app.main import app


class DummyUser:
    def __init__(self, role="admin"):
        self.id = uuid4()
        self.role = role


class DeleteEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def override_user(self, role="admin"):
        def _dep():
            return DummyUser(role=role)
        app.dependency_overrides.clear()
        from app.api.auth import get_current_user
        app.dependency_overrides[get_current_user] = _dep

    def test_delete_unauthorized(self):
        app.dependency_overrides.clear()
        r = self.client.delete("/api/agent-interactions/tasks/00000000-0000-0000-0000-000000000000")
        self.assertEqual(r.status_code, 401)

    def test_delete_forbidden(self):
        self.override_user(role="customer")
        r = self.client.delete("/api/agent-interactions/tasks/00000000-0000-0000-0000-000000000000")
        self.assertEqual(r.status_code, 403)

    def test_delete_not_found(self):
        self.override_user(role="admin")

        class FakeService:
            def __init__(self, db):
                pass
            async def delete_task(self, task_id: str, deleted_by=None, reason=None):
                raise ValueError("not found")

        with patch("app.api.agent_interactions.AgentInteractionService", FakeService):
            r = self.client.delete("/api/agent-interactions/tasks/00000000-0000-0000-0000-000000000000")
            self.assertEqual(r.status_code, 404)

    def test_delete_success(self):
        self.override_user(role="admin")
        tid = uuid4()

        class FakeTask:
            def __init__(self, _id):
                self.id = _id
                self.status = "cancelled"

        class FakeService:
            def __init__(self, db):
                pass
            async def delete_task(self, task_id: str, deleted_by=None, reason=None):
                return FakeTask(tid)

        with patch("app.api.agent_interactions.AgentInteractionService", FakeService):
            r = self.client.delete(f"/api/agent-interactions/tasks/{tid}")
            self.assertEqual(r.status_code, 200)
            data = r.json()
            self.assertEqual(data["task_id"], str(tid))
            self.assertEqual(data["message"], "Задача удалена")


if __name__ == "__main__":
    unittest.main()

