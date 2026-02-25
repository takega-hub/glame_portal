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

logger = logging.getLogger(__name__)


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
        
        params = {"$top": 1000}  # Ограничение на количество записей
        if filters:
            params["$filter"] = " and ".join(filters)
        
        params["$orderby"] = "Period desc"
        
        try:
            logger.info(f"Запрос к 1С OData API: {url}")
            logger.debug(f"Параметры: {params}")
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # OData возвращает данные в формате {"value": [...]}
            if 'value' in data:
                records = data['value']
                logger.info(f"Получено записей из 1С: {len(records)}")
                
                # Преобразуем OData формат в наш формат
                orders = []
                for record in records:
                    # Фильтруем по дате на стороне приложения
                    period = record.get('Period')
                    if period:
                        try:
                            if isinstance(period, str):
                                # Убираем микросекунды и timezone если есть
                                period_clean = period.split('.')[0].replace('Z', '')
                                record_date = datetime.fromisoformat(period_clean)
                            else:
                                record_date = period
                            
                            # Применяем фильтр по дате
                            if start_date and record_date < start_date:
                                continue
                            if end_date and record_date > end_date:
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
                
                logger.info(f"После фильтрации осталось заказов: {len(orders)}")
                return {"orders": orders}
            else:
                # Если формат не OData, возвращаем как есть
                return data
                
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP ошибка при запросе к 1С API: {e.response.status_code}")
            logger.error(f"Ответ: {e.response.text[:500]}")
            raise
        except Exception as e:
            logger.error(f"Ошибка при запросе к 1С API: {e}")
            raise
    
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
