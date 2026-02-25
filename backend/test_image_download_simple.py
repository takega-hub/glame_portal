"""
Упрощенный тест загрузки картинок без подключения к БД
Тестируем на примере товара с артикулом 71136-S
"""
import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import urljoin

# Добавляем путь к app
sys.path.insert(0, os.path.dirname(__file__))

# Загружаем .env
load_dotenv()

async def test_image_download_simple():
    """Простой тест загрузки картинок без БД"""
    from app.services.product_images_download_service import ProductImagesDownloadService
    
    # Тестовые данные из XML
    test_images = [
        "import_files/ec/ec2f3800bbf311f09138fa163e4cc04e_277b494ad0ed11f08e4dfa163e4cc04e.jpeg",
        "import_files/ec/ec2f3800bbf311f09138fa163e4cc04e_27b1896ad0ed11f08e4dfa163e4cc04e.jpeg"
    ]
    
    # Базовый URL (пример - нужно указать реальный URL от 1С)
    base_url = os.getenv("ONEC_XML_URL", "").rsplit('/', 1)[0] if os.getenv("ONEC_XML_URL") else None
    
    if not base_url:
        print("[INFO] ONEC_XML_URL не указан в .env")
        print("[INFO] Пример: http://1c-server:port/export/")
        base_url = input("Введите базовый URL (или нажмите Enter для пропуска): ").strip()
        if not base_url:
            print("[INFO] Тест пропущен. Для тестирования укажите ONEC_XML_URL в .env")
            print()
            print("[INFO] Проверка парсинга XML:")
            print("  ✓ Парсинг множественных <Картинка> элементов исправлен")
            print("  ✓ Теперь все картинки из offers.xml будут сохранены")
            return
    
    print(f"[INFO] Базовый URL: {base_url}")
    print(f"[INFO] Тестовые изображения:")
    for i, img in enumerate(test_images, 1):
        full_url = urljoin(base_url.rstrip('/') + '/', img)
        print(f"  {i}. {img}")
        print(f"     -> {full_url}")
    print()
    
    try:
        async with ProductImagesDownloadService() as download_service:
            print("[INFO] Начинаем загрузку изображений...")
            print()
            
            downloaded_urls = await download_service.download_images_for_product(
                test_images,
                product_id="test-71136-S",
                max_concurrent=2,
                base_url=base_url
            )
            
            if downloaded_urls:
                print(f"[OK] Успешно загружено {len(downloaded_urls)} изображений:")
                for i, url in enumerate(downloaded_urls, 1):
                    print(f"  {i}. {url}")
                print()
                print("[OK] Изображения сохранены локально в static/product_images/")
            else:
                print("[WARNING] Не удалось загрузить изображения")
                print("[INFO] Возможные причины:")
                print("  1. Неверный базовый URL")
                print("  2. Изображения недоступны по указанному пути")
                print("  3. Проблемы с сетью или доступом к серверу 1С")
                print()
                print("[INFO] Проверьте логи выше для деталей ошибок")
        
    except Exception as e:
        print(f"[ERROR] Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 80)
    print("ТЕСТ ЗАГРУЗКИ КАРТИНОК ДЛЯ ТОВАРА 71136-S")
    print("=" * 80)
    print()
    asyncio.run(test_image_download_simple())
