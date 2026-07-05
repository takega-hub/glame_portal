"""
Сервис для получения статистики продаж из 1С УНФ ФРЕШ
Поддержка OData API и файлов (JSON, XML, CSV)
"""
import httpx
import json
import base64
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import os
from collections import defaultdict
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

KNOWN_SELLER_NAMES_BY_EXTERNAL_ID = {
    "6ded351c-4a43-11f1-9b6c-fa163e4cc04e": "Максимычева Евгения",
    "4a1f26ca-a92d-11f0-9b6c-fa163e4cc04e": "Уразгильдеева Екатерина",
    "1d5f839e-ba5a-11f0-836e-fa163e4cc04e": "Рогалевич Ирина",
    "eee9caf0-293b-11f1-83c6-fa163e4cc04e": "Бешлиева Аджере",
    "4d189eb8-4ee8-11f1-9b97-fa163e4cc04e": "Орешников Анатолий",
}
ZERO_GUID = "00000000-0000-0000-0000-000000000000"
MSK_TZ = ZoneInfo("Europe/Moscow")


class OneCSalesService:
    """Сервис для работы со статистикой продаж из 1С"""
    
    def __init__(
        self,
        api_url: Optional[str] = None,
        api_token: Optional[str] = None,
        sales_endpoint: Optional[str] = None
    ):
        self.api_url = api_url or os.getenv("ONEC_API_URL")
        self.api_token = api_token or os.getenv("ONEC_API_TOKEN")
        
        # По умолчанию используем AccumulationRegister_Продажи_RecordType для детальных данных по товарам
        # Если не задано в окружении, используем именно этот регистр
        self.sales_endpoint = sales_endpoint or os.getenv("ONEC_SALES_ENDPOINT", "/AccumulationRegister_Продажи_RecordType")
        
        self.client = None
        if self.api_url:
            headers = {
                "Accept": "application/json"
            }
            if self.api_token:
                # Поддержка Basic Auth (для 1С OData)
                # Если токен уже в формате base64, используем его напрямую
                if self.api_token.startswith("Basic "):
                    headers["Authorization"] = self.api_token
                else:
                    # Предполагаем, что токен уже в base64 формате
                    headers["Authorization"] = f"Basic {self.api_token}"
            
            self.client = httpx.AsyncClient(
                timeout=120.0,
                headers=headers,
                verify=True
            )
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    async def close(self):
        if self.client:
            await self.client.aclose()

    def _to_1c_local_naive(self, value: datetime) -> datetime:
        """1С отдает даты документов без timezone, фактически в московском времени."""
        if value.tzinfo is not None:
            return value.astimezone(MSK_TZ).replace(tzinfo=None)
        return value
    
    async def fetch_sales_from_api(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        customer_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Получение данных о продажах через OData API
        
        Args:
            start_date: Начальная дата периода
            end_date: Конечная дата периода
            customer_key: ID покупателя для фильтрации (опционально)
        """
        if not self.client:
            raise ValueError("API URL не настроен")
        
        if not start_date:
            start_date = datetime.now() - timedelta(days=30)
        if not end_date:
            end_date = datetime.now()
        
        # Формируем URL для OData запроса
        url = f"{self.api_url.rstrip('/')}{self.sales_endpoint}"
        
        # Формируем OData фильтр
        # В 1С OData фильтры по датам могут работать по-разному
        # Попробуем сначала без фильтра по дате, если будет ошибка
        filters = []
        
        # Для 1С лучше не использовать фильтр по дате в запросе,
        # а фильтровать на стороне приложения, так как формат может отличаться
        # Но если нужен фильтр, используем простой формат
        if start_date and end_date:
            # Форматируем даты для OData
            start_str = start_date.strftime("%Y-%m-%dT00:00:00")
            end_str = end_date.strftime("%Y-%m-%dT23:59:59")
            # В 1С OData может требовать другой формат, поэтому пробуем без фильтра по дате
            # и фильтруем на стороне приложения
            pass  # Пока не используем фильтр по дате в запросе
        
        if customer_key:
            filters.append(f"Контрагент_Key eq guid'{customer_key}'")

        try:
            logger.info(f"Запрос к 1С OData API: {url}")
            check_orders = await self._fetch_check_orders_from_documents(start_date, end_date, customer_key)
            if check_orders:
                logger.info("Получено чеков/строк из Document_ЧекККМ: %s", len(check_orders))
                return {"orders": check_orders, "source": "Document_ЧекККМ"}

            records = await self._fetch_recent_register_records(url, start_date, end_date, filters)
            
            if records is not None:
                logger.info(f"Получено записей из 1С: {len(records)}")
                
                # Преобразуем OData формат в наш формат
                orders = []
                for idx, record in enumerate(records):
                    # Фильтруем по дате на стороне приложения
                    period = record.get('Period')
                    if idx == 0:
                        logger.debug(f"First record period: {period}")

                    if period:
                        try:
                            if isinstance(period, str):
                                # Убираем микросекунды и timezone если есть
                                period_clean = period.split('.')[0].replace('Z', '')
                                record_date = datetime.fromisoformat(period_clean)
                            else:
                                record_date = period
                            
                            if idx == 0:
                                logger.debug(f"Parsed date: {record_date}, Start: {start_date}, End: {end_date}")

                            # Применяем фильтр по дате
                            # Приводим даты к одному формату (naive) для сравнения
                            check_date = record_date.replace(tzinfo=None)
                            check_start = self._to_1c_local_naive(start_date) if start_date else None
                            check_end = self._to_1c_local_naive(end_date) if end_date else None
                            
                            if check_start and check_date < check_start:
                                if idx == 0:
                                    logger.debug(f"Filtered out by start date: {check_date} < {check_start}")
                                continue
                            if check_end and check_date > check_end:
                                if idx == 0:
                                    logger.debug(f"Filtered out by end date: {check_date} > {check_end}")
                                continue
                        except Exception as e:
                            logger.warning(f"Ошибка парсинга даты {period}: {e}")
                            # Если не удалось распарсить дату, пропускаем фильтрацию
                    
                    # Получаем сумму и количество
                    сумма = record.get('Сумма') or record.get('СуммаИнт') or 0
                    количество = record.get('Количество') or record.get('КоличествоИнт') or 0
                    
                    # Формируем уникальный ID для записи (документ + номер строки для детальности)
                    line_number = record.get('LineNumber') or ""
                    recorder = record.get('Recorder') or record.get('Документ') or ""
                    
                    # Если есть номер строки, добавляем его к ID для уникальности каждой позиции в чеке
                    if line_number:
                        sale_id = f"{recorder}_{line_number}"
                    else:
                        sale_id = recorder
                    
                    orders.append({
                        "id": sale_id,
                        "date": period,
                        "revenue": float(сумма) if сумма else 0.0,
                        "items_count": float(количество) if количество else 0.0,
                        "customer_id": record.get('Контрагент_Key'),
                        "product_id": record.get('Номенклатура_Key'),
                        "store_id": record.get('Склад_Key'),
                        "organization_id": record.get('Организация_Key'),
                        "document_id": recorder,
                        "channel": "offline",  # По умолчанию офлайн продажи
                        "raw_1c_data": record  # Сохраняем исходные данные из 1С для полного сохранения в БД
                    })
                
                orders, report_scopes = await self._prepare_retail_report_orders(orders)
                logger.info(f"После фильтрации осталось заказов: {len(orders)}")
                return {"orders": orders, "report_scopes": report_scopes}
            else:
                return {"orders": []}
                
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP ошибка при запросе к 1С API: {e.response.status_code}")
            logger.error(f"Ответ: {e.response.text[:500]}")
            if e.response.status_code in {401, 403}:
                logger.error(
                    "1С OData отклонила доступ к %s. Проверьте ONEC_API_TOKEN, "
                    "права пользователя OData и ONEC_SALES_ENDPOINT=%s",
                    url,
                    self.sales_endpoint,
                )
            raise
        except Exception as e:
            logger.error(f"Ошибка при запросе к 1С API: {e}")
            raise

    async def _fetch_check_orders_from_documents(
        self,
        start_date: datetime,
        end_date: datetime,
        customer_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        documents = await self._fetch_recent_documents(
            endpoint="Document_ЧекККМ",
            start_date=start_date,
            end_date=end_date,
        )
        orders: List[Dict[str, Any]] = []

        for document in documents:
            if not document.get("Posted") or document.get("DeletionMark"):
                continue
            if customer_key and document.get("Контрагент_Key") != customer_key:
                continue

            document_id = document.get("Ref_Key")
            document_date = document.get("Date")
            store_id = document.get("СтруктурнаяЕдиница_Key") or document.get("Склад_Key")
            discount_card_id = document.get("ДисконтнаяКарта_Key")
            seller_id = (
                document.get("Продавец_Key")
                or document.get("Сотрудник_Key")
                or document.get("Кассир_Key")
                or document.get("Ответственный_Key")
                or document.get("Менеджер_Key")
            )
            seller_name = (
                document.get("Продавец")
                or document.get("Сотрудник")
                or document.get("Кассир")
                or document.get("Ответственный")
                or document.get("Менеджер")
            )
            if not seller_name and seller_id in KNOWN_SELLER_NAMES_BY_EXTERNAL_ID:
                seller_name = KNOWN_SELLER_NAMES_BY_EXTERNAL_ID[seller_id]
            stocks = document.get("Запасы") or []
            if not document_id or not document_date or not isinstance(stocks, list):
                continue

            line_sum = 0.0
            for line in stocks:
                line_number = line.get("LineNumber") or len(orders) + 1
                amount = line.get("Сумма")
                if amount is None:
                    amount = line.get("Всего")
                quantity = line.get("Количество") or 0
                line_sum += float(amount or 0.0)
                raw_line = {
                    **line,
                    "Recorder": document_id,
                    "Recorder_Type": "StandardODATA.Document_ЧекККМ",
                    "Period": document_date,
                    "DocumentDate": document_date,
                    "СуммаДокумента": document.get("СуммаДокумента"),
                    "СтруктурнаяЕдиница_Key": store_id,
                    "ДисконтнаяКарта_Key": discount_card_id,
                    "Продавец_Key": seller_id,
                    "Продавец": seller_name,
                    "Контрагент_Key": document.get("Контрагент_Key"),
                    "Организация_Key": document.get("Организация_Key"),
                }
                orders.append({
                    "id": f"{document_id}_{line_number}",
                    "date": document_date,
                    "revenue": float(amount or 0.0),
                    "items_count": float(quantity or 0.0),
                    "customer_id": document.get("Контрагент_Key"),
                    "product_id": line.get("Номенклатура_Key"),
                    "store_id": store_id,
                    "organization_id": document.get("Организация_Key"),
                    "document_id": document_id,
                    "channel": "offline",
                    "revenue_without_discount": float((line.get("Цена") or 0.0) * (quantity or 0.0)),
                    "raw_1c_data": raw_line,
                })

            document_total = document.get("СуммаДокумента")
            if document_total is not None and stocks:
                diff = round(float(document_total) - line_sum, 2)
                if abs(diff) >= 0.01:
                    orders.append({
                        "id": f"{document_id}_total_adjustment",
                        "date": document_date,
                        "revenue": diff,
                        "items_count": 0.0,
                        "customer_id": document.get("Контрагент_Key"),
                        "product_id": None,
                        "store_id": store_id,
                        "organization_id": document.get("Организация_Key"),
                        "document_id": document_id,
                        "channel": "offline",
                        "product_name": "Корректировка суммы чека",
                        "raw_1c_data": {
                            "Recorder": document_id,
                            "Recorder_Type": "StandardODATA.Document_ЧекККМ",
                            "LineNumber": "total_adjustment",
                            "Period": document_date,
                            "Сумма": diff,
                            "Количество": 0,
                            "СтруктурнаяЕдиница_Key": store_id,
                            "СуммаДокумента": document_total,
                            "Продавец_Key": seller_id,
                            "Продавец": seller_name,
                        },
                    })

        return orders

    async def _fetch_recent_documents(
        self,
        endpoint: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[Dict[str, Any]]:
        page_size = 100
        url = f"{self.api_url.rstrip('/')}/{endpoint}"
        count_response = await self.client.get(f"{url}/$count")
        count_response.raise_for_status()
        total_count = int(str(count_response.text).strip() or 0)
        if total_count <= 0:
            return []

        check_start = self._to_1c_local_naive(start_date)
        check_end = self._to_1c_local_naive(end_date)
        documents: List[Dict[str, Any]] = []

        skip = max(total_count - page_size, 0)
        while skip >= 0:
            response = await self.client.get(url, params={"$top": page_size, "$skip": skip})
            response.raise_for_status()
            page_documents = response.json().get("value", [])
            if not page_documents:
                break

            page_has_needed_documents = False
            page_oldest_date = None

            for document in page_documents:
                document_date = self._parse_1c_datetime(document.get("Date"))
                if not document_date:
                    continue
                document_date = document_date.replace(tzinfo=None)
                page_oldest_date = document_date if page_oldest_date is None else min(page_oldest_date, document_date)
                if check_start <= document_date <= check_end:
                    documents.append(document)
                    page_has_needed_documents = True

            if page_oldest_date and page_oldest_date < check_start and not page_has_needed_documents:
                break
            if skip == 0:
                break
            skip = max(skip - page_size, 0)

        return documents

    async def _fetch_recent_register_records(
        self,
        url: str,
        start_date: datetime,
        end_date: datetime,
        filters: List[str],
    ) -> List[Dict[str, Any]]:
        """
        1С Fresh не разрешает фильтр по Period для этого регистра и игнорирует desc sort.
        Поэтому для ежедневной синхронизации берем последние страницы по $count/$skip и
        останавливаемся, когда ушли раньше нужного периода.
        """
        page_size = 1000

        if filters:
            params = {"$top": page_size, "$filter": " and ".join(filters)}
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json().get("value", [])

        count_response = await self.client.get(f"{url.rstrip('/')}/$count")
        count_response.raise_for_status()
        total_count = int(str(count_response.text).strip() or 0)
        if total_count <= 0:
            return []

        check_start = self._to_1c_local_naive(start_date)
        check_end = self._to_1c_local_naive(end_date)
        all_records: List[Dict[str, Any]] = []

        skip = max(total_count - page_size, 0)
        while skip >= 0:
            params = {"$top": page_size, "$skip": skip}
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            page_records = response.json().get("value", [])
            if not page_records:
                break

            page_has_needed_records = False
            page_oldest_date = None

            for record in page_records:
                record_date = self._parse_1c_datetime(record.get("Period"))
                if not record_date:
                    continue

                record_date = record_date.replace(tzinfo=None)
                page_oldest_date = record_date if page_oldest_date is None else min(page_oldest_date, record_date)

                if check_start <= record_date <= check_end:
                    all_records.append(record)
                    page_has_needed_records = True

            if page_oldest_date and page_oldest_date < check_start and not page_has_needed_records:
                break
            if skip == 0:
                break
            skip = max(skip - page_size, 0)

        return all_records

    def _parse_1c_datetime(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00").split(".")[0])
            except Exception:
                return None
        return None

    async def _prepare_retail_report_orders(
        self,
        orders: List[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        report_docs: Dict[str, Dict[str, Any]] = {}
        for order in orders:
            raw = order.get("raw_1c_data") or {}
            recorder_type = str(raw.get("Recorder_Type") or raw.get("Документ_Type") or "")
            if "ОтчетОРозничныхПродажах" not in recorder_type:
                continue
            document_id = order.get("document_id")
            if not document_id:
                continue
            report_docs.setdefault(document_id, {"line_sum": 0.0, "orders": []})
            report_docs[document_id]["line_sum"] += float(order.get("revenue") or 0.0)
            report_docs[document_id]["orders"].append(order)

        report_scopes: List[Dict[str, str]] = []
        for document_id, data in report_docs.items():
            document = await self._fetch_retail_report_document(document_id)
            document_store = document.get("СтруктурнаяЕдиница_Key") or document.get("Склад_Key")
            document_total = document.get("СуммаДокумента")

            if document_store:
                for order in data["orders"]:
                    order["store_id"] = document_store

            first_order = data["orders"][0] if data["orders"] else None
            sale_date = self._parse_1c_datetime(first_order.get("date")) if first_order else None
            if sale_date and document_store:
                report_scopes.append({
                    "date": sale_date.date().isoformat(),
                    "store_id": document_store,
                    "document_id": document_id,
                })

            if document_total is None or not first_order:
                continue

            diff = round(float(document_total) - float(data["line_sum"] or 0.0), 2)
            if abs(diff) < 0.01:
                continue

            raw_adjustment = {
                "Recorder": document_id,
                "Recorder_Type": "StandardODATA.Document_ОтчетОРозничныхПродажах",
                "LineNumber": "total_adjustment",
                "Period": first_order.get("date"),
                "Сумма": diff,
                "Количество": 0,
                "СтруктурнаяЕдиница_Key": document_store,
                "ДокументальнаяСумма": document_total,
            }
            orders.append({
                "id": f"{document_id}_total_adjustment",
                "date": first_order.get("date"),
                "revenue": diff,
                "items_count": 0.0,
                "customer_id": None,
                "product_id": None,
                "store_id": document_store or first_order.get("store_id"),
                "organization_id": first_order.get("organization_id"),
                "document_id": document_id,
                "channel": "offline",
                "product_name": "Корректировка суммы документа",
                "raw_1c_data": raw_adjustment,
            })

        if not report_scopes:
            return orders, []

        report_scope_keys = {(scope["date"], scope["store_id"]) for scope in report_scopes}
        filtered_orders = []
        for order in orders:
            raw = order.get("raw_1c_data") or {}
            recorder_type = str(raw.get("Recorder_Type") or raw.get("Документ_Type") or "")
            sale_date = self._parse_1c_datetime(order.get("date"))
            date_key = sale_date.date().isoformat() if sale_date else ""
            if "ЧекККМ" in recorder_type and (date_key, order.get("store_id")) in report_scope_keys:
                continue
            filtered_orders.append(order)

        return filtered_orders, report_scopes

    async def _fetch_retail_report_document(self, document_id: str) -> Dict[str, Any]:
        if not self.client or not self.api_url:
            return {}

        url = f"{self.api_url.rstrip('/')}/Document_ОтчетОРозничныхПродажах(guid'{document_id}')"
        try:
            response = await self.client.get(url)
            if response.status_code == 404:
                return {}
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.debug("Не удалось получить документ отчета о розничных продажах %s", document_id, exc_info=True)
            return {}
    
    def parse_sales_from_file(
        self,
        content: bytes,
        file_format: str = "json"
    ) -> Dict[str, Any]:
        """
        Парсинг файла с данными о продажах
        
        Args:
            content: Содержимое файла
            file_format: Формат файла (json, xml, csv)
        """
        if file_format == "json":
            return self._parse_sales_json(content)
        elif file_format == "xml":
            return self._parse_sales_xml(content)
        elif file_format == "csv":
            return self._parse_sales_csv(content)
        else:
            raise ValueError(f"Неподдерживаемый формат: {file_format}")
    
    def _parse_sales_json(self, content: bytes) -> Dict[str, Any]:
        """Парсинг JSON файла"""
        text = content.decode('utf-8')
        data = json.loads(text)
        
        # Поддержка различных структур
        if isinstance(data, list):
            return {"orders": data}
        elif isinstance(data, dict):
            return data
        else:
            raise ValueError("Неверный формат JSON")
    
    def _parse_sales_xml(self, content: bytes) -> Dict[str, Any]:
        """Парсинг XML файла"""
        import xml.etree.ElementTree as ET
        
        root = ET.fromstring(content.decode('utf-8'))
        
        orders = []
        for order in root.findall('.//order') or root.findall('.//Order'):
            orders.append({
                "id": order.findtext('id') or order.get('id'),
                "date": order.findtext('date'),
                "revenue": float(order.findtext('revenue') or order.findtext('total') or 0),
                "store_id": order.findtext('store_id'),
                "channel": order.findtext('channel'),
                "items_count": int(order.findtext('items_count') or 0)
            })
        
        return {"orders": orders}
    
    def _parse_sales_csv(self, content: bytes) -> Dict[str, Any]:
        """Парсинг CSV файла"""
        import csv
        from io import StringIO
        
        text = content.decode('utf-8')
        reader = csv.DictReader(StringIO(text))
        
        orders = []
        for row in reader:
            try:
                orders.append({
                    "id": row.get('id') or row.get('order_id'),
                    "date": row.get('date'),
                    "revenue": float(row.get('revenue') or row.get('total') or 0),
                    "store_id": row.get('store_id'),
                    "channel": row.get('channel'),
                    "items_count": int(row.get('items_count') or row.get('quantity') or 0)
                })
            except Exception as e:
                logger.warning(f"Ошибка парсинга строки CSV: {e}")
                continue
        
        return {"orders": orders}
    
    def calculate_metrics(self, sales_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Расчет метрик на основе данных о продажах
        
        Returns:
            {
                "total_revenue": float,
                "order_count": int,
                "average_order_value": float,
                "items_sold": int,
                "by_channel": {...},
                "by_store": {...}
            }
        """
        orders = sales_data.get("orders", [])
        
        if not orders:
            return {
                "total_revenue": 0.0,
                "order_count": 0,
                "average_order_value": 0.0,
                "items_sold": 0,
                "by_channel": {},
                "by_store": {}
            }
        
        total_revenue = sum(float(o.get("revenue", 0)) for o in orders)
        order_count = len(orders)
        items_sold = sum(int(o.get("items_count", 0)) for o in orders)
        
        # По каналам
        by_channel = {}
        for order in orders:
            channel = order.get("channel") or "unknown"
            if channel not in by_channel:
                by_channel[channel] = {"revenue": 0.0, "orders": 0}
            by_channel[channel]["revenue"] += float(order.get("revenue", 0))
            by_channel[channel]["orders"] += 1
        
        # По магазинам (складам)
        by_store = {}
        for order in orders:
            store_id = order.get("store_id") or order.get("Склад_Key") or "unknown"
            if store_id == "unknown" or not store_id:
                continue  # Пропускаем заказы без магазина
            
            if store_id not in by_store:
                by_store[store_id] = {
                    "revenue": 0.0, 
                    "orders": 0,
                    "items_sold": 0
                }
            by_store[store_id]["revenue"] += float(order.get("revenue", 0))
            by_store[store_id]["orders"] += 1
            by_store[store_id]["items_sold"] += int(order.get("items_count", 0))
        
        return {
            "total_revenue": total_revenue,
            "order_count": order_count,
            "average_order_value": total_revenue / order_count if order_count > 0 else 0.0,
            "items_sold": items_sold,
            "by_channel": by_channel,
            "by_store": by_store
        }
