"""
Проверка групп/разделов каталога в 1С
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


async def check_groups():
    """Проверка групп/разделов каталога"""
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    
    print("=" * 100)
    print("ПРОВЕРКА ГРУПП/РАЗДЕЛОВ КАТАЛОГА В 1С")
    print("=" * 100)
    print()
    
    async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
        url = f"{API_URL.rstrip('/')}/Catalog_Номенклатура"
        
        # Получаем первые 100 записей
        response = await client.get(url, params={"$top": 100})
        response.raise_for_status()
        data = response.json()
        items = data.get("value", [])
        
        print(f"Всего получено записей: {len(items)}\n")
        
        # Анализируем поля для определения групп
        groups = []
        products = []
        
        for item in items:
            is_folder = item.get("IsFolder", False)
            code = item.get("Code", "")
            description = item.get("Description", "")
            parent_key = item.get("Parent_Key")
            article = item.get("Артикул")
            
            if is_folder:
                groups.append({
                    "Code": code,
                    "Description": description,
                    "Parent_Key": parent_key,
                    "Ref_Key": item.get("Ref_Key"),
                    "IsFolder": True,
                })
            else:
                products.append({
                    "Code": code,
                    "Description": description,
                    "Артикул": article,
                    "Parent_Key": parent_key,
                    "Ref_Key": item.get("Ref_Key"),
                    "IsFolder": False,
                })
        
        print(f"Найдено групп (IsFolder=True): {len(groups)}")
        print(f"Найдено товаров (IsFolder=False): {len(products)}\n")
        
        if groups:
            print("=" * 100)
            print("ПРИМЕРЫ ГРУПП:")
            print("=" * 100)
            for i, group in enumerate(groups[:10], 1):
                print(f"\n{i}. {group['Description']} (Code: {group['Code']})")
                print(f"   Ref_Key: {group['Ref_Key']}")
                print(f"   Parent_Key: {group['Parent_Key']}")
        
        if products:
            print("\n" + "=" * 100)
            print("ПРИМЕРЫ ТОВАРОВ:")
            print("=" * 100)
            for i, product in enumerate(products[:10], 1):
                print(f"\n{i}. {product['Description']} (Code: {product['Code']})")
                print(f"   Артикул: {product['Артикул']}")
                print(f"   Ref_Key: {product['Ref_Key']}")
                print(f"   Parent_Key: {product['Parent_Key']}")
        
        # Проверяем структуру иерархии
        print("\n" + "=" * 100)
        print("АНАЛИЗ ИЕРАРХИИ:")
        print("=" * 100)
        
        # Находим группы верхнего уровня (без Parent_Key или с пустым Parent_Key)
        top_level_groups = [
            g for g in groups
            if not g.get("Parent_Key") or g.get("Parent_Key") == "00000000-0000-0000-0000-000000000000"
        ]
        
        print(f"\nГруппы верхнего уровня: {len(top_level_groups)}")
        for group in top_level_groups[:5]:
            print(f"  - {group['Description']} ({group['Code']})")
        
        # Находим товары, которые могут быть в группах
        products_in_groups = [
            p for p in products
            if p.get("Parent_Key") and p.get("Parent_Key") != "00000000-0000-0000-0000-000000000000"
        ]
        
        print(f"\nТовары с Parent_Key (возможно, в группах): {len(products_in_groups)}")
        
        # Проверяем, есть ли поле для категории/группы
        if products:
            example_product = products[0]
            print("\n" + "=" * 100)
            print("ПОЛЯ ТОВАРА ДЛЯ ОПРЕДЕЛЕНИЯ ГРУППЫ:")
            print("=" * 100)
            
            # Получаем полную информацию о товаре
            product_ref = example_product.get("Ref_Key")
            if product_ref:
                try:
                    product_url = f"{url}(guid'{product_ref}')"
                    product_response = await client.get(product_url)
                    if product_response.status_code == 200:
                        product_data = product_response.json()
                        
                        # Ищем поля, связанные с группами/категориями
                        group_related_fields = {}
                        for key, value in product_data.items():
                            key_lower = key.lower()
                            if any(keyword in key_lower for keyword in ["группа", "group", "категория", "category", "родитель", "parent"]):
                                if value is not None and value != "":
                                    group_related_fields[key] = value
                        
                        if group_related_fields:
                            print("\nНайденные поля, связанные с группами:")
                            for key, value in group_related_fields.items():
                                if isinstance(value, dict):
                                    print(f"  {key}: {value.get('Description', value)}")
                                else:
                                    print(f"  {key}: {value}")
                        else:
                            print("\nПоля, связанные с группами, не найдены в основных полях")
                except Exception as e:
                    print(f"\nОшибка при получении полной информации о товаре: {e}")
        
        # Сохраняем результаты
        result = {
            "groups": groups[:20],
            "products": products[:20],
            "top_level_groups": top_level_groups[:10],
            "products_in_groups": len(products_in_groups),
        }
        
        with open("1c_groups_analysis.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"\n✓ Результаты сохранены в: 1c_groups_analysis.json")


if __name__ == "__main__":
    asyncio.run(check_groups())
