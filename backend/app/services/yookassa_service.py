import os
from typing import Any, Dict, Optional
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting


YOOKASSA_SETTINGS_KEY = "yookassa_settings"
YOOKASSA_MODES = {"test", "live"}


class YooKassaService:
    BASE_URL = "https://api.yookassa.ru/v3"

    def __init__(self, shop_id: str, secret_key: str, mode: str = "test"):
        self.shop_id = shop_id
        self.secret_key = secret_key
        self.mode = _normalize_mode(mode)
        self.auth = (shop_id, secret_key)

    async def create_payment(
        self,
        *,
        amount_rub: str,
        description: str,
        return_url: str,
        metadata: Optional[Dict[str, Any]] = None,
        receipt: Optional[Dict[str, Any]] = None,
        idempotence_key: Optional[str] = None,
        capture: bool = True,
    ) -> Dict[str, Any]:
        key = idempotence_key or uuid4().hex
        payload: Dict[str, Any] = {
            "amount": {"value": amount_rub, "currency": "RUB"},
            "capture": bool(capture),
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": description,
        }
        if metadata:
            payload["metadata"] = metadata
        if receipt:
            payload["receipt"] = receipt

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{self.BASE_URL}/payments",
                json=payload,
                auth=self.auth,
                headers={"Idempotence-Key": key},
            )
            resp.raise_for_status()
            data = resp.json()
            data["_idempotence_key"] = key
            return data

    async def get_payment(self, payment_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{self.BASE_URL}/payments/{payment_id}", auth=self.auth)
            resp.raise_for_status()
            return resp.json()


def _normalize_mode(value: Optional[str]) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in YOOKASSA_MODES else "test"


def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value.strip()
    return ""


def _credentials_for_mode(mode: str) -> tuple[str, str]:
    normalized = _normalize_mode(mode)
    if normalized == "live":
        return (
            _first_env("YOOKASSA_LIVE_SHOP_ID", "YOOKASSA_PROD_SHOP_ID", "YOOKASSA_PRODUCTION_SHOP_ID"),
            _first_env("YOOKASSA_LIVE_SECRET_KEY", "YOOKASSA_PROD_SECRET_KEY", "YOOKASSA_PRODUCTION_SECRET_KEY"),
        )
    return (
        _first_env("YOOKASSA_TEST_SHOP_ID", "YOOKASSA_SHOP_ID"),
        _first_env("YOOKASSA_TEST_SECRET_KEY", "YOOKASSA_SECRET_KEY"),
    )


def yookassa_env_status() -> dict[str, bool]:
    test_shop_id, test_secret_key = _credentials_for_mode("test")
    live_shop_id, live_secret_key = _credentials_for_mode("live")
    return {
        "test_configured": bool(test_shop_id and test_secret_key),
        "live_configured": bool(live_shop_id and live_secret_key),
    }


def yookassa_public_config() -> dict[str, Optional[str]]:
    test_shop_id, _test_secret_key = _credentials_for_mode("test")
    live_shop_id, _live_secret_key = _credentials_for_mode("live")
    return {
        "test_shop_id": test_shop_id or None,
        "live_shop_id": live_shop_id or None,
    }


def get_yookassa_service(mode: Optional[str] = None) -> Optional[YooKassaService]:
    resolved_mode = _normalize_mode(mode or os.getenv("YOOKASSA_MODE") or "test")
    shop_id, secret_key = _credentials_for_mode(resolved_mode)
    if not shop_id or not secret_key:
        return None
    return YooKassaService(shop_id=shop_id, secret_key=secret_key, mode=resolved_mode)


async def get_yookassa_mode(db: AsyncSession) -> tuple[str, str]:
    result = await db.execute(select(AppSetting).where(AppSetting.key == YOOKASSA_SETTINGS_KEY))
    setting = result.scalar_one_or_none()
    if setting and setting.value:
        try:
            import json

            payload = json.loads(str(setting.value))
            if isinstance(payload, dict):
                return _normalize_mode(payload.get("mode")), "db"
        except Exception:
            pass

    env_mode = os.getenv("YOOKASSA_MODE")
    if env_mode:
        return _normalize_mode(env_mode), "env"
    return "test", "default"


async def get_yookassa_service_for_db(db: AsyncSession) -> Optional[YooKassaService]:
    mode, _source = await get_yookassa_mode(db)
    return get_yookassa_service(mode)
