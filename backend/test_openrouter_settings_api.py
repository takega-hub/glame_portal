import os
import asyncio
import unittest
from unittest import mock

import httpx
from fastapi import HTTPException

from app.api.settings import (
    get_openrouter_usage,
    get_openrouter_credits,
    OpenRouterUsageResponse,
)
from app.api import settings as settings_module


class DummyResponse:
    def __init__(self, json_data, status_code: int = 200, url: str = "https://openrouter.ai/api/v1/credits"):
        self._json_data = json_data
        self.status_code = status_code
        self.text = ""
        self._request = httpx.Request("GET", url)
        self._response = httpx.Response(status_code=status_code, request=self._request)

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=self._request,
                response=self._response,
            )


class OpenRouterSettingsApiTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("OPENROUTER_MANAGEMENT_API_KEY", None)
        os.environ.pop("OPENROUTER_API_KEY", None)
        settings_module._credits_cache = None
        settings_module._credits_cache_ts = 0.0

    def test_usage_requires_management_key(self):
        os.environ["OPENROUTER_API_KEY"] = "regular-key"

        async def run():
            return await get_openrouter_usage()

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(run())

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("OPENROUTER_MANAGEMENT_API_KEY", ctx.exception.detail)

    def test_usage_returns_empty_on_activity_403(self):
        os.environ["OPENROUTER_MANAGEMENT_API_KEY"] = "mgmt-key"

        class ActivityForbiddenClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url, headers=None, params=None):
                return DummyResponse({"detail": "forbidden"}, status_code=403, url=url)

        async def run():
            with mock.patch("app.api.settings.httpx.AsyncClient", ActivityForbiddenClient):
                return await get_openrouter_usage(days=7)

        result = asyncio.run(run())
        self.assertIsInstance(result, OpenRouterUsageResponse)
        self.assertEqual(result.days, 7)
        self.assertEqual(result.by_day, [])
        self.assertEqual(result.by_model, [])

    def test_credits_uses_cache_between_calls(self):
        os.environ["OPENROUTER_MANAGEMENT_API_KEY"] = "mgmt-key"

        class CreditsClient:
            call_count = 0

            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url, headers=None, params=None):
                CreditsClient.call_count += 1
                return DummyResponse(
                    {"data": {"total_credits": 100.0, "total_usage": 60.0}},
                    status_code=200,
                    url=url,
                )

        async def run():
            with mock.patch("app.api.settings.httpx.AsyncClient", CreditsClient):
                first = await get_openrouter_credits()
                second = await get_openrouter_credits()
                return first, second, CreditsClient.call_count

        first, second, call_count = asyncio.run(run())

        self.assertEqual(call_count, 1)
        self.assertEqual(first.total_credits, 100.0)
        self.assertEqual(first.total_usage, 60.0)
        self.assertEqual(first.remaining_credits, 40.0)
        self.assertFalse(first.cached)

        self.assertTrue(second.cached)
        self.assertEqual(second.total_credits, first.total_credits)
        self.assertEqual(second.remaining_credits, first.remaining_credits)

