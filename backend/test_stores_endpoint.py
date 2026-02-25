"""
Проверка доступных endpoints для складов в 1С
"""
import asyncio
import sys
import codecs
import os
import httpx

if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

API_URL = os.getenv("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata")
API_TOKEN = os.getenv("ONEC_API_TOKEN", "b2RhdGEudXNlcjpvcGV4b2JvZQ==")


async def test_stores_endpoints():
    """Тестирование различных endpoints для складов"""
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    
    # Возможные endpoints для складов
    endpoints_to_test = [
        "/Catalog_Склады",
        "/Catalog_Stores",
        "/InformationRegister_Склады",
        "/Catalog_Склады_Key",
    ]
    
    print("=" * 80)
    print("ПРОВЕРКА ENDPOINTS ДЛЯ СКЛАДОВ В 1С")
    print("=" * 80)
    print()
    
    async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
        for endpoint in endpoints_to_test:
            url = f"{API_URL.rstrip('/')}{endpoint}"
            print(f"Тестируем: {endpoint}")
            try:
                response = await client.get(url, params={"$top": 1})
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("value", [])
                    if items:
                        print(f"  ✓ Успешно! Найдено записей: {len(items)}")
                        print(f"    Пример записи:")
                        first_item = items[0]
                        for key in sorted(first_item.keys())[:10]:
                            value = first_item[key]
                            if isinstance(value, dict):
                                value_str = f"{{объект: {value.get('Description', 'ссылка')}}}"
                            else:
                                value_str = str(value)
                                if len(value_str) > 50:
                                    value_str = value_str[:47] + "..."
                            print(f"      {key}: {value_str}")
                        print(f"\n  ✓ Рекомендуемый endpoint: {endpoint}\n")
                        return endpoint
                    else:
                        print(f"  ✗ Endpoint доступен, но пустой результат\n")
                else:
                    print(f"  ✗ HTTP {response.status_code}\n")
            except httpx.HTTPStatusError as e:
                print(f"  ✗ HTTP {e.response.status_code}: {e.response.text[:100]}\n")
            except Exception as e:
                print(f"  ✗ Ошибка: {str(e)[:100]}\n")
    
    print("✗ Ни один endpoint не доступен")
    return None


if __name__ == "__main__":
    result = asyncio.run(test_stores_endpoints())
    if result:
        print(f"\nИспользуйте endpoint: {result}")
