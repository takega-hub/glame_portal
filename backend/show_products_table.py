"""
Показать таблицу товаров из 1С с основными полями
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


async def show_products_table():
    """Показать таблицу товаров"""
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    
    url = f"{API_URL.rstrip('/')}/Catalog_Номенклатура"
    params = {"$top": 500}  # Больше товаров для поиска примеров
    
    try:
        async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
            print("=" * 120)
            print("ТАБЛИЦА ТОВАРОВ ИЗ 1С (Catalog_Номенклатура)")
            print("=" * 120)
            print()
            
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            items = data.get("value", [])
            
            if not items:
                print("✗ Нет товаров")
                return
            
            # Фильтруем только товары (не папки)
            all_products = [item for item in items if not item.get("IsFolder", False)]
            
            # Ищем товары с заполненным артикулом
            products_with_article = [item for item in all_products if item.get("Артикул")]
            
            # Показываем товары с артикулом, если есть
            if products_with_article:
                products = products_with_article
            else:
                products = all_products
            
            print(f"Показано товаров: {len(products)}\n")
            print("=" * 120)
            print(f"{'Code (внутр.код 1С)':<20} {'Артикул':<20} {'Название':<40} {'Ref_Key (UUID)':<40}")
            print("=" * 120)
            
            for item in products[:15]:  # Показываем первые 15
                code = item.get("Code", "")[:18]
                article = str(item.get("Артикул", ""))[:18]
                desc = item.get("Description", "")[:38]
                ref_key = item.get("Ref_Key", "")[:38]
                
                print(f"{code:<20} {article:<20} {desc:<40} {ref_key:<40}")
            
            print("=" * 120)
            print()
            
            # Показываем детали первого товара с артикулом
            if products:
                first = products[0]
                print("ДЕТАЛЬНАЯ ИНФОРМАЦИЯ О ПЕРВОМ ТОВАРЕ:")
                print("=" * 120)
                print()
                
                print(f"Code (внутренний код 1С):     {first.get('Code')}")
                print(f"Артикул (реальный артикул):   {first.get('Артикул')}")
                print(f"Ref_Key (UUID в 1С):          {first.get('Ref_Key')}")
                print(f"Description (название):       {first.get('Description')}")
                print(f"НаименованиеПолное:           {first.get('НаименованиеПолное')}")
                print()
                
                # Показываем все заполненные поля
                filled = {k: v for k, v in first.items() if v is not None and v != "" and not isinstance(v, (list, dict)) or (isinstance(v, list) and len(v) > 0) or (isinstance(v, dict) and len(v) > 0)}
                
                print("ВСЕ ЗАПОЛНЕННЫЕ ПОЛЯ:")
                print("-" * 120)
                for key in sorted(filled.keys()):
                    value = filled[key]
                    if isinstance(value, dict):
                        value_str = f"{{объект: {value.get('Description', 'ссылка')}}}"
                    elif isinstance(value, list):
                        value_str = f"[массив: {len(value)} элементов]"
                    else:
                        value_str = str(value)
                        if len(value_str) > 60:
                            value_str = value_str[:57] + "..."
                    print(f"  {key:<50} = {value_str}")
            
    except Exception as e:
        print(f"✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(show_products_table())
