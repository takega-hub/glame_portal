from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx


logger = logging.getLogger(__name__)


class OneCGiftCertificateService:
    DEFAULT_NOMINAL_PROPERTY_NAME = "Номинал сертификата"

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

    @staticmethod
    def _gift_nomenclature_select_fields() -> str:
        return (
            "Ref_Key,Code,Description,Артикул,ТипНоменклатуры,Номинал,"
            "ПроизвольныйНоминал,ИспользоватьСерииНоменклатуры,DeletionMark"
        )

    @staticmethod
    def _is_active_gift_nomenclature(row: dict[str, Any]) -> bool:
        return (
            not bool(row.get("DeletionMark"))
            and row.get("ТипНоменклатуры") == "ПодарочныйСертификат"
            and bool(row.get("ИспользоватьСерииНоменклатуры"))
        )

    async def _scan_gift_nomenclature(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for skip in range(0, int(os.getenv("ONEC_GIFT_NOMENCLATURE_SCAN_LIMIT", "5000")), 500):
            data = await self._request_json(
                "GET",
                "/Catalog_Номенклатура",
                params={"$top": 500, "$skip": skip, "$select": self._gift_nomenclature_select_fields()},
            )
            batch = data.get("value") or []
            rows.extend(row for row in batch if self._is_active_gift_nomenclature(row))
            if len(batch) < 500:
                break
        return rows

    async def get_gift_nomenclature(self, ref_key: str) -> Optional[dict[str, Any]]:
        ref = str(ref_key or "").strip()
        if not ref:
            return None
        data = await self._request_json(
            "GET",
            f"/Catalog_Номенклатура(guid'{ref}')",
            params={"$select": self._gift_nomenclature_select_fields()},
        )
        if self._is_active_gift_nomenclature(data):
            return data
        return None

    async def find_gift_nomenclature_by_nominal(self, nominal_kopeks: int) -> Optional[dict[str, Any]]:
        nominal_rub = int(nominal_kopeks or 0) // 100
        if nominal_rub <= 0:
            return None
        rows = await self._scan_gift_nomenclature()
        for row in rows:
            if bool(row.get("ПроизвольныйНоминал")):
                continue
            if int(float(row.get("Номинал") or 0)) == nominal_rub:
                return row
        return None

    async def find_arbitrary_gift_nomenclature(self) -> Optional[dict[str, Any]]:
        configured_ref = os.getenv("ONEC_GIFT_CERTIFICATE_ARBITRARY_REF_KEY")
        if configured_ref:
            row = await self.get_gift_nomenclature(configured_ref)
            if row and bool(row.get("ПроизвольныйНоминал")):
                return row
            logger.warning(
                "ONEC_GIFT_CERTIFICATE_ARBITRARY_REF_KEY задан, но номенклатура не является активным сертификатом с произвольным номиналом"
            )

        rows = await self._scan_gift_nomenclature()
        arbitrary_rows = [row for row in rows if bool(row.get("ПроизвольныйНоминал"))]
        if not arbitrary_rows:
            return None
        arbitrary_rows.sort(
            key=lambda row: (
                int(float(row.get("Номинал") or 0)) != 0,
                str(row.get("Description") or ""),
            )
        )
        return arbitrary_rows[0]

    @staticmethod
    def _format_nominal_rub(nominal_kopeks: int) -> str:
        nominal_rub = int(nominal_kopeks or 0) // 100
        return f"{nominal_rub:,}".replace(",", " ") + " ₽"

    async def find_certificate_nominal_property(self) -> Optional[dict[str, Any]]:
        configured_ref = os.getenv("ONEC_GIFT_CERTIFICATE_NOMINAL_PROPERTY_REF_KEY")
        if configured_ref:
            try:
                row = await self._request_json(
                    "GET",
                    f"/ChartOfCharacteristicTypes_ДополнительныеРеквизитыИСведения(guid'{configured_ref}')",
                    params={"$select": "Ref_Key,Description,DeletionMark"},
                )
                if row and not bool(row.get("DeletionMark")):
                    return row
            except Exception:
                logger.warning(
                    "ONEC_GIFT_CERTIFICATE_NOMINAL_PROPERTY_REF_KEY задан, но реквизит не найден или недоступен"
                )

        target = self.DEFAULT_NOMINAL_PROPERTY_NAME.lower()
        for skip in range(0, int(os.getenv("ONEC_GIFT_PROPERTY_SCAN_LIMIT", "2000")), 500):
            data = await self._request_json(
                "GET",
                "/ChartOfCharacteristicTypes_ДополнительныеРеквизитыИСведения",
                params={"$top": 500, "$skip": skip, "$select": "Ref_Key,Description,DeletionMark"},
            )
            rows = data.get("value") or []
            for row in rows:
                if bool(row.get("DeletionMark")):
                    continue
                if str(row.get("Description") or "").strip().lower() == target:
                    return row
            if len(rows) < 500:
                break
        return None

    async def set_series_nominal(self, series_ref_key: str, nominal_kopeks: int) -> dict[str, Any]:
        prop = await self.find_certificate_nominal_property()
        if not prop or not prop.get("Ref_Key"):
            raise ValueError("Дополнительный реквизит 'Номинал сертификата' не найден в 1С")

        value = self._format_nominal_rub(nominal_kopeks)
        endpoint = f"/Catalog_СерииНоменклатуры(guid'{series_ref_key}')"
        return await self._request_json(
            "PATCH",
            endpoint,
            json_body={
                "ДополнительныеРеквизиты": [
                    {
                        "LineNumber": 1,
                        "Свойство_Key": str(prop["Ref_Key"]),
                        "Значение": value,
                        "Значение_Type": "Edm.String",
                        "ТекстоваяСтрока": value,
                    }
                ]
            },
        )

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

    async def ensure_series_sold(self, series_ref_key: str) -> None:
        endpoint = f"/Catalog_СерииНоменклатуры(guid'{series_ref_key}')"
        series = await self._request_json("GET", endpoint)
        if series.get("DeletionMark"):
            raise RuntimeError("Серия сертификата помечена на удаление в 1С")
        if not series.get("Продан"):
            await self.mark_series_sold(series_ref_key)
            series = await self._request_json("GET", endpoint)
        if not series.get("Продан"):
            raise RuntimeError("После начисления серия сертификата не отмечена проданной в 1С")

    async def get_series_balance(self, series_ref_key: str) -> float:
        balance = 0.0
        for skip in range(0, 100_000, 500):
            data = await self._request_json(
                "GET",
                "/AccumulationRegister_ПодарочныеСертификаты_RecordType",
                params={"$top": 500, "$skip": skip},
            )
            rows = data.get("value") or []
            for row in rows:
                if not row.get("Active") or row.get("НомерСертификата_Key") != series_ref_key:
                    continue
                amount = float(row.get("Сумма") or 0)
                balance += amount if row.get("RecordType") == "Receipt" else -amount
            if len(rows) < 500:
                return balance
        raise RuntimeError("Слишком много движений подарочных сертификатов в 1С для проверки остатка")

    async def issue_program_balance(
        self,
        *,
        series_ref_key: str,
        gift_nomenclature_ref: str,
        nominal_kopeks: int,
        organization_ref_key: str,
        certificate_number: str,
        source: str = "CRM",
    ) -> dict[str, Any]:
        nominal_rub = int(nominal_kopeks) / 100
        current_balance = await self.get_series_balance(series_ref_key)
        if current_balance:
            if abs(current_balance - nominal_rub) > 0.005:
                raise RuntimeError(f"Остаток сертификата в 1С ({current_balance}) не совпадает с номиналом ({nominal_rub})")
            await self.ensure_series_sold(series_ref_key)
            return {"Posted": True, "balance": current_balance}

        comment = f"GLAME {source} certificate {certificate_number}"
        matching: list[dict[str, Any]] = []
        for skip in range(0, 100_000, 500):
            data = await self._request_json(
                "GET", "/Document_ВводНачальныхОстатков", params={"$top": 500, "$skip": skip}
            )
            rows = data.get("value") or []
            matching.extend(
                row for row in rows if row.get("Комментарий") == comment and not row.get("DeletionMark")
            )
            if len(rows) < 500:
                break
        else:
            raise RuntimeError("Слишком много документов 1С для проверки начисления сертификата")
        if len(matching) > 1:
            raise RuntimeError(f"В 1С найдено несколько документов начисления для {certificate_number}")
        if matching:
            document = matching[0]
            lines = document.get("ПодарочныеСертификаты") or []
            if len(lines) != 1 or lines[0].get("НомерСертификата_Key") != series_ref_key or float(lines[0].get("Сумма") or 0) != nominal_rub:
                raise RuntimeError(f"Документ начисления {certificate_number} в 1С содержит другие данные")
        else:
            document = await self._request_json(
                "POST",
                "/Document_ВводНачальныхОстатков",
                json_body={
                    "Date": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                    "Posted": False,
                    "Организация_Key": organization_ref_key,
                    "РазделУчета": "СкидкиБонусы",
                    "Комментарий": comment,
                    "ПодарочныеСертификаты": [
                        {
                            "LineNumber": 1,
                            "ПодарочныйСертификат_Key": gift_nomenclature_ref,
                            "НомерСертификата_Key": series_ref_key,
                            "Сумма": nominal_rub,
                        }
                    ],
                },
            )
        doc_ref = document.get("Ref_Key")
        if not doc_ref:
            raise RuntimeError("1С не вернула ссылку на документ начисления сертификата")
        if not document.get("Posted"):
            await self._request_json(
                "POST",
                f"/Document_ВводНачальныхОстатков(guid'{doc_ref}')/Post",
                json_body={"PostingModeOperational": True},
            )
        balance = await self.get_series_balance(series_ref_key)
        if abs(balance - nominal_rub) > 0.005:
            raise RuntimeError(f"Документ {doc_ref} проведён, но остаток сертификата в 1С равен {balance} ₽")
        await self.ensure_series_sold(series_ref_key)
        return {"Ref_Key": doc_ref, "Posted": True, "balance": balance}
