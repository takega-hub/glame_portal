"""
Проверка полей цен в 1С
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


async def test_price_fields():
    """Проверка полей цен в 1С"""
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    
    print("=" * 80)
    print("ПРОВЕРКА ПОЛЕЙ ЦЕН В 1С")
    print("=" * 80)
    print()
    
    async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
        url = f"{API_URL.rstrip('/')}/Catalog_Номенклатура"
        params = {"$top": 20}
        
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            items = data.get("value", [])
            
            print(f"Получено товаров: {len(items)}\n")
            
            # Ищем товары с ценами
            price_fields = set()
            for item in items:
                for key, value in item.items():
                    if any(keyword in key.lower() for keyword in ["цена", "price", "стоимость", "cost"]):
                        if value is not None and value != "":
                            price_fields.add(key)
            
            print("Найденные поля с ценами:")
            for field in sorted(price_fields):
                print(f"  - {field}")
            print()
            
            # Показываем примеры товаров с ценами
            print("Примеры товаров с ценами:")
            print("-" * 80)
            for item in items[:5]:
                code = item.get("Code", "")
                name = item.get("Description", "")[:50]
                print(f"\nCode: {code}, Name: {name}")
                
                for field in sorted(price_fields):
                    value = item.get(field)
                    if value is not None and value != "":
                        print(f"  {field}: {value}")
                
                # Проверяем артикул и Parent_Key
                article = item.get("Артикул")
                parent_key = item.get("Parent_Key")
                if article:
                    print(f"  Артикул: {article}")
                if parent_key and parent_key != "00000000-0000-0000-0000-000000000000":
                    print(f"  Parent_Key (характеристика!): {parent_key}")
            
            # Сохраняем пример товара
            if items:
                with open("product_with_prices.json", "w", encoding="utf-8") as f:
                    json.dump(items[0], f, ensure_ascii=False, indent=2, default=str)
                print(f"\n✓ Пример товара сохранен в: product_with_prices.json")
                
        except Exception as e:
            print(f"✗ Ошибка: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_price_fields())
