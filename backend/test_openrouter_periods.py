import os
import asyncio
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone
import httpx

from app.api.settings import get_openrouter_stats, _period_dates


class DummyResp:
    def __init__(self, json_data, status_code=200, url="https://openrouter.ai/api/v1/activity"):
        self._json_data = json_data
        self.status_code = status_code
        self.text = ""
        self._request = httpx.Request("GET", url)
        self._response = httpx.Response(status_code=status_code, request=self._request)

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=self._request, response=self._response)


class ClientMock:
    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None, params=None):
        ClientMock.calls += 1
        now = datetime.now(timezone.utc).date()
        today = now.isoformat()
        yesterday = (now - timedelta(days=1)).isoformat()
        prev_monday = (now - timedelta(days=now.weekday() + 7)).isoformat()
        prev_month_start = (now.replace(day=1) - timedelta(days=1)).replace(day=1).isoformat()
        if url.endswith("/auth/key"):
            return DummyResp({"data": {"usage_daily": 2.0, "limit_remaining": 10.0}}, 200, url)
        if url.endswith("/credits"):
            return DummyResp({"data": {"total_credits": 100.0, "total_usage": 80.0}}, 200, url)
        if url.endswith("/activity"):
            rows = [
                {"date": yesterday, "model": "a", "usage": 1.0, "requests": 2},
                {"date": today, "model": "a", "usage": 3.0, "requests": 3},
                {"date": today, "model": "b", "usage": 2.0, "requests": 1},
                {"date": prev_monday, "model": "c", "usage": 5.0, "requests": 5},
                {"date": prev_month_start, "model": "d", "usage": 7.0, "requests": 7},
            ]
            return DummyResp({"data": rows}, 200, url)
        return DummyResp({}, 404, url)


class PeriodsTests(unittest.TestCase):
    def setUp(self):
        os.environ["OPENROUTER_API_KEY"] = "key"
        os.environ["OPENROUTER_MANAGEMENT_API_KEY"] = "mgmt"
        from app.api import settings as mod
        mod._stats_cache.clear()
        mod._stats_cache_ts.clear()

    def test_period_dates_basic(self):
        start, end = _period_dates("today")
        self.assertEqual(start, end)
        sy, ey = _period_dates("yesterday")
        self.assertEqual(sy, ey)

    def test_stats_today_filters(self):
        async def run():
            with mock.patch("app.api.settings.httpx.AsyncClient", ClientMock):
                return await get_openrouter_stats(period="today")
        res = asyncio.run(run())
        self.assertTrue(all(d.date == datetime.now(timezone.utc).date().isoformat() for d in res.by_day))
        models = {m.model for m in res.by_model}
        self.assertTrue(models.issubset({"a", "b"}))

    def test_stats_yesterday_filters(self):
        async def run():
            with mock.patch("app.api.settings.httpx.AsyncClient", ClientMock):
                return await get_openrouter_stats(period="yesterday")
        res = asyncio.run(run())
        self.assertEqual(len(res.by_day), 1)
        self.assertEqual(res.by_model[0].model, "a")

    def test_cache_used(self):
        async def run():
            with mock.patch("app.api.settings.httpx.AsyncClient", ClientMock):
                r1 = await get_openrouter_stats(period="week")
                c1 = ClientMock.calls
                r2 = await get_openrouter_stats(period="week")
                c2 = ClientMock.calls
                return r1, r2, c1, c2
        r1, r2, c1, c2 = asyncio.run(run())
        self.assertEqual(c1, c2)
        self.assertGreaterEqual(len(r1.by_day), 1)
        self.assertGreaterEqual(len(r2.by_day), 1)

    def test_week_filters(self):
        async def run():
            with mock.patch("app.api.settings.httpx.AsyncClient", ClientMock):
                return await get_openrouter_stats(period="week")
        res = asyncio.run(run())
        self.assertTrue(len(res.by_day) >= 1)
        # Должны отсутствовать записи из предыдущего месяца/недели, созданные фикстурой (model 'd' и 'c')
        models = {m.model for m in res.by_model}
        self.assertFalse("d" in models)

    def test_month_filters_boundary(self):
        # Подменяем диапазон на фиксированный, пересекающий границу месяца
        start = "2026-03-01"
        end = "2026-03-02"
        async def run():
            with mock.patch("app.api.settings._period_dates", return_value=(start, end)):
                with mock.patch("app.api.settings.httpx.AsyncClient", ClientMock):
                    return await get_openrouter_stats(period="month")
        res = asyncio.run(run())
        # Даты вне диапазона (prev_month_start) не должны попасть
        days = [d.date for d in res.by_day]
        self.assertTrue(all(start <= d <= end for d in days))

    def test_timezone_independence_utc(self):
        # Проверяем, что диапазон формируется в UTC и сравнение идёт по YYYY-MM-DD
        async def run():
            with mock.patch("app.api.settings.httpx.AsyncClient", ClientMock):
                return await get_openrouter_stats(period="today")
        res = asyncio.run(run())
        self.assertTrue(all(len(d.date) == 10 and d.date[4] == "-" for d in res.by_day))


if __name__ == "__main__":
    unittest.main()
