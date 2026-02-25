"""
Тестовый скрипт для проверки парсинга групп каталога из CommerceML XML
"""
import asyncio
import sys
from app.services.commerceml_xml_service import CommerceMLXMLService

# Тестовый XML фрагмент с группами
TEST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<КоммерческаяИнформация xmlns="urn:1C.ru:commerceml_210">
    <Каталог>
        <Группы>
            <Группа>
                <Ид>b1b9a380-ba4b-11f0-836e-fa163e4cc04e</Ид>
                <Наименование>AGafi</Наименование>
            </Группа>
            <Группа>
                <Ид>95ce49cc-b27c-11f0-9252-fa163e4cc04e</Ид>
                <Наименование>SALE</Наименование>
            </Группа>
            <Группа>
                <Ид>parent-group-id</Ид>
                <Наименование>Родительская группа</Наименование>
                <Группа>
                    <Ид>child-group-id</Ид>
                </Группа>
            </Группа>
        </Группы>
    </Каталог>
</КоммерческаяИнформация>
"""


async def test_groups_parsing():
    """Тестируем парсинг групп из XML"""
    
    print("\n=== ТЕСТ ПАРСИНГА ГРУПП ИЗ XML ===\n")
    
    service = CommerceMLXMLService()
    
    # Парсим XML
    xml_bytes = TEST_XML.encode('utf-8')
    groups = service.parse_groups(xml_bytes)
    
    print(f"Найдено групп: {len(groups)}\n")
    
    for idx, group in enumerate(groups, 1):
        print(f"Группа {idx}:")
        print(f"  - Ид: {group.get('external_id')}")
        print(f"  - Наименование: {group.get('name')}")
        if group.get('parent_id'):
            print(f"  - Родитель: {group.get('parent_id')}")
        print()
    
    return groups


async def test_with_real_url():
    """Тестируем с реальным URL"""
    xml_url = "https://s22b2e4d6.fastvps-server.com/1c_exchange/uploaded/import.xml"
    
    print("\n=== ТЕСТ С РЕАЛЬНЫМ XML ИЗ 1С ===\n")
    print(f"URL: {xml_url}\n")
    
    async with CommerceMLXMLService() as service:
        try:
            # Скачиваем XML
            xml_content = await service.download_xml_from_url(xml_url)
            print(f"OK - XML downloaded ({len(xml_content)} bytes)\n")
            
            # Парсим группы
            groups = service.parse_groups(xml_content)
            print(f"OK - Found groups: {len(groups)}\n")
            
            if groups:
                print("Первые 10 групп:")
                for idx, group in enumerate(groups[:10], 1):
                    print(f"  {idx}. {group.get('name')} (ID: {group.get('external_id')})")
                    if group.get('parent_id'):
                        print(f"     └─ Родитель: {group.get('parent_id')}")
                print()
            
            # Парсим товары
            products = service.parse_commerceml_xml(xml_content)
            print(f"OK - Found products: {len(products)}\n")
            
            if products:
                print("Первые 3 товара:")
                for idx, product in enumerate(products[:3], 1):
                    print(f"  {idx}. {product.get('name')}")
                    print(f"     - Артикул: {product.get('article')}")
                    print(f"     - ID: {product.get('id')}")
                    if product.get('category_external_id'):
                        print(f"     - Группа ID: {product.get('category_external_id')}")
                    print()
            
            return {"groups": groups, "products": products}
            
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            return None


if __name__ == "__main__":
    # Тест 1: Парсинг тестового XML
    groups = asyncio.run(test_groups_parsing())
    
    # Тест 2: Загрузка реального XML из 1С
    if len(sys.argv) > 1 and sys.argv[1] == "--real":
        result = asyncio.run(test_with_real_url())
        if result:
            print(f"\nВСЕГО: {len(result['groups'])} групп, {len(result['products'])} товаров")
    else:
        print("\nЧтобы протестировать с реальным XML из 1С, запустите:")
        print("  python backend/test_xml_groups_parse.py --real")
