import sys
import types

import pytest


ton_auto_transfer_module = types.ModuleType("app.services.ton_glm_auto_transfer_service")
ton_auto_transfer_module.TonGlmAutoTransferService = object
sys.modules.setdefault("app.services.ton_glm_auto_transfer_service", ton_auto_transfer_module)

ton_treasury_module = types.ModuleType("app.services.ton_glm_treasury_balance_service")
ton_treasury_module.TonGlmTreasuryBalanceService = object
sys.modules.setdefault("app.services.ton_glm_treasury_balance_service", ton_treasury_module)

from app.services.glm_telegram_alert_service import GlmTelegramAlertService


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class _FakeDB:
    async def execute(self, _stmt):
        return _ScalarResult(0)


class _User:
    full_name = "Партнер"
    phone = "+70000000000"
    loyalty_points = 100
    customer_id_1c = "customer-key"
    discount_card_id_1c = "card-key"


class _Member:
    id = "member-id"


@pytest.mark.asyncio
async def test_loyalty_reconciliation_skips_lots_fetch_when_lots_alerts_disabled(monkeypatch):
    service = GlmTelegramAlertService(_FakeDB())
    monkeypatch.setattr(
        service,
        "config_payload",
        lambda: {
            "loyalty_reconciliation_enabled": True,
            "loyalty_reconciliation_auto_sync_enabled": False,
            "loyalty_reconciliation_limit": 50,
            "loyalty_lots_alerts_enabled": False,
        },
    )

    class _RowsResult:
        def all(self):
            return [(_Member(), _User())]

    async def fake_execute(_stmt):
        return _RowsResult()

    service.db.execute = fake_execute

    class FakeOneC:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

        async def fetch_loyalty_balance(self, customer_key, discount_card_key):
            return {"balance": 100, "source_id": "ok"}

        async def fetch_loyalty_lots_balance(self, customer_key, discount_card_key):
            raise AssertionError("lots balance must not be fetched when lots alerts are disabled")

    monkeypatch.setattr("app.services.glm_telegram_alert_service.OneCCustomersService", FakeOneC)

    alerts = await service._collect_loyalty_reconciliation_alerts()

    assert alerts == []
