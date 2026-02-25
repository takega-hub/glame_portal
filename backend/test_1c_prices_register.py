"""
Проверка регистра цен в 1С
"""
import asyncio
import sys
import codecs
import os
import httpx
import json

if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

API_URL = os.getenv("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata")
API_TOKEN = os.getenv("ONEC_API_TOKEN", "b2RhdGEudXNlcjpvcGV4b2JvZQ==")


async def test_prices_register():
    """Проверка регистра цен в 1С"""
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    
    print("=" * 80)
    print("ПРОВЕРКА РЕГИСТРА ЦЕН В 1С")
    print("=" * 80)
    print()
    
    async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
        # Возможные регистры цен
        price_registers = [
            "/InformationRegister_ЦеныНоменклатуры",
            "/InformationRegister_ЦеныНоменклатуры_RecordType",
            "/InformationRegister_Цены",
            "/InformationRegister_РозничныеЦены",
        ]
        
        for register in price_registers:
            try:
                url = f"{API_URL.rstrip('/')}{register}"
                print(f"Проверяем: {register}")
                response = await client.get(url, params={"$top": 5})
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("value", [])
                    if items:
                        print(f"  ✓ Найден регистр цен!")
                        print(f"  Пример записи:")
                        print(json.dumps(items[0], ensure_ascii=False, indent=2, default=str)[:500])
                        print()
                        return register
                    else:
                        print(f"  Регистр пуст\n")
                else:
                    print(f"  HTTP {response.status_code}\n")
            except Exception as e:
                print(f"  Ошибка: {str(e)[:100]}\n")
        
        print("✗ Регистр цен не найден")
        return None


if __name__ == "__main__":
    asyncio.run(test_prices_register())
