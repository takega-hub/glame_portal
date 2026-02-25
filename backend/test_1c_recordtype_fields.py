import asyncio
import sys
import codecs
import os
from typing import List

if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")


# Подставляем текущие переменные окружения из базы ПЕРЕД импортом сервиса
# Используем setdefault, но если значение пустое, перезаписываем
if not os.getenv("ONEC_API_URL"):
    os.environ["ONEC_API_URL"] = "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata"
if not os.getenv("ONEC_API_TOKEN"):
    os.environ["ONEC_API_TOKEN"] = "b2RhdGEudXNlcjpvcGV4b2JvZQ=="
if not os.getenv("ONEC_SALES_BY_CARD_ENDPOINT"):
    os.environ["ONEC_SALES_BY_CARD_ENDPOINT"] = "/AccumulationRegister_ПродажиПоДисконтнымКартам_RecordType"
if not os.getenv("ONEC_LOYALTY_ENDPOINT"):
    os.environ["ONEC_LOYALTY_ENDPOINT"] = "/AccumulationRegister_БонусныеБаллы_RecordType"
if not os.getenv("ONEC_LOYALTY_ACCRUAL_ENDPOINT"):
    os.environ["ONEC_LOYALTY_ACCRUAL_ENDPOINT"] = "/AccumulationRegister_НачисленияБонусныхБаллов_RecordType"

# Импортируем сервис ПОСЛЕ установки переменных окружения
from app.services.onec_customers_service import OneCCustomersService


async def _fetch_top_fields(endpoint: str, max_retries: int = 3) -> List[str]:
    service = OneCCustomersService()
    if not service.client:
        api_url = os.getenv("ONEC_API_URL", "не задан")
        raise RuntimeError(f"ONEC_API_URL is not set (текущее значение: {api_url})")

    url = f"{service.api_url.rstrip('/')}{endpoint}"
    params = {"$top": 1}
    
    last_exception = None
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                import asyncio
                wait_time = 2 ** attempt  # Exponential backoff
                print(f"    Повторная попытка {attempt + 1}/{max_retries} через {wait_time} сек...")
                await asyncio.sleep(wait_time)
            
            response = await service.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            records = data.get("value", [])
            if not records:
                await service.close()
                return []
            fields = list(records[0].keys())
            await service.close()
            return fields
        except Exception as e:
            last_exception = e
            if attempt == max_retries - 1:
                await service.close()
                raise
    await service.close()
    raise last_exception if last_exception else RuntimeError("Неизвестная ошибка")


async def test_connection(service: OneCCustomersService) -> bool:
    """Проверка подключения к базовому URL 1С"""
    if not service.client:
        return False
    try:
        # Пробуем запросить корневой endpoint OData
        response = await service.client.get(service.api_url.rstrip('/'))
        response.raise_for_status()
        await service.close()
        return True
    except Exception as e:
        print(f"  Ошибка подключения: {type(e).__name__}: {e}")
        await service.close()
        return False


async def main() -> None:
    targets = [
        "/AccumulationRegister_ПродажиПоДисконтнымКартам_RecordType",
        "/AccumulationRegister_БонусныеБаллы_RecordType",
        "/AccumulationRegister_НачисленияБонусныхБаллов_RecordType",
    ]

    print("=== Проверка полей RecordType (1С) ===")
    sys.stdout.flush()
    
    api_url = os.getenv("ONEC_API_URL", "не задан")
    print(f"ONEC_API_URL: {api_url}")
    sys.stdout.flush()
    
    # Проверка подключения
    print("\nПроверка подключения к 1С...")
    sys.stdout.flush()
    test_service = OneCCustomersService()
    if await test_connection(test_service):
        print("  ✓ Подключение успешно")
    else:
        print("  ✗ Не удалось подключиться к 1С. Проверьте сеть и настройки.")
        return
    sys.stdout.flush()
    
    for endpoint in targets:
        try:
            print(f"\nПроверка: {endpoint}")
            sys.stdout.flush()
            fields = await _fetch_top_fields(endpoint)
            if not fields:
                print("  Нет записей (value пустой)")
            else:
                print(f"  Найдено полей: {len(fields)}")
                print("  Поля:", ", ".join(fields))
            sys.stdout.flush()
        except Exception as exc:
            import traceback
            error_msg = str(exc) if str(exc) else type(exc).__name__
            print(f"  Ошибка: {error_msg}")
            if not str(exc):
                print(f"  Тип ошибки: {type(exc).__name__}")
                traceback.print_exc()
            sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(main())
