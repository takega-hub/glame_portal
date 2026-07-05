from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

import httpx


logger = logging.getLogger(__name__)


class OneCGiftCertificateService:
    def __init__(self, api_url: Optional[str] = None, api_token: Optional[str] = None):
        self.api_url = (api_url or os.getenv("ONEC_API_URL") or "").rstrip("/")
        self.api_token = api_token or os.getenv("ONEC_API_TOKEN")
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = self.api_token if self.api_token.startswith("Basic ") else f"Basic {self.api_token}"
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0),
            headers=headers,
        )

    async def __aenter__(self) -> "OneCGiftCertificateService":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def close(self) -> None:
        await self.client.aclose()

    def _url(self, endpoint: str) -> str:
        if not self.api_url:
            raise ValueError("ONEC_API_URL не настроен")
        return f"{self.api_url}/{endpoint.lstrip('/')}"

    async def _request_json(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
        max_retries: int = 2,
    ) -> dict[str, Any]:
        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                response = await self.client.request(
                    method,
                    self._url(endpoint),
                    params=params,
                    json=json_body,
                )
                if response.status_code >= 500 and attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                response.raise_for_status()
                return response.json() if response.content else {}
            except Exception as exc:
                last_error = exc
                if attempt < max_retries - 1 and isinstance(exc, (httpx.RequestError, httpx.HTTPStatusError)):
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
        if last_error:
            raise last_error
        raise RuntimeError("Не удалось выполнить запрос к 1С")

    async def find_gift_nomenclature_by_nominal(self, nominal_kopeks: int) -> Optional[dict[str, Any]]:
        nominal_rub = int(nominal_kopeks or 0) // 100
        if nominal_rub <= 0:
            return None
        select_fields = (
            "Ref_Key,Code,Description,Артикул,ТипНоменклатуры,Номинал,"
            "ПроизвольныйНоминал,ИспользоватьСерииНоменклатуры,DeletionMark"
        )
        for skip in range(0, int(os.getenv("ONEC_GIFT_NOMENCLATURE_SCAN_LIMIT", "5000")), 500):
            data = await self._request_json(
                "GET",
                "/Catalog_Номенклатура",
                params={"$top": 500, "$skip": skip, "$select": select_fields},
            )
            rows = data.get("value") or []
            for row in rows:
                if bool(row.get("DeletionMark")):
                    continue
                if row.get("ТипНоменклатуры") != "ПодарочныйСертификат":
                    continue
                if int(float(row.get("Номинал") or 0)) == nominal_rub:
                    return row
            if len(rows) < 500:
                break
        return None

    async def create_series(
        self,
        *,
        certificate_number: str,
        gift_nomenclature_ref: str,
        sold: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "Description": certificate_number,
            "Owner": gift_nomenclature_ref,
            "Owner_Type": "StandardODATA.Catalog_Номенклатура",
            "Продан": bool(sold),
            "DeletionMark": False,
        }
        return await self._request_json("POST", "/Catalog_СерииНоменклатуры", json_body=payload)

    async def mark_series_sold(self, series_ref_key: str, sold: bool = True) -> dict[str, Any]:
        endpoint = f"/Catalog_СерииНоменклатуры(guid'{series_ref_key}')"
        return await self._request_json("PATCH", endpoint, json_body={"Продан": bool(sold)})

