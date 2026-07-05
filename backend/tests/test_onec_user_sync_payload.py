import unittest
from datetime import datetime, timezone

from app.services.onec_user_registration_payload import OneCUserRegistrationPayload
from app.services.onec_user_sync_service import OneCUserSyncService


class FakeSession:
    async def execute(self, *args, **kwargs):
        raise RuntimeError("db is not used in this test")


class OneCUserSyncPayloadTests(unittest.TestCase):
    def test_payload_normalizes_phone(self):
        p = OneCUserRegistrationPayload(phone="+7 (999) 123-45-67")
        self.assertEqual(p.phone, "79991234567")

    def test_payload_validates_inn(self):
        p = OneCUserRegistrationPayload(phone="79991234567", inn="77 00 000 000")
        self.assertEqual(p.inn, "7700000000")

    def test_payload_rejects_bad_inn(self):
        with self.assertRaises(Exception):
            OneCUserRegistrationPayload(phone="79991234567", inn="123")

    def test_retry_backoff_increases(self):
        svc = OneCUserSyncService(FakeSession())
        t1 = svc._calc_next_attempt_at(1)
        t2 = svc._calc_next_attempt_at(2)
        self.assertTrue(isinstance(t1, datetime))
        self.assertTrue(isinstance(t2, datetime))
        self.assertTrue(t1.tzinfo is not None)
        self.assertTrue(t2.tzinfo is not None)
        self.assertGreaterEqual(t2, t1)

