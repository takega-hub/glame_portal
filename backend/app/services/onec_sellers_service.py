"""Read-only service for fetching GLAME sellers/employees from 1C OData."""
from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


class OneCSellersService:
    """Fetch sellers/employees from 1C without writing anything to local DB."""

    DEFAULT_ENDPOINTS = [
        "/Catalog_Сотрудники",
        "/Catalog_ФизическиеЛица",
        "/Catalog_Пользователи",
        "/Catalog_ОтветственныеЛица",
        "/Catalog_Менеджеры",
        "/Catalog_Employees",
        "/Catalog_Users",
    ]
    COLLECTION_KEYWORDS = (
        "сотруд",
        "продав",
        "менедж",
        "пользовател",
        "employee",
        "seller",
        "salesperson",
        "manager",
        "user",
    )

    def __init__(self, api_url: Optional[str] = None, api_token: Optional[str] = None, sellers_endpoint: Optional[str] = None):
        self.api_url = api_url or os.getenv("ONEC_API_URL")
        self.api_token = api_token or os.getenv("ONEC_API_TOKEN")
        self.sellers_endpoint = sellers_endpoint or os.getenv("ONEC_SELLERS_ENDPOINT")
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "OneCSellersService":
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.client:
            await self.client.aclose()
            self.client = None

    async def _ensure_client(self) -> None:
        if self.client:
            return
        if not self.api_url:
            raise ValueError("ONEC_API_URL не настроен")

        headers = {"Accept": "application/json"}
        if self.api_token:
            if self.api_token.startswith("Basic "):
                headers["Authorization"] = self.api_token
            else:
                headers["Authorization"] = f"Basic {self.api_token}"

        self.client = httpx.AsyncClient(timeout=120.0, headers=headers, verify=True)

    def _url(self, endpoint: str) -> str:
        base = (self.api_url or "").rstrip("/")
        safe_endpoint = quote(endpoint, safe="/$()_',=")
        return f"{base}{safe_endpoint}"

    async def discover_seller_endpoints(self) -> List[str]:
        """Discover likely seller-related collections from the 1C service document."""
        await self._ensure_client()
        assert self.client is not None

        discovered: List[str] = []
        try:
            response = await self.client.get((self.api_url or "").rstrip("/"), headers={"Accept": "application/xml"})
            response.raise_for_status()
            root = ET.fromstring(response.text)
            namespaces = {
                "app": "http://www.w3.org/2007/app",
                "atom": "http://www.w3.org/2005/Atom",
            }
            for coll in root.findall(".//app:collection", namespaces):
                href = coll.get("href") or ""
                title_elem = coll.find("atom:title", namespaces)
                title = title_elem.text if title_elem is not None and title_elem.text else ""
                combined = f"{href} {title}".lower()
                if href and any(keyword in combined for keyword in self.COLLECTION_KEYWORDS):
                    endpoint = href if href.startswith("/") else f"/{href}"
                    if endpoint not in discovered:
                        discovered.append(endpoint)
        except Exception as exc:
            logger.debug("Не удалось получить service document 1С для поиска продавцов: %s", exc)
        return discovered

    async def fetch_page(self, endpoint: str, top: int, skip: int) -> List[Dict[str, Any]]:
        await self._ensure_client()
        assert self.client is not None

        response = await self.client.get(self._url(endpoint), params={"$top": top, "$skip": skip})
        response.raise_for_status()
        data = response.json()
        value = data.get("value") if isinstance(data, dict) else None
        return value if isinstance(value, list) else []

    async def fetch_from_endpoint(self, endpoint: str, limit: int) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        top = min(max(limit, 1), 1000)
        skip = 0
        while len(items) < limit:
            page = await self.fetch_page(endpoint, top=min(top, limit - len(items)), skip=skip)
            if not page:
                break
            items.extend(page)
            if len(page) < top:
                break
            skip += top
        return items

    def endpoint_candidates(self, discovered: List[str]) -> List[str]:
        candidates: List[str] = []
        if self.sellers_endpoint:
            candidates.append(self.sellers_endpoint)
        for endpoint in [*self.DEFAULT_ENDPOINTS, *discovered]:
            if endpoint not in candidates:
                candidates.append(endpoint)
        return candidates

    async def fetch_sellers(self, limit: int = 200) -> Dict[str, Any]:
        """Fetch active seller/staff records from the first working 1C endpoint.

        1C Catalog_Сотрудники also returns folders and employees moved to the
        "Уволенные" folder. The platform list must show only current store staff,
        so filtering is applied before returning data to the UI.
        """
        discovered = await self.discover_seller_endpoints()
        errors: List[Dict[str, Any]] = []

        for endpoint in self.endpoint_candidates(discovered):
            try:
                raw_items = await self.fetch_from_endpoint(endpoint, limit=limit)
                if raw_items:
                    filtered_items = self.filter_active_seller_items(raw_items)
                    sellers = [self.map_seller(item) for item in filtered_items]
                    return {
                        "endpoint": endpoint,
                        "count": len(sellers),
                        "total_loaded": len(raw_items),
                        "filtered_out": max(len(raw_items) - len(sellers), 0),
                        "filter": "active_store_staff",
                        "sellers": sellers,
                        "discovered_endpoints": discovered,
                    }
            except httpx.HTTPStatusError as exc:
                errors.append({"endpoint": endpoint, "status": exc.response.status_code})
                if exc.response.status_code in {400, 401, 403, 404}:
                    continue
                raise
            except Exception as exc:
                errors.append({"endpoint": endpoint, "error": str(exc)})
                continue

        return {
            "endpoint": None,
            "count": 0,
            "total_loaded": 0,
            "filtered_out": 0,
            "filter": "active_store_staff",
            "sellers": [],
            "discovered_endpoints": discovered,
            "errors": errors[-8:],
        }

    @staticmethod
    def filter_active_seller_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove folders, fired employees and non-store staff from 1C staff catalog."""
        fired_folder_keys = {
            str(item.get("Ref_Key"))
            for item in items
            if item.get("IsFolder") and "уволен" in str(item.get("Description") or item.get("Наименование") or "").lower()
        }
        active_names_env = os.getenv("ONEC_ACTIVE_SELLER_NAMES") or os.getenv("GLAME_ACTIVE_SELLER_NAMES") or ""
        active_names = {name.strip().lower() for name in active_names_env.split(",") if name.strip()}
        excluded_names_env = os.getenv("ONEC_EXCLUDED_SELLER_NAMES") or os.getenv("GLAME_EXCLUDED_SELLER_NAMES") or ""
        excluded_names = {
            "маркетолог/смм",
            "продавец",
            "управляющий магазином",
            "уволенные",
            # Owners/back-office accounts can exist in 1C staff catalog, but they
            # are not store seller rows from the staffing schedule.
            "орешников анатолий анатольевич",
            "орешникова елена сергеевна",
            *[name.strip().lower() for name in excluded_names_env.split(",") if name.strip()],
        }

        result: List[Dict[str, Any]] = []
        for item in items:
            name = str(item.get("Description") or item.get("Наименование") or item.get("Name") or "").strip()
            name_lower = name.lower()
            parent_key = str(item.get("Parent_Key") or "")
            staff_code = str(item.get("МагнитныйКод") or item.get("ШтрихКод") or "").strip()

            if item.get("IsFolder"):
                continue
            if item.get("DeletionMark") or item.get("ПометкаУдаления"):
                continue
            if item.get("ВАрхиве") or item.get("Недействителен"):
                continue
            if parent_key in fired_folder_keys:
                continue
            if not name or "ваканси" in name_lower or name_lower in excluded_names:
                continue
            if active_names and name_lower not in active_names:
                continue
            # Store staff from the staffing sheet have a табельный/магнитный code.
            # Empty codes are service/non-retail records in the current 1C catalog.
            if not staff_code:
                continue
            result.append(item)
        return result

    @staticmethod
    def map_seller(item: Dict[str, Any]) -> Dict[str, Any]:
        external_id = item.get("Ref_Key") or item.get("Ref") or item.get("Key") or item.get("ID") or item.get("Code")
        name = (
            item.get("Description")
            or item.get("Наименование")
            or item.get("Name")
            or item.get("ФИО")
            or item.get("FullName")
            or item.get("ПолноеНаименование")
            or "Без имени"
        )
        code = item.get("МагнитныйКод") or item.get("ШтрихКод") or item.get("Code") or item.get("Код") or item.get("Number")
        email = item.get("Email") or item.get("E-mail") or item.get("ЭлектроннаяПочта") or item.get("АдресЭлектроннойПочты")
        phone = item.get("Phone") or item.get("Телефон") or item.get("МобильныйТелефон") or item.get("НомерТелефона")
        store = item.get("Склад") or item.get("Склад_Key") or item.get("Магазин") or item.get("Подразделение") or item.get("Подразделение_Key")
        position = item.get("Должность") or item.get("Position") or item.get("Роль") or item.get("Role")
        is_deleted = bool(item.get("DeletionMark") or item.get("ПометкаУдаления"))

        return {
            "external_id": str(external_id) if external_id is not None else None,
            "name": str(name),
            "code": str(code) if code is not None else None,
            "email": str(email) if email is not None else None,
            "phone": str(phone) if phone is not None else None,
            "store": str(store) if store is not None else None,
            "position": str(position) if position is not None else None,
            "is_deleted": is_deleted,
            "raw": item,
        }
