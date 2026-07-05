import os
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx


class CdekAuthError(Exception):
    pass


class CdekService:
    def __init__(self, *, base_url: str, client_id: str, client_secret: str):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    async def _get_token(self) -> str:
        now = time.time()
        if self._token and now < (self._token_expires_at - 30):
            return self._token

        url = f"{self.base_url}/oauth/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, data=data)
            if resp.status_code >= 400:
                raise CdekAuthError(resp.text)
            payload = resp.json()

        token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        if not token or not expires_in:
            raise CdekAuthError("Invalid token response")

        self._token = str(token)
        try:
            self._token_expires_at = now + int(expires_in)
        except Exception:
            self._token_expires_at = now + 300
        return self._token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any] | List[Any]:
        token = await self._get_token()
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.request(
                method,
                url,
                params=params,
                json=json,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()

    async def search_cities(
        self,
        *,
        query: str,
        country_codes: Optional[List[str]] = None,
        size: int = 20,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "size": max(1, min(int(size), 100)),
            "city": query,
        }
        if country_codes:
            params["country_codes"] = ",".join(country_codes)
        data = await self._request("GET", "/location/cities", params=params)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        return []

    async def list_pickup_points(
        self,
        *,
        city_code: int,
        type_: str = "PVZ",
        size: int = 200,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "city_code": int(city_code),
            "type": type_,
            "size": max(1, min(int(size), 500)),
        }
        data = await self._request("GET", "/deliverypoints", params=params)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        return []

    async def calculate_by_available_tariffs(
        self,
        *,
        from_city_code: int,
        to_city_code: int,
        packages: List[Dict[str, Any]],
        tariff_codes: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "from_location": {"code": int(from_city_code)},
            "to_location": {"code": int(to_city_code)},
            "packages": packages,
        }
        if tariff_codes:
            payload["tariff_codes"] = [int(x) for x in tariff_codes]
        data = await self._request("POST", "/calculator/tarifflist", json=payload)
        if isinstance(data, dict):
            return data
        return {"tariffs": data}

    async def create_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = await self._request("POST", "/orders", json=payload)
        if isinstance(data, dict):
            return data
        return {"result": data}

    async def get_order(self, order_uuid: str) -> Dict[str, Any]:
        data = await self._request("GET", f"/orders/{order_uuid}")
        if isinstance(data, dict):
            return data
        return {"result": data}


def get_cdek_service() -> Optional[CdekService]:
    client_id = os.getenv("CDEK_CLIENT_ID")
    client_secret = os.getenv("CDEK_CLIENT_SECRET")
    base_url = os.getenv("CDEK_BASE_URL") or "https://api.cdek.ru/v2"
    if not client_id or not client_secret:
        return None
    return CdekService(base_url=base_url, client_id=client_id, client_secret=client_secret)
