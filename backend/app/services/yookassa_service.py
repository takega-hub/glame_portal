import os
from typing import Any, Dict, Optional
from uuid import uuid4

import httpx


class YooKassaService:
    BASE_URL = "https://api.yookassa.ru/v3"

    def __init__(self, shop_id: str, secret_key: str):
        self.shop_id = shop_id
        self.secret_key = secret_key
        self.auth = (shop_id, secret_key)

    async def create_payment(
        self,
        *,
        amount_rub: str,
        description: str,
        return_url: str,
        metadata: Optional[Dict[str, Any]] = None,
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


def get_yookassa_service() -> Optional[YooKassaService]:
    shop_id = os.getenv("YOOKASSA_SHOP_ID")
    secret_key = os.getenv("YOOKASSA_SECRET_KEY")
    if not shop_id or not secret_key:
        return None
    return YooKassaService(shop_id=shop_id, secret_key=secret_key)

