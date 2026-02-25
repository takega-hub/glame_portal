"""
Скрипт для проверки доступных данных о продажах из 1С
Определяет с какой даты доступны данные и какие регистры можно использовать
"""
import asyncio
import httpx
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import json

if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

sys.path.insert(0, str(Path(__file__).parent))

env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)


async def check_1c_sales_availability():
    """Проверка доступных данных о продажах из 1С"""
    
    api_url = os.getenv("ONEC_API_URL")
    api_token = os.getenv("ONEC_API_TOKEN")
    sales_endpoint = os.getenv("ONEC_SALES_ENDPOINT", "/AccumulationRegister_Продажи_RecordType")
    
    if not api_url:
        print("[ERROR] ONEC_API_URL не настроен в .env")
        return
    
    if not api_token:
        print("[ERROR] ONEC_API_TOKEN не настроен в .env")
        return
    
    print("=" * 80)
    print("ПРОВЕРКА ДОСТУПНЫХ ДАННЫХ О ПРОДАЖАХ ИЗ 1С")
    print("=" * 80)
    print(f"\nAPI URL: {api_url}")
    print(f"Endpoint: {sales_endpoint}")
    print()
    
    headers = {
        "Accept": "application/json"
    }
    if api_token.startswith("Basic "):
        headers["Authorization"] = api_token
    else:
        headers["Authorization"] = f"Basic {api_token}"
    
    async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
        url = f"{api_url.rstrip('/')}{sales_endpoint}"
        
        print(f"[INFO] Запрос к 1С: {url}")
        print()
        
        try:
            # Запрашиваем первые записи (самые новые)
            params = {
                "$top": 10,
                "$orderby": "Period desc"
            }
            
            print("[INFO] Получение последних записей (для проверки структуры)...")
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            records = data.get('value', [])
            
            if not records:
                print("[WARNING] Не получено записей из 1С")
                print("[INFO] Возможные причины:")
                print("  - Нет данных в регистре")
                print("  - Неправильный endpoint")
                print("  - Проблемы с правами доступа")
                return
            
            print(f"[OK] Получено {len(records)} записей")
            print()
            
            # Анализируем структуру данных
            print("=" * 80)
            print("СТРУКТУРА ДАННЫХ")
            print("=" * 80)
            if records:
                print("\nПоля первой записи:")
                first_record = records[0]
                for key, value in first_record.items():
                    value_str = str(value)
                    if len(value_str) > 100:
                        value_str = value_str[:100] + "..."
                    print(f"  {key}: {value_str}")
            
            # Определяем самую раннюю дату
            print("\n" + "=" * 80)
            print("ОПРЕДЕЛЕНИЕ ДИАПАЗОНА ДАТ")
            print("=" * 80)
            
            # Запрашиваем самую раннюю запись
            params_oldest = {
                "$top": 1,
                "$orderby": "Period asc"
            }
            
            print("\n[INFO] Поиск самой ранней записи...")
            response_oldest = await client.get(url, params=params_oldest)
            response_oldest.raise_for_status()
            
            data_oldest = response_oldest.json()
            oldest_records = data_oldest.get('value', [])
            
            if oldest_records:
                oldest_record = oldest_records[0]
                oldest_period = oldest_record.get('Period')
                if oldest_period:
                    try:
                        if isinstance(oldest_period, str):
                            oldest_period_clean = oldest_period.split('.')[0].replace('Z', '')
                            oldest_date = datetime.fromisoformat(oldest_period_clean)
                        else:
                            oldest_date = oldest_period
                        
                        print(f"[OK] Самая ранняя дата: {oldest_date.strftime('%Y-%m-%d %H:%M:%S')}")
                    except Exception as e:
                        print(f"[WARNING] Не удалось распарсить дату: {e}")
                        print(f"  Значение: {oldest_period}")
            
            # Определяем самую новую дату
            if records:
                newest_record = records[0]
                newest_period = newest_record.get('Period')
                if newest_period:
                    try:
                        if isinstance(newest_period, str):
                            newest_period_clean = newest_period.split('.')[0].replace('Z', '')
                            newest_date = datetime.fromisoformat(newest_period_clean)
                        else:
                            newest_date = newest_period
                        
                        print(f"[OK] Самая новая дата: {newest_date.strftime('%Y-%m-%d %H:%M:%S')}")
                    except Exception as e:
                        print(f"[WARNING] Не удалось распарсить дату: {e}")
                        print(f"  Значение: {newest_period}")
            
            # Подсчитываем общее количество записей (приблизительно)
            print("\n[INFO] Подсчет общего количества записей...")
            params_count = {
                "$top": 1,
                "$count": "true"
            }
            
            try:
                response_count = await client.get(url, params=params_count)
                response_count.raise_for_status()
                data_count = response_count.json()
                total_count = data_count.get('@odata.count')
                if total_count is not None:
                    print(f"[OK] Всего записей в регистре: {total_count:,}")
            except Exception as e:
                print(f"[WARNING] Не удалось получить общее количество: {e}")
            
            # Анализируем доступные поля
            print("\n" + "=" * 80)
            print("ДОСТУПНЫЕ ПОЛЯ ДЛЯ ИМПОРТА")
            print("=" * 80)
            
            if records:
                record = records[0]
                available_fields = {
                    'Дата продажи': record.get('Period'),
                    'Сумма': record.get('Сумма') or record.get('СуммаИнт'),
                    'Количество': record.get('Количество') or record.get('КоличествоИнт'),
                    'Товар (ID)': record.get('Номенклатура_Key'),
                    'Магазин (ID)': record.get('Склад_Key'),
                    'Клиент (ID)': record.get('Контрагент_Key'),
                    'Документ (ID)': record.get('Recorder'),
                    'Тип документа': record.get('Recorder_Type'),
                    'Организация (ID)': record.get('Организация_Key'),
                    'Номер строки': record.get('LineNumber'),
                }
                
                print("\nПоля, которые можно импортировать:")
                for field_name, field_value in available_fields.items():
                    if field_value is not None:
                        value_str = str(field_value)
                        if len(value_str) > 50:
                            value_str = value_str[:50] + "..."
                        print(f"  ✓ {field_name}: {value_str}")
                    else:
                        print(f"  ✗ {field_name}: отсутствует")
            
            # Проверяем другие возможные регистры
            print("\n" + "=" * 80)
            print("ДРУГИЕ ВОЗМОЖНЫЕ РЕГИСТРЫ")
            print("=" * 80)
            
            other_endpoints = [
                "/AccumulationRegister_ПродажиПоДисконтнымКартам_RecordType",
                "/DocumentJournal_РозничныеПродажи",
                "/AccumulationRegister_Продажи_RecordType",
            ]
            
            for endpoint in other_endpoints:
                if endpoint == sales_endpoint:
                    continue
                
                test_url = f"{api_url.rstrip('/')}{endpoint}"
                try:
                    print(f"\n[INFO] Проверка {endpoint}...")
                    test_response = await client.get(test_url, params={"$top": 1})
                    if test_response.status_code == 200:
                        test_data = test_response.json()
                        test_records = test_data.get('value', [])
                        if test_records:
                            print(f"  [OK] Доступен, содержит данные")
                        else:
                            print(f"  [OK] Доступен, но пуст")
                    else:
                        print(f"  [SKIP] Недоступен (код {test_response.status_code})")
                except Exception as e:
                    print(f"  [SKIP] Ошибка: {str(e)[:100]}")
            
            print("\n" + "=" * 80)
            print("РЕКОМЕНДАЦИИ")
            print("=" * 80)
            print("\n1. Для импорта исторических данных используйте:")
            print(f"   - Регистр: {sales_endpoint}")
            if oldest_records:
                oldest_period = oldest_records[0].get('Period')
                if oldest_period:
                    try:
                        if isinstance(oldest_period, str):
                            oldest_period_clean = oldest_period.split('.')[0].replace('Z', '')
                            oldest_date = datetime.fromisoformat(oldest_period_clean)
                        else:
                            oldest_date = oldest_period
                        print(f"   - Начальная дата: {oldest_date.strftime('%Y-%m-%d')}")
                    except:
                        pass
            
            print("\n2. Для регулярной синхронизации используйте:")
            print("   - API endpoint: POST /api/analytics/1c-sales/sync")
            print("   - Параметры: period=month или start_date/end_date")
            
            print("\n3. Для ночной синхронизации:")
            print("   - Скрипт: backend/scripts/sync_sales_nightly.py")
            print("   - Настройте через cron или Task Scheduler")
            
        except httpx.HTTPStatusError as e:
            print(f"\n[ERROR] HTTP ошибка: {e.response.status_code}")
            print(f"Ответ: {e.response.text[:500]}")
        except Exception as e:
            print(f"\n[ERROR] Ошибка: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(check_1c_sales_availability())
