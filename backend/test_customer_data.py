"""
Скрипт для проверки данных конкретного покупателя в 1С
Используется для диагностики расхождений между данными в 1С и нашей платформе
"""
import argparse
import asyncio
import os
import sys
import httpx
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import json

# Исправление для Windows event loop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Настройка переменных окружения
os.environ.setdefault("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata")
os.environ.setdefault("ONEC_API_TOKEN", "b2RhdGEudXNlcjpvcGV4b2JvZQ==")

ONEC_API_URL = os.getenv("ONEC_API_URL")
ONEC_API_TOKEN = os.getenv("ONEC_API_TOKEN")

DEFAULT_PHONE = "79787566405"


async def fetch_with_auth(url: str, params: Dict[str, Any] = None, max_retries: int = 3):
    """Запрос к 1С API с авторизацией и retry"""
    headers = {
        "Authorization": f"Basic {ONEC_API_TOKEN}",
        "Accept": "application/json"
    }
    
    last_exception = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                return response.json()
        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RequestError) as e:
            last_exception = e
            wait_time = 2 ** attempt
            print(f"Ошибка подключения (попытка {attempt + 1}/{max_retries}): {e}. Повтор через {wait_time}с...")
            if attempt < max_retries - 1:
                await asyncio.sleep(wait_time)
        except httpx.HTTPStatusError as e:
            print(f"HTTP ошибка {e.response.status_code}: {e.response.text}")
            raise
    
    if last_exception:
        raise last_exception
    return None


async def find_discount_card_by_phone(phone: str) -> Optional[Dict[str, Any]]:
    """Поиск дисконтной карты по телефону"""
    print(f"\n{'='*60}")
    print(f"1. Поиск дисконтной карты по телефону: {phone}")
    print(f"{'='*60}")
    
    url = f"{ONEC_API_URL}/Catalog_ДисконтныеКарты"
    params = {
        "$filter": f"КодКартыШтрихкод eq '{phone}'",
        "$top": 1
    }
    
    try:
        data = await fetch_with_auth(url, params)
        cards = data.get("value", [])
        
        if not cards:
            print(f"[ERROR] Дисконтная карта с телефоном {phone} не найдена")
            return None
        
        card = cards[0]
        print(f"[OK] Найдена дисконтная карта:")
        print(f"   Ref_Key: {card.get('Ref_Key')}")
        print(f"   Code: {card.get('Code')}")
        print(f"   Description: {card.get('Description')}")
        print(f"   КодКартыШтрихкод: {card.get('КодКартыШтрихкод')}")
        print(f"   ВладелецКарты_Key: {card.get('ВладелецКарты_Key')}")
        
        # Выводим все поля для анализа
        print(f"\n   Все поля карты:")
        for key, value in sorted(card.items()):
            if value is not None:
                print(f"     {key}: {value}")
        
        return card
    except Exception as e:
        print(f"[ERROR] Ошибка при поиске карты: {e}")
        return None


async def get_customer_details(customer_key: str) -> Optional[Dict[str, Any]]:
    """Получение данных контрагента"""
    print(f"\n{'='*60}")
    print(f"2. Получение данных контрагента: {customer_key}")
    print(f"{'='*60}")
    
    url = f"{ONEC_API_URL}/Catalog_Контрагенты"
    params = {
        "$filter": f"Ref_Key eq guid'{customer_key}'",
        "$top": 1
    }
    
    try:
        data = await fetch_with_auth(url, params)
        customers = data.get("value", [])
        
        if not customers:
            print(f"[ERROR] Контрагент {customer_key} не найден")
            return None
        
        customer = customers[0]
        print(f"[OK] Найден контрагент:")
        print(f"   Ref_Key: {customer.get('Ref_Key')}")
        print(f"   Code: {customer.get('Code')}")
        print(f"   Description: {customer.get('Description')}")
        
        # Выводим все поля для анализа
        print(f"\n   Все поля контрагента:")
        for key, value in sorted(customer.items()):
            if value is not None:
                print(f"     {key}: {value}")
        
        return customer
    except Exception as e:
        print(f"[ERROR] Ошибка при получении контрагента: {e}")
        return None


async def get_loyalty_balance(card_key: str, customer_key: str = None) -> Optional[Dict[str, Any]]:
    """Получение баланса бонусов"""
    print(f"\n{'='*60}")
    print(f"3. Получение баланса бонусов")
    print(f"{'='*60}")
    
    url = f"{ONEC_API_URL}/AccumulationRegister_БонусныеБаллы_RecordType"
    
    # Пробуем разные поля для фильтрации
    filter_fields = [
        ("БонуснаяКарта_Key", card_key),
        ("ДисконтнаяКарта_Key", card_key),
        ("ВладелецКарты_Key", card_key),
    ]
    
    if customer_key:
        filter_fields.extend([
            ("ВладелецКарты_Key", customer_key),
            ("Контрагент_Key", customer_key),
            ("Покупатель_Key", customer_key),
        ])
    
    for field_name, filter_value in filter_fields:
        if not filter_value:
            continue
        
        params = {
            "$filter": f"{field_name} eq guid'{filter_value}'",
            "$top": 1000,
            "$orderby": "Period desc"
        }
        
        try:
            print(f"\n   Попытка фильтрации по полю: {field_name}")
            data = await fetch_with_auth(url, params)
            records = data.get("value", [])
            
            if records:
                print(f"[OK] Найдено записей: {len(records)}")
                
                # Выводим первые 5 записей
                print(f"\n   Первые записи:")
                for i, record in enumerate(records[:5], 1):
                    print(f"\n   Запись {i}:")
                    for key, value in sorted(record.items()):
                        if value is not None:
                            print(f"     {key}: {value}")
                
                # Остаток бонусных баллов = значение поля "КСписанию" из последней записи
                # "КСписанию" показывает, сколько баллов доступно для списания (остаток)
                last_record = records[0] if records else None
                balance = 0
                
                if last_record:
                    к_списанию = last_record.get("КСписанию") or last_record.get("К списанию") or 0
                    начислено = last_record.get("Начислено") or 0
                    try:
                        balance = float(к_списанию)  # Остаток = значение "КСписанию"
                        print(f"\n   [BALANCE] Остаток бонусов (КСписанию): {int(balance)}")
                        print(f"      Начислено: {начислено}, К списанию: {к_списанию}")
                    except (TypeError, ValueError):
                        balance = 0
                        print(f"   [ERROR] Не удалось преобразовать КСписанию в число: {к_списанию}")
                
                return {
                    "field_used": field_name,
                    "records_count": len(records),
                    "balance": int(balance),  # Остаток = КСписанию из последней записи
                    "last_record": last_record,
                    "records": records[:10]  # Первые 10 для анализа
                }
            else:
                print(f"   [WARN] Записей не найдено")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400 and "Сегмент пути" in e.response.text:
                print(f"   [WARN] Поле {field_name} не найдено в регистре")
                continue
            print(f"   [ERROR] HTTP ошибка: {e.response.status_code}: {e.response.text}")
        except Exception as e:
            print(f"   [ERROR] Ошибка: {e}")
    
    print(f"\n[ERROR] Не удалось получить баланс бонусов ни по одному полю")
    return None


async def get_sales_by_card(card_key: str, days: int = 365) -> Optional[Dict[str, Any]]:
    """Получение продаж по дисконтной карте"""
    print(f"\n{'='*60}")
    print(f"4. Получение продаж по дисконтной карте (за {days} дней)")
    print(f"{'='*60}")
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Форматируем даты для OData
    start_date_str = start_date.strftime("%Y-%m-%dT%H:%M:%S")
    end_date_str = end_date.strftime("%Y-%m-%dT%H:%M:%S")
    
    # Пробуем разные endpoints и поля
    endpoints = [
        ("AccumulationRegister_ПродажиПоДисконтнымКартам_RecordType", [
            "ДисконтнаяКарта_Key",
            "Карта_Key",
            "ВладелецКарты_Key",
        ]),
        ("AccumulationRegister_Продажи_RecordType", [
            "Контрагент_Key",
            "Покупатель_Key",
        ]),
    ]
    
    for endpoint, filter_fields in endpoints:
        url = f"{ONEC_API_URL}/{endpoint}"
        
        for field_name in filter_fields:
            # Сначала пробуем без фильтра по дате
            params = {
                "$filter": f"{field_name} eq guid'{card_key}'",
                "$top": 1000,
                "$orderby": "Period desc"
            }
            
            try:
                print(f"\n   Попытка: {endpoint} с полем {field_name}")
                data = await fetch_with_auth(url, params)
                records = data.get("value", [])
                
                if records:
                    print(f"[OK] Найдено продаж: {len(records)}")
                    
                    # Фильтруем по дате в коде
                    filtered_records = []
                    for record in records:
                        period = record.get("Period")
                        if period:
                            try:
                                if isinstance(period, str):
                                    record_date = datetime.fromisoformat(period.replace("Z", "+00:00").split(".")[0])
                                else:
                                    record_date = period
                                if start_date <= record_date <= end_date:
                                    filtered_records.append(record)
                            except:
                                # Если не удалось распарсить дату, включаем запись
                                filtered_records.append(record)
                        else:
                            # Если даты нет, включаем запись
                            filtered_records.append(record)
                    
                    # Рассчитываем сумму
                    total_amount = 0.0
                    total_quantity = 0
                    for record in filtered_records:
                        сумма = record.get("Сумма") or 0
                        количество = record.get("Количество") or 0
                        try:
                            total_amount += float(сумма)
                            total_quantity += float(количество)
                        except (TypeError, ValueError):
                            pass
                    
                    print(f"   [SUM] Общая сумма (за {days} дней): {total_amount:,.2f} руб")
                    print(f"   [QTY] Общее количество: {total_quantity}")
                    print(f"   [CNT] Количество покупок: {len(filtered_records)} (из {len(records)} всего)")
                    
                    # Выводим первые 3 записи
                    print(f"\n   Первые записи:")
                    for i, record in enumerate(records[:3], 1):
                        print(f"\n   Запись {i}:")
                        for key, value in sorted(record.items()):
                            if value is not None:
                                print(f"     {key}: {value}")
                    
                    return {
                        "endpoint": endpoint,
                        "field_used": field_name,
                        "records_count": len(filtered_records),
                        "total_records": len(records),
                        "total_amount": total_amount,
                        "total_quantity": total_quantity,
                        "records": filtered_records[:10]
                    }
                else:
                    print(f"   [WARN] Продаж не найдено")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 400 and "Сегмент пути" in e.response.text:
                    print(f"   [WARN] Поле {field_name} не найдено")
                    continue
                print(f"   [ERROR] HTTP ошибка: {e.response.status_code}: {e.response.text}")
            except Exception as e:
                print(f"   [ERROR] Ошибка: {e}")
    
    print(f"\n[ERROR] Не удалось получить продажи")
    return None


async def search_migration_documents(customer_key: str = None, card_key: str = None, expected_amount: float = None) -> Optional[List[Dict[str, Any]]]:
    """Поиск документов переноса данных из старой системы"""
    print(f"\n{'='*60}")
    print(f"Поиск документов переноса/миграции данных")
    print(f"{'='*60}")
    
    if expected_amount:
        print(f"   Ожидаемая сумма переноса: {expected_amount:,.2f} руб")
    
    # Типы документов, которые могут содержать перенос данных
    document_types = [
        "Document_ВводОстатков",
        "Document_ВводНачальныхОстатков",
        "Document_ПервоначальныеДанные",
        "Document_МиграцияДанных",
        "Document_ПереносДанных",
    ]
    
    found_documents = []
    
    for doc_type in document_types:
        try:
            url = f"{ONEC_API_URL}/{doc_type}"
            params = {
                "$top": 100,
                "$orderby": "Date desc"
            }
            
            print(f"\n   Проверка типа документа: {doc_type}")
            data = await fetch_with_auth(url, params)
            documents = data.get("value", [])
            
            if documents:
                print(f"   [OK] Найдено документов: {len(documents)}")
                
                # Фильтруем по покупателю, если указан
                for doc in documents:
                    # Выводим все поля для анализа
                    print(f"\n   Документ: {doc.get('Number', 'N/A')}")
                    
                    # Ищем сумму в различных полях
                    suma = None
                    suma_fields = [
                        'Сумма', 'СуммаДокумента', 'СуммаВсего', 'Итого',
                        'СуммаПродаж', 'СуммаПокупок', 'Amount', 'Total'
                    ]
                    
                    for field in suma_fields:
                        if field in doc and doc[field]:
                            suma = doc[field]
                            print(f"     {field}: {suma}")
                            break
                    
                    # Выводим основные поля
                    print(f"     Date: {doc.get('Date', 'N/A')}")
                    print(f"     Ref_Key: {doc.get('Ref_Key', 'N/A')}")
                    print(f"     Posted: {doc.get('Posted', 'N/A')}")
                    
                    # ВСЕ поля документа не выводим (слишком много данных)
                    # Для отладки можно раскомментировать:
                    # print(f"\n     Все поля документа:")
                    # for key, value in sorted(doc.items()):
                    #     if value is not None and not key.endswith("@navigationLinkUrl"):
                    #         print(f"       {key}: {value}")
                    
                    found_documents.append({
                        "type": doc_type,
                        "document": doc,
                        "suma": suma
                    })
            else:
                print(f"   [INFO] Документы типа {doc_type} не найдены")
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                print(f"   [INFO] Тип документа {doc_type} не существует в системе")
            else:
                print(f"   [WARN] Ошибка при запросе {doc_type}: {e.response.status_code}")
        except Exception as e:
            print(f"   [WARN] Ошибка при обработке {doc_type}: {e}")
    
    # Дополнительный поиск: проверяем регистры на наличие старых записей с большой суммой
    print(f"\n{'='*60}")
    print(f"Поиск в регистрах накопления по сумме")
    print(f"{'='*60}")
    
    if card_key and expected_amount:
        # Ищем в регистре продаж записи с суммой близкой к ожидаемой
        try:
            url = f"{ONEC_API_URL}/AccumulationRegister_ПродажиПоДисконтнымКартам_RecordType"
            params = {
                "$filter": f"ДисконтнаяКарта_Key eq guid'{card_key}'",
                "$top": 1000,
                "$orderby": "Period"  # От старых к новым
            }
            
            data = await fetch_with_auth(url, params)
            records = data.get("value", [])
            
            if records:
                print(f"\n   Анализ {len(records)} записей продаж...")
                
                # Ищем запись с суммой близкой к ожидаемой (±10%)
                tolerance = expected_amount * 0.1
                
                for record in records:
                    сумма = record.get("Сумма", 0)
                    try:
                        сумма_float = float(сумма)
                        if abs(сумма_float - expected_amount) <= tolerance:
                            print(f"\n   [FOUND] Найдена запись с похожей суммой:")
                            print(f"     Period: {record.get('Period')}")
                            print(f"     Сумма: {сумма_float:,.2f} руб")
                            print(f"     Recorder: {record.get('Recorder')}")
                            print(f"     Recorder_Type: {record.get('Recorder_Type')}")
                            print(f"     Количество: {record.get('Количество')}")
                            
                            # Пробуем получить документ
                            recorder = record.get('Recorder')
                            recorder_type = record.get('Recorder_Type')
                            
                            if recorder and recorder_type:
                                # Извлекаем тип документа из Recorder_Type
                                # Например: StandardODATA.Document_ОтчетОРозничныхПродажах
                                if 'Document_' in recorder_type:
                                    doc_type_name = recorder_type.split('Document_')[1]
                                    
                                    # Для документов "ВводНачальныхОстатков" используем сумму из записи регистра
                                    if doc_type_name == 'ВводНачальныхОстатков':
                                        try:
                                            doc_url = f"{ONEC_API_URL}/Document_{doc_type_name}"
                                            doc_params = {
                                                "$filter": f"Ref_Key eq guid'{recorder}'",
                                                "$top": 1
                                            }
                                            doc_data = await fetch_with_auth(doc_url, doc_params)
                                            docs = doc_data.get("value", [])
                                            if docs:
                                                doc = docs[0]
                                                print(f"\n     Детали документа:")
                                                print(f"       Number: {doc.get('Number', 'N/A')}")
                                                print(f"       Date: {doc.get('Date', 'N/A')}")
                                                print(f"       Posted: {doc.get('Posted', 'N/A')}")
                                                
                                                # Добавляем документ в список найденных
                                                # ВАЖНО: Используем сумму из записи регистра, а не из документа!
                                                found_documents.append({
                                                    "type": f"Document_{doc_type_name}",
                                                    "document": doc,
                                                    "suma": сумма_float,  # Сумма из записи регистра
                                                    "source": "register",  # Указываем источник
                                                    "register_record": {
                                                        "Period": record.get('Period'),
                                                        "Сумма": сумма_float,
                                                        "Количество": record.get('Количество')
                                                    }
                                                })
                                                print(f"     [OK] Документ переноса добавлен (сумма из регистра: {сумма_float:,.2f} руб)")
                                        except Exception as e:
                                            print(f"     [WARN] Не удалось получить документ: {e}")
                                    else:
                                        # Для других типов документов получаем детали
                                        try:
                                            doc_url = f"{ONEC_API_URL}/Document_{doc_type_name}"
                                            doc_params = {
                                                "$filter": f"Ref_Key eq guid'{recorder}'",
                                                "$top": 1
                                            }
                                            doc_data = await fetch_with_auth(doc_url, doc_params)
                                            docs = doc_data.get("value", [])
                                            if docs:
                                                doc = docs[0]
                                                print(f"\n     Детали документа:")
                                                print(f"       Number: {doc.get('Number', 'N/A')}")
                                                print(f"       Date: {doc.get('Date', 'N/A')}")
                                                print(f"       Posted: {doc.get('Posted', 'N/A')}")
                                        except Exception as e:
                                            print(f"     [WARN] Не удалось получить документ: {e}")
                    except (TypeError, ValueError):
                        pass
        except Exception as e:
            print(f"   [ERROR] Ошибка при поиске в регистре: {e}")
    
    return found_documents if found_documents else None


async def get_retail_sales_document_details(document_key: str) -> Optional[Dict[str, Any]]:
    """Получение деталей документа 'ОтчетОРозничныхПродажах' и его строк с артикулами"""
    print(f"\n{'='*60}")
    print(f"Получение деталей документа продажи: {document_key}")
    print(f"{'='*60}")
    
    # Пробуем разные варианты endpoint для документа
    document_endpoints = [
        "Document_ОтчетОРозничныхПродажах",
        "Document_ОтчетОРозничныхПродажах_Товары",
    ]
    
    # Сначала получаем сам документ
    url = f"{ONEC_API_URL}/Document_ОтчетОРозничныхПродажах"
    params = {
        "$filter": f"Ref_Key eq guid'{document_key}'",
        "$top": 1
    }
    
    try:
        print(f"\n   Получение документа...")
        data = await fetch_with_auth(url, params)
        documents = data.get("value", [])
        
        if not documents:
            print(f"[ERROR] Документ {document_key} не найден")
            return None
        
        document = documents[0]
        print(f"[OK] Найден документ:")
        print(f"   Ref_Key: {document.get('Ref_Key')}")
        print(f"   Number: {document.get('Number')}")
        print(f"   Date: {document.get('Date')}")
        print(f"   Posted: {document.get('Posted')}")
        
        # Получаем строки документа (товары) из регистра накопления
        # В 1С OData строки документа доступны через регистр накопления, где Recorder указывает на документ
        print(f"\n   Получение строк документа из регистра накопления...")
        
        lines = []
        # Пробуем получить строки из регистра накопления по Recorder
        register_endpoints = [
            "AccumulationRegister_ПродажиПоДисконтнымКартам_RecordType",
            "AccumulationRegister_Продажи_RecordType",
        ]
        
        for endpoint in register_endpoints:
            try:
                register_url = f"{ONEC_API_URL}/{endpoint}"
                params = {
                    "$filter": f"Recorder eq guid'{document_key}'",
                    "$top": 1000,
                    "$orderby": "LineNumber"
                }
                
                print(f"   Попытка получить строки из: {endpoint}")
                register_data = await fetch_with_auth(register_url, params)
                register_records = register_data.get("value", [])
                
                if register_records:
                    print(f"[OK] Найдено строк в регистре: {len(register_records)}")
                    lines = register_records
                    break
            except Exception as e:
                print(f"   [WARN] Не удалось получить строки из {endpoint}: {e}")
                continue
        
        # Если не получили строки из регистра, пробуем навигационное свойство (на случай, если оно работает)
        if not lines:
            print(f"\n   [INFO] Строки не найдены в регистре, пробуем навигационное свойство...")
            lines_urls = [
                f"{ONEC_API_URL}/Document_ОтчетОРозничныхПродажах(guid'{document_key}')/Товары",
            ]
            
            for lines_url in lines_urls:
                try:
                    print(f"   Попытка получить строки из: {lines_url}")
                    lines_data = await fetch_with_auth(lines_url, None)
                    lines_records = lines_data.get("value", [])
                    
                    if lines_records:
                        print(f"[OK] Найдено строк через навигацию: {len(lines_records)}")
                        lines = lines_records
                        break
                except Exception as e:
                    print(f"   [WARN] Не удалось получить строки из {lines_url}: {e}")
                    continue
        
        if not lines:
            print(f"\n   [WARN] Строки документа не найдены ни в регистре, ни через навигацию")
            return {
                "document": document,
                "lines": [],
                "message": "Строки документа не найдены"
            }
        
        # Для каждой строки получаем артикул товара и проверяем связь с каталогом GLAME
        lines_with_articles = []
        for i, line in enumerate(lines, 1):
            номенклатура_key = line.get("Номенклатура_Key")
            line_data = {
                "line_number": i,
                "line_number_1c": line.get("LineNumber"),
                "номенклатура_key": номенклатура_key,
                "номенклатура_description": line.get("Номенклатура_Description"),
                "количество": line.get("Количество", 0),
                "цена": line.get("Цена", 0),
                "сумма": line.get("Сумма", 0),
                "скидка": line.get("Скидка", 0),
                "характеристика_key": line.get("Характеристика_Key"),
            }
            
            # Получаем артикул товара из Catalog_Номенклатура
            if номенклатура_key:
                try:
                    product_url = f"{ONEC_API_URL}/Catalog_Номенклатура"
                    product_params = {
                        "$filter": f"Ref_Key eq guid'{номенклатура_key}'",
                        "$top": 1
                    }
                    product_data = await fetch_with_auth(product_url, product_params)
                    products = product_data.get("value", [])
                    
                    if products:
                        product = products[0]
                        артикул = product.get("Code") or product.get("Артикул")
                        line_data["артикул"] = артикул
                        line_data["название"] = product.get("Description") or product.get("Наименование")
                        line_data["категория"] = product.get("ВидНоменклатуры") or product.get("Категория")
                        line_data["бренд"] = product.get("Бренд") or product.get("Производитель")
                        
                        # Пропускаем упаковку (мешочки, салфетки, пакеты, коробки и т.д.)
                        упаковка_ключевые_слова = [
                            'мешочек', 'мешок', 'пакет', 'салфетка', 'коробка', 
                            'упаковка', 'конверт', 'футляр', 'чехол', 'обертка',
                            'bag', 'box', 'pack', 'wrap', 'case', 'pouch'
                        ]
                        название_нижний = (line_data.get("название") or "").lower()
                        if any(ключ in название_нижний for ключ in упаковка_ключевые_слова):
                            line_data["linked"] = False
                            line_data["is_packaging"] = True
                            print(f"   [SKIP] Товар {i} пропущен (упаковка): {line_data['название']} (артикул: {артикул})")
                            continue
                        
                        # Проверяем связь с каталогом GLAME
                        if артикул:
                            try:
                                from app.database.connection import AsyncSessionLocal
                                from app.models.product import Product
                                from sqlalchemy import select
                                
                                async with AsyncSessionLocal() as session:
                                    # Поиск по external_id (приоритет 1)
                                    stmt = select(Product).where(Product.external_id == номенклатура_key)
                                    result = await session.execute(stmt)
                                    glame_product = result.scalars().first()
                                    
                                    # Поиск по артикулу (приоритет 2)
                                    if not glame_product and артикул:
                                        stmt = select(Product).where(
                                            (Product.article == артикул) | (Product.external_code == артикул)
                                        )
                                        result = await session.execute(stmt)
                                        glame_product = result.scalars().first()
                                    
                                    if glame_product:
                                        line_data["glame_product_id"] = str(glame_product.id)
                                        line_data["glame_product_name"] = glame_product.name
                                        line_data["linked"] = True
                                        print(f"   [OK] Товар {i}: {line_data['название']} (артикул: {артикул}) -> СВЯЗАН с GLAME: {glame_product.name}")
                                    else:
                                        line_data["linked"] = False
                                        print(f"   [WARN] Товар {i}: {line_data['название']} (артикул: {артикул}) -> НЕ НАЙДЕН в каталоге GLAME")
                            except Exception as e:
                                print(f"   [WARN] Ошибка при проверке связи с каталогом: {e}")
                                line_data["linked"] = False
                        else:
                            line_data["linked"] = False
                            print(f"   [WARN] Товар {i}: {line_data['название']} -> артикул не найден")
                    else:
                        print(f"   [WARN] Товар {номенклатура_key} не найден в каталоге 1С")
                        line_data["linked"] = False
                except Exception as e:
                    print(f"   [WARN] Ошибка при получении данных товара {номенклатура_key}: {e}")
                    line_data["linked"] = False
            
            lines_with_articles.append(line_data)
        
        return {
            "document": document,
            "lines": lines_with_articles,
            "lines_count": len(lines_with_articles)
        }
        
    except Exception as e:
        print(f"[ERROR] Ошибка при получении деталей документа: {e}")
        import traceback
        traceback.print_exc()
        return None


async def check_our_database(phone: str):
    """Проверка данных в нашей БД"""
    print(f"\n{'='*60}")
    print(f"5. Проверка данных в нашей БД")
    print(f"{'='*60}")
    
    try:
        from app.database.connection import AsyncSessionLocal
        from app.models.user import User
        from sqlalchemy import select
        
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.phone == phone)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                print(f"[ERROR] Пользователь с телефоном {phone} не найден в БД")
                return None
            
            print(f"[OK] Найден пользователь:")
            print(f"   ID: {user.id}")
            print(f"   Phone: {user.phone}")
            print(f"   Full name: {user.full_name}")
            print(f"   Email: {user.email}")
            print(f"   Discount card number: {user.discount_card_number}")
            print(f"   Discount card ID 1C: {user.discount_card_id_1c}")
            print(f"   Customer ID 1C: {user.customer_id_1c}")
            print(f"   Loyalty points: {user.loyalty_points}")
            print(f"   Total purchases: {user.total_purchases}")
            print(f"   Total spent: {user.total_spent} (копеек) = {user.total_spent / 100:.2f} ₽")
            print(f"   Average check: {user.average_check} (копеек) = {user.average_check / 100:.2f} ₽" if user.average_check else "   Average check: None")
            print(f"   Last purchase date: {user.last_purchase_date}")
            # Безопасное получение city (может не существовать, если миграция не применена)
            city = getattr(user, 'city', None)
            print(f"   City: {city or 'не указан'}")
            print(f"   Synced at: {user.synced_at}")
            
            return user
    except Exception as e:
        print(f"[ERROR] Ошибка при проверке БД: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main(phone: str):
    """Основная функция"""
    print(f"\n{'='*60}")
    print(f"ПРОВЕРКА ДАННЫХ ПОКУПАТЕЛЯ: {phone}")
    print(f"{'='*60}")
    
    # 1. Находим дисконтную карту
    card = await find_discount_card_by_phone(phone)
    if not card:
        print("\n[ERROR] Не удалось найти дисконтную карту. Завершение.")
        return
    
    card_key = card.get("Ref_Key")
    customer_key = card.get("ВладелецКарты_Key")
    
    # 2. Получаем данные контрагента
    customer = None
    if customer_key:
        customer = await get_customer_details(customer_key)
    
    # 3. Получаем баланс бонусов
    loyalty_data = await get_loyalty_balance(card_key, customer_key)
    
    # 4. Получаем продажи
    sales_data = await get_sales_by_card(card_key)
    
    # 4.0. Поиск документов переноса/миграции данных из старой системы
    # Разница между суммой в UI (365,054) и API (132,694) = ~232,360 руб
    migration_docs = None
    migration_amount = 365054.00 - (sales_data.get("total_amount", 0) if sales_data else 0)
    if migration_amount > 1000:  # Если разница больше 1000 руб
        print(f"\n{'='*60}")
        print(f"Обнаружена разница в суммах: {migration_amount:,.2f} руб")
        print(f"Поиск документов переноса данных...")
        print(f"{'='*60}")
        migration_docs = await search_migration_documents(
            customer_key=customer_key,
            card_key=card_key,
            expected_amount=migration_amount
        )
    
    # 4.1. Анализируем товары из продаж и проверяем связь с каталогом GLAME
    if sales_data and sales_data.get("records"):
        print(f"\n{'='*60}")
        print(f"4.1. Анализ товаров и проверка связи с каталогом GLAME")
        print(f"{'='*60}")
        
        # Используем данные из регистра накопления, которые уже получены
        total_lines = 0
        linked_lines = 0
        products_processed = set()  # Для уникальности
        
        # Обрабатываем первые 10 записей
        for record in sales_data["records"][:10]:
            номенклатура_key = record.get("Номенклатура_Key")
            if not номенклатура_key or номенклатура_key in products_processed:
                continue
            
            products_processed.add(номенклатура_key)
            total_lines += 1
            
            try:
                # Получаем артикул товара из Catalog_Номенклатура
                product_url = f"{ONEC_API_URL}/Catalog_Номенклатура"
                product_params = {
                    "$filter": f"Ref_Key eq guid'{номенклатура_key}'",
                    "$top": 1
                }
                product_data = await fetch_with_auth(product_url, product_params)
                products = product_data.get("value", [])
                
                if products:
                    product = products[0]
                    артикул = product.get("Code") or product.get("Артикул")
                    название = product.get("Description") or product.get("Наименование")
                    
                    # Пропускаем упаковку (мешочки, салфетки, пакеты, коробки и т.д.)
                    упаковка_ключевые_слова = [
                        'мешочек', 'мешок', 'пакет', 'салфетка', 'коробка', 
                        'упаковка', 'конверт', 'футляр', 'чехол', 'обертка',
                        'bag', 'box', 'pack', 'wrap', 'case', 'pouch'
                    ]
                    название_нижний = (название or "").lower()
                    if any(ключ in название_нижний for ключ in упаковка_ключевые_слова):
                        print(f"   [SKIP] Товар пропущен (упаковка): {название[:50]} (артикул: {артикул})")
                        total_lines -= 1  # Не считаем упаковку в общее количество
                        continue
                    
                    # Проверяем связь с каталогом GLAME
                    if артикул:
                        try:
                            from app.database.connection import AsyncSessionLocal
                            from app.models.product import Product
                            from sqlalchemy import select
                            
                            async with AsyncSessionLocal() as session:
                                # Поиск по external_id (приоритет 1)
                                stmt = select(Product).where(Product.external_id == номенклатура_key)
                                result = await session.execute(stmt)
                                glame_product = result.scalars().first()
                                
                                # Поиск по артикулу (приоритет 2)
                                if not glame_product and артикул:
                                    stmt = select(Product).where(
                                        (Product.article == артикул) | (Product.external_code == артикул)
                                    )
                                    result = await session.execute(stmt)
                                    glame_product = result.scalars().first()
                                
                                if glame_product:
                                    linked_lines += 1
                                    print(f"   [OK] Товар: {название[:50]} (артикул: {артикул}) -> СВЯЗАН с GLAME: {glame_product.name}")
                                else:
                                    print(f"   [WARN] Товар: {название[:50]} (артикул: {артикул}) -> НЕ НАЙДЕН в каталоге GLAME")
                        except Exception as e:
                            print(f"   [ERROR] Ошибка при проверке связи: {e}")
                    else:
                        print(f"   [WARN] Товар: {название[:50]} -> артикул не найден")
                else:
                    print(f"   [WARN] Товар {номенклатура_key} не найден в каталоге 1С")
            except Exception as e:
                print(f"   [ERROR] Ошибка при обработке товара {номенклатура_key}: {e}")
        
        print(f"\n[SUMMARY] Анализ товаров:")
        print(f"   Всего уникальных товаров: {total_lines}")
        print(f"   Связано с каталогом GLAME: {linked_lines}")
        print(f"   Не связано: {total_lines - linked_lines}")
        if total_lines > 0:
            print(f"   Процент связанных: {linked_lines * 100 // total_lines}%")
    
    # 5. Проверяем нашу БД
    db_user = await check_our_database(phone)
    
    # 6. Извлекаем город из данных 1С
    city_from_1c = None
    if customer:
        try:
            # ПРИОРИТЕТ 1: Поле "ОсновныеСведения" (многострочное, город на 3-й строке)
            основные_сведения = customer.get("ОсновныеСведения")
            if основные_сведения:
                if isinstance(основные_сведения, str):
                    # Разбиваем на строки и берем третью строку (индекс 2)
                    lines = основные_сведения.strip().split('\n')
                    if len(lines) >= 3:
                        city_from_1c = lines[2].strip()
                        if city_from_1c:
                            print(f"[INFO] Город найден в ОсновныеСведения: {city_from_1c}")
                elif isinstance(основные_сведения, list) and len(основные_сведения) >= 3:
                    city_from_1c = str(основные_сведения[2]).strip()
                    if city_from_1c:
                        print(f"[INFO] Город найден в ОсновныеСведения (список): {city_from_1c}")
            
            # ПРИОРИТЕТ 2: Пробуем разные варианты структуры адреса
            if not city_from_1c:
                address_data = customer.get("Состав") or customer.get("Адрес") or customer.get("Address")
                
                if address_data:
                    # Если это словарь с вложенной структурой
                    if isinstance(address_data, dict):
                        # Пробуем найти АдресРФ
                        address_rf = address_data.get("АдресРФ") or address_data.get("Адрес")
                        if address_rf and isinstance(address_rf, dict):
                            # Берем значение из поля Улица (там хранится город)
                            city_from_1c = address_rf.get("Улица") or address_rf.get("Город") or address_rf.get("City")
                        # Если нет вложенности, проверяем прямое поле Улица
                        if not city_from_1c:
                            city_from_1c = address_data.get("Улица") or address_data.get("Город") or address_data.get("City")
                    # Если это список, берем первый элемент
                    elif isinstance(address_data, list) and len(address_data) > 0:
                        first_item = address_data[0]
                        if isinstance(first_item, dict):
                            address_rf = first_item.get("АдресРФ") or first_item.get("Адрес")
                            if address_rf and isinstance(address_rf, dict):
                                city_from_1c = address_rf.get("Улица") or address_rf.get("Город") or address_rf.get("City")
                            if not city_from_1c:
                                city_from_1c = first_item.get("Улица") or first_item.get("Город") or first_item.get("City")
            
            # ПРИОРИТЕТ 3: Прямые поля для города
            if not city_from_1c:
                city_from_1c = customer.get("Город") or customer.get("City") or customer.get("НаселенныйПункт")
        except Exception as e:
            print(f"[WARN] Ошибка при извлечении города из данных 1С: {e}")
    
    # 7. Сравнение данных
    print(f"\n{'='*60}")
    print(f"7. СРАВНЕНИЕ ДАННЫХ")
    print(f"{'='*60}")
    
    # Безопасное получение city из БД (может не существовать, если миграция не применена)
    db_city = getattr(db_user, 'city', None) if db_user else None
    if city_from_1c or db_city:
        print(f"\n[CITY] ГОРОД:")
        if city_from_1c:
            print(f"   1С: {city_from_1c}")
        if db_user:
            print(f"   Наша БД: {db_city or 'не указан'}")
            if city_from_1c and city_from_1c != db_city:
                print(f"   [DIFF] РАСХОЖДЕНИЕ: {city_from_1c} vs {db_city}")
            elif city_from_1c and city_from_1c == db_city:
                print(f"   [OK] Совпадает")
    
    if loyalty_data:
        print(f"\n[BONUSES] БОНУСЫ:")
        print(f"   1С: {loyalty_data['balance']} баллов")
        if db_user:
            print(f"   Наша БД: {db_user.loyalty_points} баллов")
            if loyalty_data['balance'] != db_user.loyalty_points:
                print(f"   [DIFF] РАСХОЖДЕНИЕ: {loyalty_data['balance']} vs {db_user.loyalty_points}")
            else:
                print(f"   [OK] Совпадает")
    
    if sales_data:
        print(f"\n[SALES] ПРОДАЖИ:")
        print(f"   1С API (текущие): {sales_data['total_amount']:,.2f} руб, {sales_data['records_count']} покупок")
        if db_user:
            db_total = db_user.total_spent / 100 if db_user.total_spent else 0
            print(f"   Наша БД: {db_total:,.2f} руб, {db_user.total_purchases} покупок")
            if abs(sales_data['total_amount'] - db_total) > 0.01:
                print(f"   [DIFF] РАСХОЖДЕНИЕ по сумме: {sales_data['total_amount']:,.2f} vs {db_total:,.2f}")
            if sales_data['records_count'] != db_user.total_purchases:
                print(f"   [DIFF] РАСХОЖДЕНИЕ по количеству: {sales_data['records_count']} vs {db_user.total_purchases}")
            if abs(sales_data['total_amount'] - db_total) < 0.01 and sales_data['records_count'] == db_user.total_purchases:
                print(f"   [OK] Совпадает")
    
    # Выводим информацию о документах переноса, если найдены
    if migration_docs and len(migration_docs) > 0:
        print(f"\n[MIGRATION] ДОКУМЕНТЫ ПЕРЕНОСА ДАННЫХ:")
        print(f"   Найдено документов переноса: {len(migration_docs)}")
        
        total_migration_sum = 0.0
        
        for i, doc_info in enumerate(migration_docs, 1):
            doc = doc_info.get("document", {})
            doc_type = doc_info.get("type", "Unknown")
            suma = doc_info.get("suma")
            source = doc_info.get("source", "document")  # "register" или "document"
            register_record = doc_info.get("register_record")
            
            print(f"\n   Документ {i}:")
            print(f"     Тип: {doc_type}")
            print(f"     Number: {doc.get('Number', 'N/A')}")
            print(f"     Date: {doc.get('Date', 'N/A')}")
            print(f"     Ref_Key: {doc.get('Ref_Key', 'N/A')}")
            print(f"     Posted: {doc.get('Posted', 'N/A')}")
            
            # Выводим сумму, если найдена
            if suma:
                try:
                    suma_float = float(suma)
                    total_migration_sum += suma_float
                    if source == "register" and register_record:
                        print(f"     Сумма (из регистра): {suma_float:,.2f} руб")
                        print(f"       Period: {register_record.get('Period', 'N/A')}")
                        print(f"       Количество: {register_record.get('Количество', 'N/A')}")
                    else:
                        print(f"     Сумма: {suma_float:,.2f} руб")
                except (TypeError, ValueError):
                    print(f"     Сумма: {suma} (не удалось преобразовать)")
            else:
                # Ищем поле с суммой в самом документе
                suma_fields = [
                    'Сумма', 'СуммаДокумента', 'СуммаВсего', 'Итого',
                    'СуммаПродаж', 'СуммаПокупок', 'Amount', 'Total'
                ]
                found_suma = False
                for field in suma_fields:
                    if field in doc and doc[field]:
                        try:
                            suma_float = float(doc[field])
                            total_migration_sum += suma_float
                            print(f"     {field}: {suma_float:,.2f} руб")
                            found_suma = True
                            break
                        except (TypeError, ValueError):
                            pass
                
                if not found_suma:
                    print(f"     Сумма: НЕ НАЙДЕНА (документ может не содержать итоговой суммы)")
        
        if total_migration_sum > 0:
            print(f"\n   [ИТОГО] Общая сумма переноса: {total_migration_sum:,.2f} руб")
        else:
            print(f"\n   [WARN] Сумма переноса не определена (поля суммы не найдены в документах)")
            print(f"   [INFO] Возможно, нужно запросить строки документа или использовать другой регистр")
    elif migration_amount and migration_amount > 1000:
        print(f"\n[MIGRATION] ДОКУМЕНТЫ ПЕРЕНОСА:")
        print(f"   Ожидаемая сумма переноса: {migration_amount:,.2f} руб")
        print(f"   Документы переноса НЕ НАЙДЕНЫ")
        print(f"   Возможно, данные были перенесены другим способом или под другим покупателем")
    
    # 8. ФИНАЛЬНЫЕ ИТОГОВЫЕ ДАННЫЕ
    print(f"\n{'='*60}")
    print(f"8. ИТОГОВЫЕ ДАННЫЕ")
    print(f"{'='*60}")
    
    # Город
    if city_from_1c:
        print(f"\n[ИТОГИ] ГОРОД:")
        print(f"   Город: {city_from_1c}")
    
    # Собираем общую сумму переноса
    total_migration_sum = 0.0
    if migration_docs and len(migration_docs) > 0:
        for doc_info in migration_docs:
            suma = doc_info.get("suma")
            if suma:
                try:
                    total_migration_sum += float(suma)
                except (TypeError, ValueError):
                    pass
            else:
                # Ищем сумму в документе
                doc = doc_info.get("document", {})
                suma_fields = ['Сумма', 'СуммаДокумента', 'СуммаВсего', 'Итого', 'СуммаПродаж', 'СуммаПокупок']
                for field in suma_fields:
                    if field in doc and doc[field]:
                        try:
                            total_migration_sum += float(doc[field])
                            break
                        except (TypeError, ValueError):
                            pass
    
    # Общая сумма покупок = начальный ввод + покупки за год
    sales_total = sales_data.get('total_amount', 0) if sales_data else 0
    total_purchases_sum = total_migration_sum + sales_total
    
    print(f"\n[ИТОГИ] ОБЩАЯ СУММА ПОКУПОК:")
    print(f"   Начальный ввод (перенос): {total_migration_sum:,.2f} руб")
    print(f"   Покупки за год: {sales_total:,.2f} руб")
    print(f"   ИТОГО: {total_purchases_sum:,.2f} руб")
    
    # Количество баллов
    if loyalty_data:
        print(f"\n[ИТОГИ] КОЛИЧЕСТВО БАЛЛОВ:")
        print(f"   Бонусные баллы: {loyalty_data['balance']} баллов")
    
    # История покупок товаров
    if sales_data and sales_data.get("records"):
        print(f"\n[ИТОГИ] ИСТОРИЯ ПОКУПОК ТОВАРОВ:")
        print(f"   Всего записей в истории: {len(sales_data['records'])}")
        print(f"   Показываем последние 20 покупок:")
        print(f"\n   {'Дата':<20} {'Товар':<50} {'Артикул':<20} {'Сумма':>15} {'Кол-во':>10}")
        print(f"   {'-'*20} {'-'*50} {'-'*20} {'-'*15} {'-'*10}")
        
        # Сортируем по дате (от новых к старым) и берем последние 20
        sorted_records = sorted(
            sales_data['records'][:100],  # Обрабатываем первые 100 для производительности
            key=lambda x: x.get('Period', ''),
            reverse=True
        )[:20]
        
        # Кэш для товаров, чтобы не делать повторные запросы
        products_cache = {}
        
        for record in sorted_records:
            period = record.get('Period', 'N/A')
            if isinstance(period, str):
                try:
                    # Форматируем дату
                    period_dt = datetime.fromisoformat(period.replace("Z", "+00:00").split(".")[0])
                    period_str = period_dt.strftime("%Y-%m-%d %H:%M")
                except:
                    period_str = str(period)[:19]
            else:
                period_str = str(period)[:19]
            
            номенклатура_key = record.get("Номенклатура_Key")
            сумма = record.get("Сумма", 0)
            количество = record.get("Количество", 0)
            
            # Получаем название товара из кэша или делаем запрос
            название = "Неизвестно"
            артикул = "N/A"
            
            if номенклатура_key:
                if номенклатура_key in products_cache:
                    название = products_cache[номенклатура_key]['название']
                    артикул = products_cache[номенклатура_key]['артикул']
                else:
                    try:
                        product_url = f"{ONEC_API_URL}/Catalog_Номенклатура"
                        product_params = {
                            "$filter": f"Ref_Key eq guid'{номенклатура_key}'",
                            "$top": 1
                        }
                        product_data = await fetch_with_auth(product_url, product_params)
                        products = product_data.get("value", [])
                        if products:
                            product = products[0]
                            название = (product.get("Description") or product.get("Наименование") or "Неизвестно")[:48]
                            артикул = (product.get("Code") or product.get("Артикул") or "N/A")[:18]
                            # Сохраняем в кэш
                            products_cache[номенклатура_key] = {
                                'название': название,
                                'артикул': артикул
                            }
                    except Exception as e:
                        # Сохраняем в кэш, чтобы не повторять запрос
                        products_cache[номенклатура_key] = {
                            'название': "Ошибка загрузки",
                            'артикул': "N/A"
                        }
            
            try:
                сумма_float = float(сумма)
                количество_float = float(количество)
                print(f"   {period_str:<20} {название:<50} {артикул:<20} {сумма_float:>15,.2f} {количество_float:>10.1f}")
            except (TypeError, ValueError):
                print(f"   {period_str:<20} {название:<50} {артикул:<20} {'N/A':>15} {'N/A':>10}")
    
    print(f"\n{'='*60}")
    print(f"ПРОВЕРКА ЗАВЕРШЕНА")
    print(f"{'='*60}\n")


def parse_args():
    parser = argparse.ArgumentParser(description="Debug 1C customer data")
    parser.add_argument("--phone", "-p", default=os.getenv("PHONE_TO_CHECK", DEFAULT_PHONE), help="Телефон покупателя")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.phone))
