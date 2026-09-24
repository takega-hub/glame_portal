import httpx
import pytest

from app.services.onec_customers_service import OneCCustomersService


class _FakeOneCClient:
    def __init__(self):
        self.calls = []

    async def get(self, url, params=None):
        params = dict(params or {})
        self.calls.append((url, params))
        if url.endswith("/AccumulationRegister_БонусныеБаллы_Остатки"):
            request = httpx.Request("GET", url)
            return httpx.Response(404, request=request, json={"error": "not found"})
        if url.endswith("/AccumulationRegister_БонусныеБаллы_RecordType") and "$filter" in params:
            request = httpx.Request("GET", url)
            return httpx.Response(403, request=request, text="Операция не разрешена в предложении ГДЕ")
        if url.endswith("/AccumulationRegister_БонусныеБаллы_RecordType"):
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                json={
                    "value": [
                        {
                            "Active": True,
                            "Period": "2026-08-01T00:00:00",
                            "БонуснаяКарта_Key": "card-key",
                            "Начислено": 150,
                            "КСписанию": 40,
                            "Recorder": "doc-1",
                        },
                        {
                            "Active": True,
                            "Period": "2026-08-01T00:00:00",
                            "БонуснаяКарта_Key": "other-card",
                            "Начислено": 999,
                            "КСписанию": 0,
                        },
                    ]
                },
            )
        raise AssertionError(f"unexpected request: {url} {params}")


@pytest.mark.asyncio
async def test_fetch_loyalty_balance_falls_back_to_scan_when_1c_forbids_filtered_recordtype(monkeypatch):
    monkeypatch.setenv("ONEC_LOYALTY_FILTER_FIELDS", "БонуснаяКарта_Key")
    service = OneCCustomersService(api_url="https://onec.example/odata", api_token=None)
    if service.client:
        await service.client.aclose()
    service.client = _FakeOneCClient()

    result = await service.fetch_loyalty_balance("customer-key", "card-key", max_retries=1)

    assert result["balance"] == 110
    assert ("https://onec.example/odata/AccumulationRegister_БонусныеБаллы_RecordType", {"$top": 100, "$skip": 0}) in service.client.calls
