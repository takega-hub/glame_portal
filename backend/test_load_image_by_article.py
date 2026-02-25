"""
Тестовый скрипт для загрузки изображения товара по артикулу.
Проверяет весь путь: поиск товара в 1С -> поиск файлов -> скачивание изображения.
"""
import asyncio
import sys
import os
import codecs
import logging
from pathlib import Path

# Настройка кодировки для Windows
if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

# Включаем DEBUG логирование
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(message)s')

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import httpx
from app.services.onec_images_service import OneCImagesService
from app.services.yml_images_service import YMLImagesService


async def find_product_in_1c(article: str, api_url: str, api_token: str):
    """Найти товар в 1С по артикулу"""
    headers = {"Accept": "application/json"}
    if api_token:
        if api_token.startswith("Basic "):
            headers["Authorization"] = api_token
        else:
            headers["Authorization"] = f"Basic {api_token}"
    
    async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
        # Ищем в Catalog_ХарактеристикиНоменклатуры (приоритет - там артикулы характеристик)
        url = f"{api_url.rstrip('/')}/Catalog_ХарактеристикиНоменклатуры"
        params = {
            "$filter": f"Артикул eq '{article}'",
            "$top": 10
        }
        
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            items = data.get("value", [])
            
            if items:
                # Берем первый найденный
                item = items[0]
                return {
                    "ref_key": item.get("Ref_Key"),
                    "code": item.get("Code"),
                    "article": item.get("Артикул"),
                    "name": item.get("Description"),
                    "parent_key": item.get("Parent_Key"),
                    "is_characteristic": True
                }
        except Exception as e:
            print(f"   [WARN] Ошибка поиска в характеристиках: {e}")
        
        # Если не нашли точное совпадение, пробуем частичное (например, "170018-g" -> "170018")
        article_base = article.split("-")[0] if "-" in article else article
        if article_base != article:
            print(f"   [INFO] Пробуем поиск по базовому артикулу '{article_base}'...")
            url = f"{api_url.rstrip('/')}/Catalog_ХарактеристикиНоменклатуры"
            params = {
                "$filter": f"startswith(Артикул, '{article_base}')",
                "$top": 10
            }
            
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                items = data.get("value", [])
                
                # Ищем точное совпадение или частичное
                for item in items:
                    item_article = item.get("Артикул", "")
                    if article.lower() in item_article.lower() or item_article.lower().startswith(article_base.lower()):
                        return {
                            "ref_key": item.get("Ref_Key"),
                            "code": item.get("Code"),
                            "article": item.get("Артикул"),
                            "name": item.get("Description"),
                            "parent_key": item.get("Parent_Key"),
                            "is_characteristic": True
                        }
            except Exception as e:
                print(f"   [WARN] Ошибка частичного поиска в характеристиках: {e}")
        
        # Если не нашли в характеристиках, ищем в основной номенклатуре
        url = f"{api_url.rstrip('/')}/Catalog_Номенклатура"
        params = {
            "$filter": f"Артикул eq '{article}'",
            "$top": 1
        }
        
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            items = data.get("value", [])
            
            if items:
                item = items[0]
                return {
                    "ref_key": item.get("Ref_Key"),
                    "code": item.get("Code"),
                    "article": item.get("Артикул"),
                    "name": item.get("Description"),
                    "parent_key": item.get("Parent_Key"),
                    "is_characteristic": False
                }
        except Exception as e:
            print(f"   [WARN] Ошибка поиска в номенклатуре: {e}")
        
        # Пробуем найти основную карточку по базовому артикулу и затем ищем характеристики
        if article_base != article:
            print(f"   [INFO] Ищем основную карточку по артикулу '{article_base}' и затем характеристики...")
            url = f"{api_url.rstrip('/')}/Catalog_Номенклатура"
            params = {
                "$filter": f"Артикул eq '{article_base}'",
                "$top": 1
            }
            
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                main_items = data.get("value", [])
                
                if main_items:
                    main_item = main_items[0]
                    main_ref_key = main_item.get("Ref_Key")
                    
                    # Ищем характеристики для этой основной карточки
                    url = f"{api_url.rstrip('/')}/Catalog_ХарактеристикиНоменклатуры"
                    params = {
                        "$filter": f"Parent_Key eq guid'{main_ref_key}'",
                        "$top": 50
                    }
                    
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                    char_items = data.get("value", [])
                    
                    # Ищем характеристику с нужным артикулом
                    for char_item in char_items:
                        char_article = char_item.get("Артикул", "")
                        if article.lower() in char_article.lower():
                            return {
                                "ref_key": char_item.get("Ref_Key"),
                                "code": char_item.get("Code"),
                                "article": char_item.get("Артикул"),
                                "name": char_item.get("Description"),
                                "parent_key": char_item.get("Parent_Key"),
                                "is_characteristic": True
                            }
            except Exception as e:
                print(f"   [WARN] Ошибка поиска через основную карточку: {e}")
        
        return None


async def test_load_image_by_article(article: str):
    """Тестовая загрузка изображения по артикулу"""
    
    print("=" * 100)
    print(f"ТЕСТ: Загрузка изображения для артикула '{article}'")
    print("=" * 100)
    
    # Получаем настройки из переменных окружения
    api_url = os.getenv("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata")
    api_token = os.getenv("ONEC_API_TOKEN", "b2RhdGEudXNlcjpvcGV4b2JvZQ==")
    
    # Шаг 1: Найти товар в 1С по артикулу
    print("\n[ШАГ 1] Поиск товара в 1С по артикулу...")
    product_info = await find_product_in_1c(article, api_url, api_token)
    
    if not product_info:
        print(f"[X] Товар с артикулом '{article}' не найден в 1С")
        print("\n[ШАГ 1.1] Пробуем поиск в YML...")
        async with YMLImagesService() as yml_service:
            yml_images = await yml_service.get_images_by_article(article)
            if yml_images:
                print(f"[OK] Найдено изображений в YML: {len(yml_images)}")
                for i, img_url in enumerate(yml_images, 1):
                    print(f"   Изображение {i}: {img_url}")
            else:
                print(f"[X] Изображения не найдены ни в 1С, ни в YML")
        return
    
    print(f"[OK] Товар найден в 1С:")
    print(f"   - Ref_Key: {product_info['ref_key']}")
    print(f"   - Code: {product_info['code']}")
    print(f"   - Артикул: {product_info['article']}")
    print(f"   - Название: {product_info['name']}")
    print(f"   - Тип: {'Характеристика' if product_info['is_characteristic'] else 'Основная карточка'}")
    if product_info['parent_key']:
        print(f"   - Parent_Key: {product_info['parent_key']}")
    
    product_ref_key = product_info['ref_key']
    characteristic_ref_key = product_info['ref_key'] if product_info['is_characteristic'] else None
    main_product_ref_key = product_info['parent_key'] if product_info['is_characteristic'] else product_info['ref_key']
    
    # Шаг 2: Поиск присоединенных файлов в 1С
    print("\n[ШАГ 2] Поиск присоединенных файлов в 1С...")
    
    async with OneCImagesService(api_url=api_url, api_token=api_token) as images_service:
        # 2.1: Поиск файлов для характеристики (если это характеристика)
        if characteristic_ref_key:
            print(f"\n[ШАГ 2.1] Поиск файлов для характеристики (Ref_Key: {characteristic_ref_key})...")
            char_files = await images_service.fetch_attached_files(
                characteristic_ref_key,
                collection="Catalog_ХарактеристикиНоменклатурыПрисоединенныеФайлы"
            )
            print(f"   Найдено файлов для характеристики: {len(char_files)}")
            for i, file_meta in enumerate(char_files, 1):
                print(f"   Файл {i}:")
                print(f"     - Ref_Key: {file_meta.get('Ref_Key')}")
                print(f"     - Описание: {file_meta.get('Description', 'без описания')}")
                print(f"     - Размер: {file_meta.get('Размер', 'неизвестно')} байт")
                print(f"     - Расширение: {file_meta.get('Расширение', 'неизвестно')}")
                print(f"     - Индекс картинки: {file_meta.get('ИндексКартинки', 'неизвестно')}")
        
        # 2.2: Поиск файлов для основного товара
        if main_product_ref_key:
            print(f"\n[ШАГ 2.2] Поиск файлов для основного товара (Ref_Key: {main_product_ref_key})...")
            product_files = await images_service.fetch_attached_files(
                main_product_ref_key,
                collection="Catalog_НоменклатураПрисоединенныеФайлы"
            )
        else:
            print(f"\n[ШАГ 2.2] Пропуск поиска файлов для основного товара (нет Parent_Key)")
            product_files = []
        print(f"   Найдено файлов для товара: {len(product_files)}")
        for i, file_meta in enumerate(product_files, 1):
            print(f"   Файл {i}:")
            print(f"     - Ref_Key: {file_meta.get('Ref_Key')}")
            print(f"     - Описание: {file_meta.get('Description', 'без описания')}")
            print(f"     - Размер: {file_meta.get('Размер', 'неизвестно')} байт")
            print(f"     - Расширение: {file_meta.get('Расширение', 'неизвестно')}")
            print(f"     - Индекс картинки: {file_meta.get('ИндексКартинки', 'неизвестно')}")
        
        # Шаг 3: Скачивание изображений
        print("\n[ШАГ 3] Скачивание изображений...")
        
        all_files = []
        if characteristic_ref_key:
            all_files.extend([(f, "характеристика") for f in char_files])
        all_files.extend([(f, "товар") for f in product_files])
        
        downloaded_images = []
        
        for file_meta, source_type in all_files:
            file_ref = file_meta.get("Ref_Key")
            if not file_ref:
                continue
            
            print(f"\n   Скачивание файла {file_ref} ({source_type})...")
            collection = "Catalog_ХарактеристикиНоменклатурыПрисоединенныеФайлы" if source_type == "характеристика" else "Catalog_НоменклатураПрисоединенныеФайлы"
            
            print(f"      Пробуем скачать файл через download_file_from_storage...")
            file_data = await images_service.download_file_from_storage(
                file_ref,
                collection=collection
            )
            
            if file_data:
                print(f"   [OK] Файл успешно скачан: {len(file_data)} байт")
                
                # Конвертируем в base64 для отображения
                import base64
                extension = file_meta.get("Расширение", "jpeg").lower()
                mime_type = f"image/{extension}" if extension in ["jpeg", "jpg", "png", "gif", "webp"] else "image/jpeg"
                base64_data = base64.b64encode(file_data).decode("utf-8")
                data_url_preview = f"data:{mime_type};base64,{base64_data[:100]}..."  # Первые 100 символов для примера
                
                downloaded_images.append({
                    "source": source_type,
                    "file_ref": file_ref,
                    "description": file_meta.get("Description", "без описания"),
                    "size": len(file_data),
                    "extension": extension,
                    "data_url_preview": data_url_preview,
                })
                
                print(f"   📸 Изображение: {file_meta.get('Description', 'без описания')}")
                print(f"   📏 Размер: {len(file_data)} байт")
                print(f"   🎨 Формат: {mime_type}")
                print(f"   🔗 Data URL (первые 100 символов): {data_url_preview}")
            else:
                print(f"   [X] Не удалось скачать файл")
        
        # Шаг 4: Использование готового метода get_images_for_product
        print("\n[ШАГ 4] Использование метода get_images_for_product...")
        images = await images_service.get_images_for_product(
            product_ref_key=main_product_ref_key,
            characteristic_ref_key=characteristic_ref_key
        )
        print(f"   [OK] Получено изображений: {len(images)}")
        for i, img in enumerate(images, 1):
            preview = img[:150] + "..." if len(img) > 150 else img
            print(f"   Изображение {i}: {preview} (data URL, {len(img)} символов)")
    
    # Шаг 5: Поиск в YML (если в 1С не нашли)
    print("\n[ШАГ 5] Поиск изображений в YML (резервный источник)...")
    async with YMLImagesService() as yml_service:
        yml_images = await yml_service.get_images_by_article(article)
        if yml_images:
            print(f"   ✅ Найдено изображений в YML: {len(yml_images)}")
            for i, img_url in enumerate(yml_images, 1):
                print(f"   Изображение {i}: {img_url}")
        else:
            print(f"   ⚠️  Изображения не найдены в YML для артикула '{article}'")
    
    # Итоги
    print("\n" + "=" * 100)
    print("ИТОГИ:")
    print("=" * 100)
    print(f"✅ Товар найден в 1С")
    print(f"✅ Ref_Key: {product_ref_key}")
    if characteristic_ref_key:
        print(f"✅ Ref_Key характеристики: {characteristic_ref_key}")
    if downloaded_images:
        print(f"✅ Скачано изображений из 1С: {len(downloaded_images)}")
        for img in downloaded_images:
            print(f"   - {img['description']} ({img['source']}): {img['size']} байт, {img['extension']}")
    else:
        print(f"⚠️  Изображения не найдены в 1С")
    
    if yml_images:
        print(f"✅ Найдено изображений в YML: {len(yml_images)}")
    else:
        print(f"⚠️  Изображения не найдены в YML")


async def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Тест загрузки изображения по артикулу")
    parser.add_argument("--article", default="170018-g", help="Артикул товара")
    args = parser.parse_args()
    
    try:
        await test_load_image_by_article(args.article)
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Закрываем соединения
        pass


if __name__ == "__main__":
    asyncio.run(main())
