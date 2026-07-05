import asyncio
import httpx
import logging
import os
from typing import Any, Dict, Optional, List, Tuple
from datetime import datetime, timezone, timedelta


logger = logging.getLogger(__name__)


class OneCOutboundService:
    def __init__(
        self,
        api_url: Optional[str] = None,
        api_token: Optional[str] = None,
        customers_endpoint: Optional[str] = None,
        discount_cards_endpoint: Optional[str] = None,
    ):
        self.api_url = (api_url or os.getenv("ONEC_API_URL") or "").rstrip("/")
        self.api_token = api_token or os.getenv("ONEC_API_TOKEN")
        self.customers_endpoint = customers_endpoint or os.getenv("ONEC_CUSTOMERS_ENDPOINT", "/Catalog_Контрагенты")
        self.discount_cards_endpoint = discount_cards_endpoint or os.getenv(
            "ONEC_DISCOUNT_CARDS_ENDPOINT",
            "/Catalog_ДисконтныеКарты",
        )

        self.client: Optional[httpx.AsyncClient] = None
        if self.api_url:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            if self.api_token:
                if self.api_token.startswith("Basic "):
                    headers["Authorization"] = self.api_token
                else:
                    headers["Authorization"] = f"Basic {self.api_token}"

            connect_timeout = float(os.getenv("ONEC_CONNECT_TIMEOUT", "60.0"))
            read_timeout = float(os.getenv("ONEC_READ_TIMEOUT", "300.0"))

            timeout_config = httpx.Timeout(
                connect=connect_timeout,
                read=read_timeout,
                write=30.0,
                pool=60.0,
            )

            self.client = httpx.AsyncClient(
                timeout=timeout_config,
                headers=headers,
                verify=True,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def close(self):
        if self.client:
            await self.client.aclose()

    def _url(self, endpoint: str) -> str:
        endpoint_clean = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        return f"{self.api_url}{endpoint_clean}"

    @staticmethod
    def _is_missing_field_error(resp: httpx.Response) -> bool:
        try:
            if resp.status_code != 400:
                return False
            text = resp.text or ""
            return "Сегмент пути" in text or "not found" in text.lower()
        except Exception:
            return False

    async def _request_json(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> Tuple[int, Dict[str, Any]]:
        if not self.client:
            raise ValueError("ONEC_API_URL не настроен")

        url = self._url(endpoint)
        last_exc: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                resp = await self.client.request(method, url, params=params, json=json_body)
                if resp.status_code >= 500 and attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                if not resp.content:
                    return resp.status_code, {}
                return resp.status_code, resp.json()
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RequestError) as e:
                last_exc = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                body = (e.response.text or "")[:2000]
                logger.error("1C HTTP %s %s -> %s: %s", method, url, status_code, body)
                raise
            except Exception as e:
                last_exc = e
                raise

        if last_exc:
            raise last_exc
        raise RuntimeError("Не удалось выполнить запрос к 1С")

    async def find_discount_card_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        params = {"$filter": f"КодКартыШтрихкод eq '{phone}' and DeletionMark eq false", "$top": 1}
        try:
            _, data = await self._request_json("GET", self.discount_cards_endpoint, params=params)
        except httpx.HTTPStatusError as error:
            body = error.response.text or ""
            if "КодКартыШтрихкод" not in body and "Операция не разрешена" not in body:
                raise
            logger.warning("1С не поддерживает filter по штрихкоду карты, использую scan fallback")
            offset = 0
            page_size = 1000
            while True:
                _, data = await self._request_json(
                    "GET",
                    self.discount_cards_endpoint,
                    params={"$top": page_size, "$skip": offset, "$orderby": "Code"},
                )
                values = data.get("value") or []
                for item in values:
                    if (
                        str(item.get("КодКартыШтрихкод") or "") == str(phone)
                        and not bool(item.get("DeletionMark"))
                    ):
                        return item
                if len(values) < page_size:
                    break
                offset += page_size
            return None
        values = data.get("value") or []
        return values[0] if values else None

    async def find_customer_by_fields(self, candidates: List[Tuple[str, str]]) -> Optional[Dict[str, Any]]:
        for field_name, value in candidates:
            safe_value = str(value or "").replace("'", "''")
            params = {"$filter": f"{field_name} eq '{safe_value}' and DeletionMark eq false", "$top": 1}
            try:
                _, data = await self._request_json("GET", self.customers_endpoint, params=params)
            except httpx.HTTPStatusError as e:
                if self._is_missing_field_error(e.response):
                    continue
                raise
            values = data.get("value") or []
            if values:
                return values[0]
        return None

    async def create_customer(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        _, data = await self._request_json("POST", self.customers_endpoint, json_body=payload)
        return data or payload

    async def fetch_customer_by_ref_key(self, customer_ref_key: str) -> Optional[Dict[str, Any]]:
        _, data = await self._request_json(
            "GET",
            self.customers_endpoint,
            params={"$filter": f"Ref_Key eq guid'{customer_ref_key}'", "$top": 1},
        )
        values = data.get("value") or []
        return values[0] if values else None

    async def update_customer(self, customer_ref_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        endpoint = f"{self.customers_endpoint}(guid'{customer_ref_key}')"
        _, data = await self._request_json("PATCH", endpoint, json_body=payload)
        return data or payload

    async def find_property_value(self, property_ref_key: str, description: str) -> Optional[Dict[str, Any]]:
        endpoint = "/Catalog_ЗначенияСвойствОбъектов"
        safe_description = str(description or "").replace("'", "''")
        params = {
            "$filter": f"Owner_Key eq guid'{property_ref_key}' and Description eq '{safe_description}'",
            "$top": 1,
        }
        _, data = await self._request_json("GET", endpoint, params=params)
        values = data.get("value") or []
        return values[0] if values else None

    async def create_property_value(self, property_ref_key: str, description: str) -> Dict[str, Any]:
        endpoint = "/Catalog_ЗначенияСвойствОбъектов"
        body = {
            "Owner_Key": property_ref_key,
            "Description": description,
            "ПолноеНаименование": description,
            "IsFolder": False,
        }
        _, data = await self._request_json("POST", endpoint, json_body=body)
        return data or body

    async def create_discount_card(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        _, data = await self._request_json("POST", self.discount_cards_endpoint, json_body=payload)
        return data or payload

    async def update_discount_card(self, card_ref_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        endpoint = f"{self.discount_cards_endpoint}(guid'{card_ref_key}')"
        _, data = await self._request_json("PATCH", endpoint, json_body=payload)
        return data or payload

    async def find_welcome_bonus_doc(self, comment: str) -> Optional[Dict[str, Any]]:
        endpoint = "/Document_НачислениеСписаниеБонусныхБаллов"
        select_fields = "Ref_Key,Number,Date,Posted,Комментарий"
        params = {"$filter": f"Комментарий eq '{comment}'", "$top": 1, "$select": select_fields}
        try:
            _, data = await self._request_json("GET", endpoint, params=params)
        except httpx.HTTPStatusError as error:
            body = error.response.text or ""
            if "Неверные параметры в операции сравнения" not in body and "Комментарий" not in body:
                raise
            logger.warning("1С не поддерживает filter по Комментарий для бонусных документов, использую scan fallback")
            _, data = await self._request_json(
                "GET",
                endpoint,
                params={"$top": 50, "$orderby": "Date desc", "$select": select_fields},
            )
        values = data.get("value") or []
        for item in values:
            if str(item.get("Комментарий") or "") == comment:
                return item
        return None

    async def create_welcome_bonus_doc(
        self,
        bonus_program_key: str,
        card_ref_key: str,
        points: int,
        comment: str,
        analytics_key: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        endpoint = "/Document_НачислениеСписаниеБонусныхБаллов"
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        accrual: Dict[str, Any] = {
            "LineNumber": 1,
            "БонуснаяКарта_Key": card_ref_key,
            "Количество": float(points),
            "ДатаНачисления": now,
        }
        if analytics_key:
            accrual["АналитикаНачисленияБонусов_Key"] = analytics_key
        if expires_at:
            accrual["ДатаСгорания"] = expires_at

        payload: Dict[str, Any] = {
            "Date": now,
            "Posted": True,
            "БонуснаяПрограмма_Key": bonus_program_key,
            "Комментарий": comment,
            "НачисленияБонусов": [accrual],
        }
        _, data = await self._request_json("POST", endpoint, json_body=payload)
        return data or payload

    async def create_bonus_spend_doc(
        self,
        bonus_program_key: str,
        card_ref_key: str,
        points: int,
        comment: str,
    ) -> Dict[str, Any]:
        endpoint = "/Document_НачислениеСписаниеБонусныхБаллов"
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        expires_days = int(os.getenv("ONEC_GLM_BRIDGE_SPEND_EXPIRES_DAYS") or os.getenv("ONEC_WELCOME_BONUS_EXPIRES_DAYS", "365"))
        expires_at = (datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=expires_days)).isoformat()
        analytics_key = (
            os.getenv("ONEC_GLM_BRIDGE_SPEND_ANALYTICS_KEY")
            or os.getenv("ONEC_WELCOME_BONUS_ANALYTICS_KEY")
        )
        accrual: Dict[str, Any] = {
            "LineNumber": 1,
            "БонуснаяКарта_Key": card_ref_key,
            "Количество": -float(points),
            "ДатаНачисления": now,
            "ДатаСгорания": expires_at,
        }
        if analytics_key:
            accrual["АналитикаНачисленияБонусов_Key"] = analytics_key

        payload: Dict[str, Any] = {
            "Date": now,
            "Posted": True,
            "БонуснаяПрограмма_Key": bonus_program_key,
            "Комментарий": comment,
            "НачисленияБонусов": [accrual],
            "СписанияБонусов": [],
        }
        _, data = await self._request_json("POST", endpoint, json_body=payload)
        return data or payload

    async def update_welcome_bonus_doc(
        self,
        doc_ref_key: str,
        bonus_program_key: str,
        card_ref_key: str,
        points: int,
        comment: str,
        analytics_key: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        endpoint = f"/Document_НачислениеСписаниеБонусныхБаллов(guid'{doc_ref_key}')"
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        accrual: Dict[str, Any] = {
            "LineNumber": 1,
            "БонуснаяКарта_Key": card_ref_key,
            "Количество": float(points),
            "ДатаНачисления": now,
        }
        if analytics_key:
            accrual["АналитикаНачисленияБонусов_Key"] = analytics_key
        if expires_at:
            accrual["ДатаСгорания"] = expires_at

        payload: Dict[str, Any] = {
            "Posted": True,
            "БонуснаяПрограмма_Key": bonus_program_key,
            "Комментарий": comment,
            "НачисленияБонусов": [accrual],
        }
        _, data = await self._request_json("PATCH", endpoint, json_body=payload)
        return data or payload

    async def update_bonus_spend_doc(
        self,
        doc_ref_key: str,
        bonus_program_key: str,
        card_ref_key: str,
        points: int,
        comment: str,
    ) -> Dict[str, Any]:
        endpoint = f"/Document_НачислениеСписаниеБонусныхБаллов(guid'{doc_ref_key}')"
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        expires_days = int(os.getenv("ONEC_GLM_BRIDGE_SPEND_EXPIRES_DAYS") or os.getenv("ONEC_WELCOME_BONUS_EXPIRES_DAYS", "365"))
        expires_at = (datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=expires_days)).isoformat()
        analytics_key = (
            os.getenv("ONEC_GLM_BRIDGE_SPEND_ANALYTICS_KEY")
            or os.getenv("ONEC_WELCOME_BONUS_ANALYTICS_KEY")
        )
        accrual: Dict[str, Any] = {
            "LineNumber": 1,
            "БонуснаяКарта_Key": card_ref_key,
            "Количество": -float(points),
            "ДатаНачисления": now,
            "ДатаСгорания": expires_at,
        }
        if analytics_key:
            accrual["АналитикаНачисленияБонусов_Key"] = analytics_key

        payload: Dict[str, Any] = {
            "Posted": True,
            "БонуснаяПрограмма_Key": bonus_program_key,
            "Комментарий": comment,
            "НачисленияБонусов": [accrual],
            "СписанияБонусов": [],
        }
        _, data = await self._request_json("PATCH", endpoint, json_body=payload)
        return data or payload

    async def create_bonus_lot_repair_doc(
        self,
        bonus_program_key: str,
        card_ref_key: str,
        points: int,
        comment: str,
    ) -> Dict[str, Any]:
        """Reduce visual accrual lots without changing current spendable balance."""
        endpoint = "/Document_НачислениеСписаниеБонусныхБаллов"
        now_dt = datetime.now(timezone.utc).replace(microsecond=0)
        now = now_dt.isoformat()
        expires_days = int(os.getenv("ONEC_GLM_BRIDGE_SPEND_EXPIRES_DAYS") or os.getenv("ONEC_WELCOME_BONUS_EXPIRES_DAYS", "365"))
        expires_at = (now_dt + timedelta(days=expires_days)).isoformat()
        analytics_key = (
            os.getenv("ONEC_GLM_BRIDGE_SPEND_ANALYTICS_KEY")
            or os.getenv("ONEC_WELCOME_BONUS_ANALYTICS_KEY")
        )
        accrual: Dict[str, Any] = {
            "LineNumber": 1,
            "БонуснаяКарта_Key": card_ref_key,
            "Количество": -float(points),
            "ДатаНачисления": now,
            "ДатаСгорания": expires_at,
        }
        if analytics_key:
            accrual["АналитикаНачисленияБонусов_Key"] = analytics_key
        spend: Dict[str, Any] = {
            "LineNumber": 1,
            "БонуснаяКарта_Key": card_ref_key,
            "Количество": 0.0,
            "КорректировкаКСписанию": -float(points),
        }
        payload: Dict[str, Any] = {
            "Date": now,
            "Posted": True,
            "БонуснаяПрограмма_Key": bonus_program_key,
            "Комментарий": comment,
            "НачисленияБонусов": [accrual],
            "СписанияБонусов": [spend],
        }
        _, data = await self._request_json("POST", endpoint, json_body=payload)
        return data or payload

    async def unpost_welcome_bonus_doc(self, doc_ref_key: str) -> None:
        endpoint = f"/Document_НачислениеСписаниеБонусныхБаллов(guid'{doc_ref_key}')/Unpost"
        await self._request_json("POST", endpoint, json_body={"PostingModeOperational": True})

    async def post_welcome_bonus_doc(self, doc_ref_key: str) -> None:
        endpoint = f"/Document_НачислениеСписаниеБонусныхБаллов(guid'{doc_ref_key}')/Post"
        await self._request_json("POST", endpoint, json_body={"PostingModeOperational": True})
