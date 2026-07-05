"""
Сервис для работы с покупателями из 1С УНФ ФРЕШ
Синхронизация дисконтных карт и история покупок
"""
import httpx
import json
import base64
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone
import os
import asyncio

logger = logging.getLogger(__name__)


class OneCCustomersService:
    """Сервис для работы с покупателями из 1С"""

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_token: Optional[str] = None,
        discount_cards_endpoint: Optional[str] = None,
        customers_endpoint: Optional[str] = None
    ):
        self.api_url = api_url or os.getenv("ONEC_API_URL")
        self.api_token = api_token or os.getenv("ONEC_API_TOKEN")
        self.discount_cards_endpoint = discount_cards_endpoint or os.getenv(
            "ONEC_DISCOUNT_CARDS_ENDPOINT",
            "/Catalog_ДисконтныеКарты"
        )
        self.customers_endpoint = customers_endpoint or os.getenv(
            "ONEC_CUSTOMERS_ENDPOINT",
            "/Catalog_Контрагенты"
        )

        self.client = None
        if self.api_url:
            headers = {
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            if self.api_token:
                # Поддержка Basic Auth
                if self.api_token.startswith("Basic "):
                    headers["Authorization"] = self.api_token
                else:
                    headers["Authorization"] = f"Basic {self.api_token}"

            # Настройка таймаутов: отдельно для подключения и чтения
            connect_timeout = float(os.getenv("ONEC_CONNECT_TIMEOUT", "60.0"))
            read_timeout = float(os.getenv("ONEC_READ_TIMEOUT", "300.0"))

            timeout_config = httpx.Timeout(
                connect=connect_timeout,
                read=read_timeout,
                write=30.0,
                pool=60.0
            )

            self.client = httpx.AsyncClient(
                timeout=timeout_config,
                headers=headers,
                verify=True,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
            )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def close(self):
        if self.client:
            await self.client.aclose()

    async def fetch_discount_cards(
        self,
        limit: int = 1000,
        offset: int = 0,
        max_retries: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Получение списка дисконтных карт с повторными попытками

        Returns:
            Список дисконтных карт с полями:
            - КодКартыШтрихкод: номер телефона = логин
            - Ref_Key: ID карты
            - ВладелецКарты_Key: ID покупателя
            - Code: внутренний код карты
        """
        if not self.client:
            raise ValueError("API URL не настроен")

        url = f"{self.api_url.rstrip('/')}{self.discount_cards_endpoint}"
        params = {
            "$top": limit,
            "$skip": offset,
            "$orderby": "Code"
        }

        last_exception = None
        for attempt in range(max_retries):
            try:
                logger.info(f"Запрос дисконтных карт (попытка {attempt + 1}/{max_retries}): {url}")
                response = await self.client.get(url, params=params)
                response.raise_for_status()

                data = response.json()
                if 'value' in data:
                    logger.info(f"Успешно получено {len(data['value'])} дисконтных карт")
                    return data['value']
                return []
            except httpx.ConnectTimeout as e:
                last_exception = e
                wait_time = 2 ** attempt  # Экспоненциальная задержка: 1s, 2s, 4s
                logger.warning(f"Таймаут подключения (попытка {attempt + 1}/{max_retries}). Повтор через {wait_time}с...")
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Не удалось подключиться к 1С после {max_retries} попыток")
            except httpx.ReadTimeout as e:
                last_exception = e
                wait_time = 2 ** attempt
                logger.warning(f"Таймаут чтения данных (попытка {attempt + 1}/{max_retries}). Повтор через {wait_time}с...")
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Таймаут чтения данных после {max_retries} попыток")
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP ошибка {e.response.status_code}: {e.response.text}")
                raise
            except httpx.RequestError as e:
                last_exception = e
                wait_time = 2 ** attempt
                logger.warning(f"Ошибка запроса (попытка {attempt + 1}/{max_retries}): {e}. Повтор через {wait_time}с...")
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Ошибка запроса после {max_retries} попыток")
            except Exception as e:
                logger.error(f"Неожиданная ошибка при получении дисконтных карт: {e}")
                raise

        # Если все попытки исчерпаны, выбрасываем последнее исключение
        if last_exception:
            raise last_exception
        raise Exception("Не удалось получить дисконтные карты")

    async def find_discount_card_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        if not self.client:
            raise ValueError("API URL не настроен")
        safe_phone = str(phone or "").replace("'", "''")
        if not safe_phone:
            return None
        url = f"{self.api_url.rstrip('/')}{self.discount_cards_endpoint}"
        params = {"$filter": f"КодКартыШтрихкод eq '{safe_phone}' and DeletionMark eq false", "$top": 1}
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            values = data.get("value") or []
            return values[0] if values else None
        except httpx.HTTPStatusError as error:
            body = error.response.text or ""
            if "КодКартыШтрихкод" not in body and "Операция не разрешена" not in body:
                raise
            logger.warning("1С не поддерживает быстрый поиск карты по штрихкоду, использую scan fallback")
            offset = 0
            page_size = 1000
            while True:
                cards = await self.fetch_discount_cards(limit=page_size, offset=offset)
                for item in cards:
                    if str(item.get("КодКартыШтрихкод") or "") == safe_phone and not bool(item.get("DeletionMark")):
                        return item
                if len(cards) < page_size:
                    return None
                offset += page_size

    async def fetch_customers(
        self,
        limit: int = 1000,
        offset: int = 0,
        max_retries: int = 3,
    ) -> List[Dict[str, Any]]:
        """Получение списка контрагентов с пагинацией."""
        if not self.client:
            raise ValueError("API URL не настроен")

        url = f"{self.api_url.rstrip('/')}{self.customers_endpoint}"
        params = {
            "$top": limit,
            "$skip": offset,
            "$orderby": "Code",
        }

        last_exception = None
        for attempt in range(max_retries):
            try:
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                return data.get("value") or []
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RequestError) as e:
                last_exception = e
                wait_time = 2 ** attempt
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("Не удалось получить контрагентов из 1С после %s попыток", max_retries)
            except httpx.HTTPStatusError:
                raise
            except Exception:
                raise

        if last_exception:
            raise last_exception
        raise Exception("Не удалось получить контрагентов")

    async def fetch_customers_by_referral_code(
        self,
        referral_code: str,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """Быстрый поиск контрагентов по рефкоду в email-поле 1С."""
        if not self.client:
            raise ValueError("API URL не настроен")
        code = str(referral_code or "").strip().upper().replace("'", "''")
        if not code:
            return []
        url = f"{self.api_url.rstrip('/')}{self.customers_endpoint}"
        email_fields = [
            field.strip()
            for field in os.getenv("ONEC_CUSTOMER_EMAIL_FIELDS", "АдресЭПДляПоиска").split(",")
            if field.strip()
        ]
        for field_name in email_fields:
            params = {
                "$filter": f"substringof('{code}',{field_name}) eq true and DeletionMark eq false",
                "$top": limit,
            }
            try:
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                return data.get("value") or []
            except httpx.HTTPStatusError as e:
                body = e.response.text or ""
                if "substringof" in body or "Сегмент пути" in body or "not found" in body.lower():
                    continue
                raise
        return []

    async def fetch_customer_details(
        self,
        customer_key: str,
        max_retries: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """
        Получение данных контрагента по Ref_Key.
        """
        if not self.client:
            raise ValueError("API URL не настроен")

        url = f"{self.api_url.rstrip('/')}{self.customers_endpoint}"
        params = {
            "$filter": f"Ref_Key eq guid'{customer_key}'",
            "$top": 1,
        }

        last_exception = None
        for attempt in range(max_retries):
            try:
                logger.info(
                    "Запрос данных контрагента %s (попытка %s/%s)",
                    customer_key,
                    attempt + 1,
                    max_retries,
                )
                response = await self.client.get(url, params=params)
                response.raise_for_status()

                data = response.json()
                if "value" in data and data["value"]:
                    return data["value"][0]
                return None
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RequestError) as e:
                last_exception = e
                wait_time = 2 ** attempt
                logger.warning(
                    "Ошибка при получении контрагента (попытка %s/%s): %s. Повтор через %sс...",
                    attempt + 1,
                    max_retries,
                    e,
                    wait_time,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("Не удалось получить контрагента после %s попыток", max_retries)
            except httpx.HTTPStatusError as e:
                logger.error("HTTP ошибка %s: %s", e.response.status_code, e.response.text)
                raise
            except Exception as e:
                logger.error("Неожиданная ошибка при получении контрагента: %s", e)
                raise

        if last_exception:
            raise last_exception
        return None

    async def get_customer_by_phone(
        self,
        phone: str,
        max_retries: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Получение информации о покупателе по номеру телефона с повторными попытками

        Args:
            phone: Номер телефона (логин)
            max_retries: Максимальное количество попыток

        Returns:
            Информация о дисконтной карте и покупателе
        """
        if not self.client:
            raise ValueError("API URL не настроен")

        url = f"{self.api_url.rstrip('/')}{self.discount_cards_endpoint}"
        params = {
            "$filter": f"КодКартыШтрихкод eq '{phone}'",
            "$top": 1
        }

        last_exception = None
        for attempt in range(max_retries):
            try:
                response = await self.client.get(url, params=params)
                response.raise_for_status()

                data = response.json()
                if 'value' in data and len(data['value']) > 0:
                    return data['value'][0]
                return None
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RequestError) as e:
                last_exception = e
                wait_time = 2 ** attempt
                logger.warning(f"Ошибка при поиске покупателя по телефону {phone} (попытка {attempt + 1}/{max_retries}): {e}. Повтор через {wait_time}с...")
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Не удалось найти покупателя по телефону {phone} после {max_retries} попыток")
            except Exception as e:
                logger.error(f"Ошибка при поиске покупателя по телефону {phone}: {e}")
                raise

        if last_exception:
            raise last_exception
        return None

    async def get_customer_purchases(
        self,
        customer_key: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000,
        max_retries: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Получение истории покупок покупателя с повторными попытками

        ВАЖНО: Используем AccumulationRegister_Продажи без фильтрации через OData,
        так как 1С Fresh возвращает ошибку 500 при фильтрации по Контрагент_Key.
        Данные фильтруются на стороне приложения после парсинга RecordSet.

        Args:
            customer_key: ID покупателя (Контрагент_Key)
            start_date: Начальная дата
            end_date: Конечная дата
            limit: Максимальное количество записей
            max_retries: Максимальное количество попыток

        Returns:
            Список покупок с полями:
            - Period: дата покупки
            - Сумма: сумма покупки
            - Количество: количество товара
            - Номенклатура_Key: ID товара
            - Документ: ID документа продажи
        """
        if not self.client:
            raise ValueError("API URL не настроен")

        # Быстрый путь: RecordType позволяет фильтровать по Контрагент_Key и периоду.
        # Это критично для ручной синхронизации партнера: не листаем весь регистр 1С.
        sales_endpoint = os.getenv("ONEC_SALES_ENDPOINT", "/AccumulationRegister_Продажи_RecordType")
        recordtype_url = f"{self.api_url.rstrip('/')}{sales_endpoint}"
        filters = [f"Контрагент_Key eq guid'{customer_key}'"]
        if start_date:
            filters.append(f"Period ge datetime'{start_date.strftime('%Y-%m-%dT%H:%M:%S')}'")
        if end_date:
            filters.append(f"Period le datetime'{end_date.strftime('%Y-%m-%dT%H:%M:%S')}'")
        try:
            response = await self.client.get(
                recordtype_url,
                params={
                    "$filter": " and ".join(filters),
                    "$top": limit,
                },
            )
            response.raise_for_status()
            records = (response.json() or {}).get("value") or []
            fast_purchases = [
                {
                    "Period": record.get("Period"),
                    "Сумма": record.get("Сумма", 0),
                    "Количество": record.get("Количество", 0),
                    "Номенклатура_Key": record.get("Номенклатура_Key"),
                    "Номенклатура_Description": record.get("Номенклатура_Description"),
                    "Характеристика_Key": record.get("Характеристика_Key"),
                    "Документ": record.get("Документ") or record.get("Recorder"),
                    "Документ_Type": record.get("Документ_Type") or record.get("Recorder_Type"),
                    "Recorder": record.get("Recorder"),
                    "Recorder_Type": record.get("Recorder_Type"),
                    "LineNumber": record.get("LineNumber"),
                    "Склад_Key": record.get("Склад_Key"),
                    "Контрагент_Key": record.get("Контрагент_Key"),
                    "raw_1c_data": record,
                }
                for record in records
            ]
            return sorted(
                fast_purchases,
                key=lambda item: item.get("Period") or "",
                reverse=True,
            )[:limit]
        except httpx.HTTPStatusError as error:
            logger.warning(
                "1С не приняла быстрый фильтр продаж по контрагенту %s: %s",
                customer_key,
                error.response.text[:500],
            )
        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RequestError) as error:
            logger.warning(
                "Не удалось быстро получить продажи по контрагенту %s: %s",
                customer_key,
                error,
            )

        # Fallback: старый путь через документ-регистратор без OData-фильтрации.
        sales_endpoint = "/AccumulationRegister_Продажи"
        url = f"{self.api_url.rstrip('/')}{sales_endpoint}"

        last_exception = None
        for attempt in range(max_retries):
            # ВАЖНО: 1С Fresh возвращает ошибку 500 при большом $top с AUTOORDER
            # Используем меньший лимит и пагинацию
            batch_size = 100
            all_purchases = []
            skip = 0

            while True:
                params = {
                    # "$filter": " and ".join(filters),  # НЕ ИСПОЛЬЗУЕМ - вызывает ошибку 500
                    # "$orderby": "Period desc",  # УДАЛЕНО - вызывает ошибку 500 в 1С Fresh
                    "$top": batch_size,
                    "$skip": skip,
                }

                try:
                    logger.info(f"Запрос истории покупок для покупателя {customer_key} (попытка {attempt + 1}/{max_retries}, skip={skip})")
                    response = await self.client.get(url, params=params)
                    response.raise_for_status()

                    data = response.json()
                    if 'value' in data:
                        records = data['value']

                        if not records:
                            break

                        # Парсим RecordSet для извлечения покупок
                        for record in records:
                            record_set = record.get("RecordSet", [])
                            if not isinstance(record_set, list):
                                continue

                            for movement in record_set:
                                # Проверяем контрагента
                                kontragent_key = movement.get("Контрагент_Key", "")

                                # Фильтруем строго по контрагенту. Анонимные движения с нулевым
                                # Контрагент_Key дают чужие позиции в истории покупателя.
                                if kontragent_key == customer_key:
                                    period = movement.get("Period", "")
                                    if period:
                                        try:
                                            if isinstance(period, str):
                                                dt = datetime.fromisoformat(period.replace("Z", "+00:00").split(".")[0])
                                                date_str = dt.strftime("%Y-%m-%d")

                                                # Фильтруем по дате
                                                if start_date and date_str < start_date.strftime("%Y-%m-%d"):
                                                    continue
                                                if end_date and date_str > end_date.strftime("%Y-%m-%d"):
                                                    continue

                                            # Формируем запись покупки
                                            all_purchases.append({
                                                "Period": period,
                                                "Сумма": movement.get("Сумма", 0),
                                                "Количество": movement.get("Количество", 0),
                                                "Номенклатура_Key": movement.get("Номенклатура_Key"),
                                                "Номенклатура_Description": movement.get("Номенклатура_Description"),
                                                "Характеристика_Key": movement.get("Характеристика_Key"),
                                                "Документ": movement.get("Документ"),
                                                "Документ_Type": movement.get("Документ_Type"),
                                                "Склад_Key": movement.get("Склад_Key"),
                                                "Контрагент_Key": kontragent_key,
                                                "raw_1c_data": movement,
                                            })
                                        except Exception as e:
                                            pass

                        skip += batch_size

                        # Ограничиваем общее количество
                        if len(all_purchases) >= limit * 2:
                            all_purchases = all_purchases[:limit * 2]
                            break

                        # Если получили меньше чем запросили, значит это последний батч
                        if len(records) < batch_size:
                            break

                    else:
                        break

                except httpx.HTTPStatusError as e:
                    # Проверяем, это ли ошибка AUTOORDER
                    if e.response.status_code == 500 and "AUTOORDER" in e.response.text:
                        logger.warning(
                            "Ошибка AUTOORDER в 1С Fresh при skip=%s, пробуем с меньшим batch_size",
                            skip
                        )
                        # Уменьшаем batch_size и пробуем снова
                        batch_size = max(50, batch_size // 2)
                        skip = 0
                        all_purchases = []

                        # Если batch_size достиг минимума, прерываем цикл
                        if batch_size <= 50:
                            logger.warning(
                                "batch_size достиг минимума 50, прерываем запрос"
                            )
                            break
                        continue
                    else:
                        logger.error(f"HTTP ошибка {e.response.status_code}: {e.response.text}")
                        raise
                except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RequestError) as e:
                    last_exception = e
                    wait_time = 2 ** attempt
                    logger.warning(f"Ошибка при получении истории покупок (попытка {attempt + 1}/{max_retries}): {e}. Повтор через {wait_time}с...")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
                        break
                    else:
                        logger.error(f"Не удалось получить историю покупок после {max_retries} попыток")
                        break
                except Exception as e:
                    logger.error(f"Неожиданная ошибка при получении истории покупок: {e}")
                    raise

            if all_purchases:
                break

        if not all_purchases and last_exception:
            raise last_exception

        if not all_purchases:
            return []

        # Сортируем по Period desc на стороне приложения (так как $orderby вызывает ошибку 500 в 1С Fresh)
        def parse_period(p):
            if not p:
                return datetime.min.replace(tzinfo=timezone.utc)
            try:
                if isinstance(p, str):
                    return datetime.fromisoformat(p.replace('Z', '+00:00').split('.')[0])
                return p
            except Exception:
                return datetime.min.replace(tzinfo=timezone.utc)

        all_purchases = sorted(all_purchases, key=lambda r: parse_period(r.get('Period')), reverse=True)

        # Ограничиваем результат
        return all_purchases[:limit]

    async def fetch_sales_by_discount_card(
        self,
        discount_card_key: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000,
        max_retries: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Получение продаж по дисконтной карте (точная привязка).

        ВАЖНО: Используем AccumulationRegister_Продажи без фильтрации через OData,
        так как 1С Fresh возвращает ошибку 500 при фильтрации.
        Данные фильтруются на стороне приложения после парсинга RecordSet.
        """
        if not self.client:
            raise ValueError("API URL не настроен")

        # Используем тот же регистр, что и get_customer_purchases
        sales_endpoint = os.getenv("ONEC_SALES_ENDPOINT", "/AccumulationRegister_Продажи")
        url = f"{self.api_url.rstrip('/')}{sales_endpoint}"

        last_exception = None
        for attempt in range(max_retries):
            batch_size = 100
            all_purchases = []
            skip = 0

            while True:
                params = {
                    "$top": batch_size,
                    "$skip": skip,
                }
                try:
                    logger.info(
                        "Запрос продаж по дисконтной карте %s (попытка %s/%s, skip=%s)",
                        discount_card_key,
                        attempt + 1,
                        max_retries,
                        skip,
                    )
                    response = await self.client.get(url, params=params)
                    response.raise_for_status()

                    data = response.json()
                    records = data.get("value", [])

                    if not records:
                        break

                    # Парсим RecordSet для извлечения покупок
                    for record in records:
                        record_set = record.get("RecordSet", [])
                        if not isinstance(record_set, list):
                            continue

                        for movement in record_set:
                            # Проверяем дисконтную карту
                            discount_card = movement.get("ДисконтнаяКарта_Key", "")

                            # Если карта совпадает
                            if discount_card == discount_card_key:
                                period = movement.get("Period", "")
                                if period:
                                    try:
                                        if isinstance(period, str):
                                            dt = datetime.fromisoformat(period.replace("Z", "+00:00").split(".")[0])
                                            date_str = dt.strftime("%Y-%m-%d")

                                            # Фильтруем по дате
                                            if start_date and date_str < start_date.strftime("%Y-%m-%d"):
                                                continue
                                            if end_date and date_str > end_date.strftime("%Y-%m-%d"):
                                                continue

                                            # Формируем запись покупки
                                            all_purchases.append({
                                                "Period": period,
                                                "Сумма": movement.get("Сумма", 0),
                                                "Количество": movement.get("Количество", 0),
                                                "Номенклатура_Key": movement.get("Номенклатура_Key"),
                                                "Номенклатура_Description": movement.get("Номенклатура_Description"),
                                                "Характеристика_Key": movement.get("Характеристика_Key"),
                                                "Документ": movement.get("Документ"),
                                                "Документ_Type": movement.get("Документ_Type"),
                                                "Склад_Key": movement.get("Склад_Key"),
                                                "ДисконтнаяКарта_Key": discount_card,
                                                "raw_1c_data": movement,
                                            })
                                    except Exception as e:
                                        pass

                    skip += batch_size

                    # Ограничиваем общее количество
                    if len(all_purchases) >= limit * 2:
                        all_purchases = all_purchases[:limit * 2]
                        break

                    # Если получили меньше чем запросили, значит это последний батч
                    if len(records) < batch_size:
                        break

                except httpx.HTTPStatusError as e:
                    # Проверяем, это ли ошибка AUTOORDER
                    if e.response.status_code == 500 and "AUTOORDER" in e.response.text:
                        logger.warning(
                            "Ошибка AUTOORDER в 1С Fresh при skip=%s, пробуем с меньшим batch_size",
                            skip
                        )
                        # Уменьшаем batch_size и пробуем снова
                        batch_size = max(50, batch_size // 2)
                        skip = 0
                        all_purchases = []

                        # Если batch_size достиг минимума, прерываем цикл
                        if batch_size <= 50:
                            logger.warning(
                                "batch_size достиг минимума 50, прерываем запрос продаж по карте"
                            )
                            break
                        continue
                    else:
                        logger.error(f"HTTP ошибка {e.response.status_code}: {e.response.text}")
                        raise
                except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RequestError) as e:
                    last_exception = e
                    wait_time = 2 ** attempt
                    logger.warning(
                        "Ошибка при получении продаж по карте (попытка %s/%s): %s. Повтор через %sс...",
                        attempt + 1,
                        max_retries,
                        e,
                        wait_time,
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
                        break
                    else:
                        logger.error("Не удалось получить продажи по карте после %s попыток", max_retries)
                        break
                except Exception as e:
                    logger.error("Неожиданная ошибка при получении продаж по карте: %s", e)
                    raise

            if all_purchases:
                break

        if not all_purchases and last_exception:
            raise last_exception

        if not all_purchases:
            return []

        # Сортируем по Period desc на стороне приложения
        def parse_period(p):
            if not p:
                return datetime.min.replace(tzinfo=timezone.utc)
            try:
                if isinstance(p, str):
                    return datetime.fromisoformat(p.replace('Z', '+00:00').split('.')[0])
                return p
            except Exception:
                return datetime.min.replace(tzinfo=timezone.utc)

        all_purchases = sorted(all_purchases, key=lambda r: parse_period(r.get('Period')), reverse=True)

        # Ограничиваем результат
        return all_purchases[:limit]

    async def fetch_product_details(
        self,
        product_key_1c: str,
        max_retries: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Получение данных товара из 1С по Номенклатура_Key.
        Возвращает артикул (Code), название и другие данные товара.
        """
        if not self.client:
            raise ValueError("API URL не настроен")

        products_endpoint = os.getenv(
            "ONEC_PRODUCTS_ENDPOINT",
            "/Catalog_Номенклатура"
        )
        url = f"{self.api_url.rstrip('/')}{products_endpoint}"

        params = {
            "$filter": f"Ref_Key eq guid'{product_key_1c}'",
            "$top": 1
        }

        last_exception = None
        for attempt in range(max_retries):
            try:
                logger.debug(f"Запрос данных товара {product_key_1c} (попытка {attempt + 1}/{max_retries})")
                response = await self.client.get(url, params=params)
                response.raise_for_status()

                data = response.json()
                if 'value' in data and len(data['value']) > 0:
                    product_data = data['value'][0]

                    # Название товара из разных возможных полей
                    name = (
                        product_data.get("Description") or
                        product_data.get("Наименование") or
                        product_data.get("НаименованиеПолное") or
                        product_data.get("Name")
                    )

                    # Артикул из разных возможных полей
                    article = (
                        product_data.get("Артикул") or
                        product_data.get("Code") or
                        product_data.get("Код") or
                        product_data.get("СКУ") or
                        product_data.get("SKU")
                    )

                    # Категория/Вид номенклатуры
                    category = (
                        product_data.get("Категория") or
                        product_data.get("ВидНоменклатуры") or
                        product_data.get("ГруппаНоменклатуры") or
                        product_data.get("Category")
                    )

                    # Бренд/Производитель - пробуем разные поля
                    brand = (
                        product_data.get("Бренд") or
                        product_data.get("Производитель") or
                        product_data.get("Brand") or
                        product_data.get("Марка") or
                        product_data.get("ТорговаяМарка")
                    )

                    # Если бренд не найден, пробуем извлечь из названия (например "Серьги Kalliope" -> "Kalliope")
                    if not brand and name:
                        # Известные бренды GLAME
                        known_brands = ["Kalliope", "Bicolor", "UNOde50", "GLAME", "Swarovski"]
                        name_parts = name.split()
                        for part in name_parts:
                            for kb in known_brands:
                                if kb.lower() in part.lower():
                                    brand = kb
                                    break
                            if brand:
                                break

                    return {
                        "key": product_data.get("Ref_Key"),
                        "code": product_data.get("Code"),  # Артикул/код товара
                        "name": name,  # Название
                        "article": article,  # Артикул
                        "barcode": (
                            product_data.get("Штрихкод")
                            or product_data.get("Barcode")
                            or product_data.get("BarCode")
                            or product_data.get("КодКартыШтрихкод")
                        ),
                        "category": category,
                        "brand": brand,
                        "raw_data": product_data  # Все данные для дальнейшего использования
                    }
                return None
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RequestError) as e:
                last_exception = e
                wait_time = 2 ** attempt
                logger.warning(f"Ошибка при получении данных товара {product_key_1c} (попытка {attempt + 1}/{max_retries}): {e}. Повтор через {wait_time}с...")
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Не удалось получить данные товара {product_key_1c} после {max_retries} попыток")
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP ошибка при получении товара {product_key_1c}: {e.response.status_code}: {e.response.text}")
                # Не пробрасываем ошибку, просто возвращаем None
                return None
            except Exception as e:
                logger.error(f"Неожиданная ошибка при получении товара {product_key_1c}: {e}")
                return None

        if last_exception:
            logger.error(f"Не удалось получить данные товара {product_key_1c}: {last_exception}")
        return None

    async def fetch_loyalty_balance(
        self,
        customer_key: Optional[str],
        discount_card_key: Optional[str],
        max_retries: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Получение баланса бонусов из AccumulationRegister_БонусныеБаллы.
        Возвращает {"balance": int, "source_id": str|None}.
        """
        if not self.client:
            raise ValueError("API URL не настроен")

        # Пробуем сначала виртуальную таблицу остатков
        loyalty_balances_endpoint = os.getenv(
            "ONEC_LOYALTY_BALANCES_ENDPOINT",
            "/AccumulationRegister_БонусныеБаллы_Остатки"
        )

        loyalty_endpoint = os.getenv(
            "ONEC_LOYALTY_ENDPOINT",
            "/AccumulationRegister_БонусныеБаллы_RecordType"
        )

        filter_fields = self._loyalty_filter_fields()
        filter_values = {
            "card": discount_card_key,
            "customer": customer_key,
        }

        # Сначала пробуем виртуальную таблицу остатков
        last_exception = None
        for attempt in range(max_retries):
            for field_name in filter_fields:
                # Определяем, какое значение использовать для фильтра
                if "БонуснаяКарта" in field_name or "ДисконтнаяКарта" in field_name or "Карта" in field_name:
                    if not filter_values["card"]:
                        continue
                    filter_value = filter_values["card"]
                elif "ВладелецКарты" in field_name:
                    if filter_values["card"]:
                        filter_value = filter_values["card"]
                    elif filter_values["customer"]:
                        filter_value = filter_values["customer"]
                    else:
                        continue
                elif "Контрагент" in field_name or "Покупатель" in field_name:
                    if not filter_values["customer"]:
                        continue
                    filter_value = filter_values["customer"]
                else:
                    continue

                if not filter_value:
                    continue

                # Пробуем виртуальную таблицу остатков
                balances_url = f"{self.api_url.rstrip('/')}{loyalty_balances_endpoint}"
                params = {
                    "$filter": f"{field_name} eq guid'{filter_value}'",
                    "$top": 1,
                }
                try:
                    logger.info(
                        "Попытка получить остаток из виртуальной таблицы (поле %s)",
                        field_name,
                    )
                    response = await self.client.get(balances_url, params=params)
                    response.raise_for_status()

                    data = response.json()
                    records = data.get("value", [])
                    if records:
                        record = records[0]
                        # В виртуальной таблице остатков должно быть поле "Остаток" или "КоличествоОстаток"
                        остаток = record.get("Остаток") or record.get("КоличествоОстаток") or record.get("Начислено")
                        if остаток is not None:
                            try:
                                balance = int(float(остаток))
                                source_id = record.get("БонуснаяКарта_Key") or filter_value
                                logger.info("Получен остаток из виртуальной таблицы: %s", balance)
                                return {"balance": balance, "source_id": source_id}
                            except (TypeError, ValueError):
                                pass
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        logger.debug("Виртуальная таблица остатков не найдена, используем RecordType")
                    elif e.response.status_code == 400 and "Сегмент пути" in e.response.text:
                        logger.debug("Поле %s не найдено в виртуальной таблице остатков", field_name)
                    else:
                        logger.debug("Ошибка при запросе виртуальной таблицы остатков: %s", e.response.status_code)
                except Exception as e:
                    logger.debug("Ошибка при запросе виртуальной таблицы остатков: %s", e)

                # Если виртуальная таблица не сработала, используем RecordType
                url = f"{self.api_url.rstrip('/')}{loyalty_endpoint}"
                params = {
                    "$filter": f"{field_name} eq guid'{filter_value}'",
                    "$top": 10000,  # Увеличиваем лимит для получения всех записей
                    "$orderby": "Period desc",  # Сортируем по дате
                }
                try:
                    logger.info(
                        "Запрос баланса бонусов (поле %s, попытка %s/%s)",
                        field_name,
                        attempt + 1,
                        max_retries,
                    )
                    response = await self.client.get(url, params=params)
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 500 and "AUTOORDER" in e.response.text:
                            logger.warning(
                                "1C не приняла $orderby для бонусов, повторяем запрос без сортировки."
                            )
                            params.pop("$orderby", None)
                            response = await self.client.get(url, params=params)
                            try:
                                response.raise_for_status()
                            except httpx.HTTPStatusError as no_order_error:
                                if no_order_error.response.status_code == 500 and "Операция не разрешена" in no_order_error.response.text:
                                    return await self._fetch_loyalty_balance_by_scan(
                                        customer_key=customer_key,
                                        discount_card_key=discount_card_key,
                                        endpoint=loyalty_endpoint,
                                    )
                                raise
                        elif e.response.status_code == 500 and "Операция не разрешена" in e.response.text:
                            return await self._fetch_loyalty_balance_by_scan(
                                customer_key=customer_key,
                                discount_card_key=discount_card_key,
                                endpoint=loyalty_endpoint,
                            )
                        else:
                            raise

                    data = response.json()
                    records = data.get("value", [])
                    if not records:
                        return {"balance": 0, "source_id": None}
                    records = self._filter_records_by_date(records, None, None)
                    calculated = self._current_loyalty_balance_from_records(records)

                    logger.info(
                        "Остаток бонусов рассчитан по движениям регистра: %s (записей=%s)",
                        calculated["balance"], len(records)
                    )

                    return calculated
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 400 and "Сегмент пути" in e.response.text:
                        logger.warning(
                            "Поле %s не найдено в регистре бонусов, пробуем следующее поле.",
                            field_name,
                        )
                        continue
                    logger.error("HTTP ошибка %s: %s", e.response.status_code, e.response.text)
                    raise
                except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RequestError) as e:
                    last_exception = e
                    wait_time = 2 ** attempt
                    logger.warning(
                        "Ошибка при получении баланса бонусов (попытка %s/%s): %s. Повтор через %sс...",
                        attempt + 1,
                        max_retries,
                        e,
                        wait_time,
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error("Не удалось получить баланс бонусов после %s попыток", max_retries)
                except Exception as e:
                    logger.error("Неожиданная ошибка при получении баланса бонусов: %s", e)
                    raise

        if last_exception:
            raise last_exception
        return None

    def build_customer_profile(
        self,
        discount_card: Dict[str, Any],
        purchases: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Построение профиля покупателя на основе данных из 1С

        Args:
            discount_card: Данные дисконтной карты
            purchases: История покупок

        Returns:
            Профиль покупателя с аналитикой
        """
        phone = discount_card.get('КодКартыШтрихкод', '')
        customer_key = discount_card.get('ВладелецКарты_Key')

        if not purchases:
            return {
                "phone": phone,
                "customer_id": customer_key,
                "discount_card_id": discount_card.get('Ref_Key'),
                "total_revenue": 0.0,
                "purchase_count": 0,
                "average_check": 0.0,
                "total_items": 0,
                "last_purchase": None,
                "first_purchase": None
            }

        # Рассчитываем метрики
        total_revenue = sum(float(p.get('Сумма', 0) or 0) for p in purchases)
        total_items = sum(float(p.get('Количество', 0) or 0) for p in purchases)
        purchase_count = len(purchases)

        # Даты покупок
        dates = []
        for p in purchases:
            period = p.get('Period')
            if period:
                try:
                    if isinstance(period, str):
                        dates.append(datetime.fromisoformat(period.replace('Z', '+00:00')))
                    else:
                        dates.append(period)
                except:
                    pass

        # Анализ категорий товаров (если доступно)
        product_ids = [p.get('Номенклатура_Key') for p in purchases if p.get('Номенклатура_Key')]

        return {
            "phone": phone,
            "customer_id": customer_key,
            "discount_card_id": discount_card.get('Ref_Key'),
            "total_revenue": total_revenue,
            "purchase_count": purchase_count,
            "average_check": total_revenue / purchase_count if purchase_count > 0 else 0.0,
            "total_items": total_items,
            "last_purchase": max(dates).isoformat() if dates else None,
            "first_purchase": min(dates).isoformat() if dates else None,
            "purchase_frequency_days": self._calculate_frequency(dates),
            "favorite_products": list(set(product_ids))[:10],  # Топ-10 товаров
            "metadata": {
                "card_code": discount_card.get('Code'),
                "card_description": discount_card.get('Description')
            }
        }

    def _calculate_frequency(self, dates: List[datetime]) -> Optional[float]:
        """Расчет средней частоты покупок в днях"""
        if len(dates) < 2:
            return None

        sorted_dates = sorted(dates)
        intervals = []
        for i in range(1, len(sorted_dates)):
            delta = (sorted_dates[i] - sorted_dates[i-1]).days
            if delta > 0:
                intervals.append(delta)

        if intervals:
            return sum(intervals) / len(intervals)
        return None

    @staticmethod
    def _filter_records_by_date(
        records: List[Dict[str, Any]],
        start_date: Optional[datetime],
        end_date: Optional[datetime],
    ) -> List[Dict[str, Any]]:
        # Сортируем по Period desc на стороне приложения (так как $orderby вызывает ошибку 500 в 1С Fresh)
        def parse_period(p):
            if not p:
                return datetime.min.replace(tzinfo=timezone.utc)
            try:
                if isinstance(p, str):
                    return datetime.fromisoformat(p.replace("Z", "+00:00").split(".")[0])
                return p
            except Exception:
                return datetime.min.replace(tzinfo=timezone.utc)

        records = sorted(records, key=lambda r: parse_period(r.get("Period")), reverse=True)

        if not start_date and not end_date:
            return records

        def _normalize(dt_value: datetime) -> datetime:
            """Нормализует datetime к UTC aware"""
            if dt_value is None:
                return None
            if dt_value.tzinfo is None:
                return dt_value.replace(tzinfo=timezone.utc)
            return dt_value.astimezone(timezone.utc)

        normalized_start = _normalize(start_date) if start_date else None
        normalized_end = _normalize(end_date) if end_date else None

        filtered_records = []
        for record in records:
            period = record.get("Period")
            if not period:
                filtered_records.append(record)
                continue
            try:
                if isinstance(period, str):
                    # Убираем миллисекунды и добавляем timezone если нет
                    period_clean = period.replace("Z", "+00:00")
                    # Обрабатываем формат без timezone (2025-12-11T17:31:59)
                    if "+" not in period_clean and "-" not in period_clean[10:]:
                        period_clean = period_clean.split(".")[0] + "+00:00"
                    else:
                        period_clean = period_clean.split(".")[0]
                        if "+" not in period_clean and not period_clean.endswith("Z"):
                            period_clean += "+00:00"
                    record_date = datetime.fromisoformat(period_clean)
                else:
                    record_date = period

                # Нормализуем к UTC
                record_date = _normalize(record_date)

                if normalized_start and record_date < normalized_start:
                    continue
                if normalized_end and record_date > normalized_end:
                    continue
                filtered_records.append(record)
            except Exception as e:
                logger.warning("Ошибка парсинга даты %s: %s", period, e)
                # Включаем запись если не можем распарсить дату
                filtered_records.append(record)

        return filtered_records

    @staticmethod
    def _current_loyalty_balance_from_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate current bonus balance from raw AccumulationRegister_БонусныеБаллы records."""
        now = datetime.now(timezone.utc)

        def parse_period(value: Any) -> datetime:
            if not value:
                return datetime.min.replace(tzinfo=timezone.utc)
            try:
                if isinstance(value, str):
                    parsed = datetime.fromisoformat(value.replace("Z", "+00:00").split(".")[0])
                else:
                    parsed = value
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except Exception:
                return datetime.min.replace(tzinfo=timezone.utc)

        def as_float(value: Any) -> float:
            try:
                return float(value or 0)
            except (TypeError, ValueError):
                return 0.0

        current_records = [
            record
            for record in records
            if record.get("Active", True) and parse_period(record.get("Period")) <= now
        ]
        accrued = 0.0
        to_spend = 0.0
        for record in current_records:
            # In UNF Fresh AccumulationRegister_БонусныеБаллы_RecordType both Receipt and
            # Expense rows can carry Начислено/КСписанию movement columns. The report's
            # spendable balance is the current-period total Начислено minus total КСписанию.
            accrued += as_float(record.get("Начислено") or 0)
            to_spend += as_float(record.get("КСписанию") or record.get("К списанию") or 0)

        latest_record = max(current_records, key=lambda item: parse_period(item.get("Period")), default=None)
        source_id = (
            latest_record.get("Recorder")
            or latest_record.get("Документ")
            or latest_record.get("Ref_Key")
        ) if latest_record else None
        balance = accrued - to_spend
        return {
            "balance": max(0, int(round(balance))),
            "source_id": source_id,
            "accrued": accrued,
            "to_spend": to_spend,
            "rows_count": len(current_records),
        }

    async def _fetch_loyalty_balance_by_scan(
        self,
        customer_key: Optional[str],
        discount_card_key: Optional[str],
        endpoint: str,
    ) -> Dict[str, Any]:
        """Fallback для 1C Fresh: читаем регистр бонусов без WHERE/ORDERBY и фильтруем локально."""
        if not self.client:
            raise ValueError("API URL не настроен")

        url = f"{self.api_url.rstrip('/')}{endpoint}"
        batch_size = int(os.getenv("ONEC_LOYALTY_SCAN_BATCH_SIZE", "100"))
        max_records = int(os.getenv("ONEC_LOYALTY_SCAN_MAX_RECORDS", "50000"))
        skip = 0
        matched: List[Dict[str, Any]] = []

        def matches(record: Dict[str, Any]) -> bool:
            if discount_card_key:
                for field in ("БонуснаяКарта_Key", "БонуснаяКарта", "ДисконтнаяКарта_Key", "ДисконтнаяКарта", "Карта_Key", "Карта"):
                    if str(record.get(field) or "") == str(discount_card_key):
                        return True
            if customer_key:
                for field in ("Контрагент_Key", "Покупатель_Key", "ВладелецКарты_Key"):
                    if str(record.get(field) or "") == str(customer_key):
                        return True
            return False

        while skip < max_records:
            response = await self.client.get(url, params={"$top": batch_size, "$skip": skip})
            response.raise_for_status()
            records = response.json().get("value", [])
            if not records:
                break
            matched.extend(record for record in records if matches(record))
            skip += batch_size
            if len(records) < batch_size:
                break

        if not matched:
            return {"balance": 0, "source_id": None}

        matched = self._filter_records_by_date(matched, None, None)
        calculated = self._current_loyalty_balance_from_records(matched)
        logger.info("Остаток бонусов найден fallback-сканированием: %s", calculated["balance"])
        return calculated

    async def fetch_loyalty_lots_balance(
        self,
        customer_key: Optional[str],
        discount_card_key: Optional[str],
    ) -> Dict[str, Any]:
        """Return active bonus accrual lots total from AccumulationRegister_НачисленияБонусныхБаллов."""
        if not self.client:
            raise ValueError("API URL не настроен")

        endpoint = os.getenv(
            "ONEC_LOYALTY_LOTS_ENDPOINT",
            "/AccumulationRegister_НачисленияБонусныхБаллов_RecordType",
        )
        url = f"{self.api_url.rstrip('/')}{endpoint}"
        batch_size = int(os.getenv("ONEC_LOYALTY_LOTS_SCAN_BATCH_SIZE", os.getenv("ONEC_LOYALTY_SCAN_BATCH_SIZE", "100")))
        max_records = int(os.getenv("ONEC_LOYALTY_LOTS_SCAN_MAX_RECORDS", os.getenv("ONEC_LOYALTY_SCAN_MAX_RECORDS", "50000")))
        skip = 0
        matched: List[Dict[str, Any]] = []

        def matches(record: Dict[str, Any]) -> bool:
            if discount_card_key and str(record.get("БонуснаяКарта_Key") or "") == str(discount_card_key):
                return True
            if customer_key and str(record.get("ВладелецКарты_Key") or "") == str(customer_key):
                return True
            return False

        while skip < max_records:
            response = await self.client.get(url, params={"$top": batch_size, "$skip": skip})
            response.raise_for_status()
            records = response.json().get("value", [])
            if not records:
                break
            matched.extend(record for record in records if matches(record))
            skip += batch_size
            if len(records) < batch_size:
                break

        def as_float(value: Any) -> float:
            try:
                return float(value or 0)
            except (TypeError, ValueError):
                return 0.0

        active_records = [record for record in matched if record.get("Active", True)]
        total = sum(as_float(record.get("Сумма")) for record in active_records)
        latest_record = max(active_records, key=lambda item: str(item.get("Period") or ""), default=None)
        return {
            "balance": max(0, int(round(total))),
            "raw_balance": total,
            "rows_count": len(active_records),
            "source_id": latest_record.get("Recorder") if latest_record else None,
        }

    @staticmethod
    def _extract_balance_value(record: Dict[str, Any]) -> Optional[float]:
        # Для AccumulationRegister_БонусныеБаллы_RecordType: Начислено и КСписанию
        if "Начислено" in record or "КСписанию" in record:
            к_списанию = record.get("КСписанию") or record.get("К списанию") or 0
            try:
                return float(к_списанию)
            except (TypeError, ValueError):
                pass

        # Для AccumulationRegister_НачисленияБонусныхБаллов_RecordType: Сумма
        if "Сумма" in record:
            сумма = record.get("Сумма")
            if сумма is not None:
                try:
                    return float(сумма)
                except (TypeError, ValueError):
                    pass

        # Альтернативные поля
        balance_fields = [
            "Баланс",
            "Остаток",
            "ОстатокБаллов",
            "Количество",
            "БонусныеБаллы",
            "Баллы",
            "КоличествоБонусов",
        ]
        for field in balance_fields:
            value = record.get(field)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue

        return None

    @staticmethod
    def _sales_by_card_filter_fields() -> List[str]:
        raw = os.getenv(
            "ONEC_SALES_BY_CARD_FILTER_FIELDS",
            "ДисконтнаяКарта_Key,ДисконтнаяКарта,Карта_Key,Карта",
        )
        fields = [field.strip() for field in raw.split(",") if field.strip()]
        return fields or ["ДисконтнаяКарта_Key"]

    @staticmethod
    def _loyalty_filter_fields() -> List[str]:
        # По умолчанию используем БонуснаяКарта_Key (правильное поле для AccumulationRegister_БонусныеБаллы_RecordType)
        raw = os.getenv(
            "ONEC_LOYALTY_FILTER_FIELDS",
            "БонуснаяКарта_Key,ДисконтнаяКарта_Key,ВладелецКарты_Key,Контрагент_Key,Покупатель_Key",
        )
        fields = [field.strip() for field in raw.split(",") if field.strip()]
        return fields or ["БонуснаяКарта_Key"]
