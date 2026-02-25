"""
Тестовый скрипт для проверки загрузки картинок товара
Тестируем на примере товара с артикулом 71136-S
"""
import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Добавляем путь к app
sys.path.insert(0, os.path.dirname(__file__))

# Загружаем .env
load_dotenv()

async def test_image_download():
    """Тест загрузки картинок для товара"""
    from app.database.connection import AsyncSessionLocal
    from app.models.product import Product
    from app.services.product_images_download_service import ProductImagesDownloadService
    from sqlalchemy import select
    
    # Тестовые данные из XML
    test_images = [
        "import_files/ec/ec2f3800bbf311f09138fa163e4cc04e_277b494ad0ed11f08e4dfa163e4cc04e.jpeg",
        "import_files/ec/ec2f3800bbf311f09138fa163e4cc04e_27b1896ad0ed11f08e4dfa163e4cc04e.jpeg"
    ]
    
    # Базовый URL (пример - нужно указать реальный URL от 1С)
    # Обычно это URL директории, где лежат XML файлы
    base_url = os.getenv("ONEC_XML_URL", "").rsplit('/', 1)[0] if os.getenv("ONEC_XML_URL") else None
    
    if not base_url:
        print("[WARNING] ONEC_XML_URL не указан в .env. Используем тестовый URL.")
        print("Укажите реальный базовый URL для тестирования.")
        base_url = input("Введите базовый URL (например, http://1c-server/export/): ").strip()
        if not base_url:
            print("[ERROR] Базовый URL не указан, тест отменен")
            return
    
    print(f"[INFO] Базовый URL: {base_url}")
    print(f"[INFO] Тестовые изображения: {test_images}")
    print()
    
    try:
        # Находим товар по артикулу
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Product).where(Product.article == "71136-S")
            )
            product = result.scalar_one_or_none()
            
            if not product:
                print(f"[ERROR] Товар с артикулом 71136-S не найден в базе данных")
                print("[INFO] Попробуйте сначала выполнить синхронизацию товаров из XML")
                return
            
            print(f"[OK] Найден товар: {product.name} (ID: {product.id}, артикул: {product.article})")
            print(f"[INFO] Текущие изображения товара: {product.images}")
            print()
            
            # Тестируем загрузку изображений
            async with ProductImagesDownloadService() as download_service:
                print("[INFO] Начинаем загрузку изображений...")
                print()
                
                downloaded_urls = await download_service.download_images_for_product(
                    test_images,
                    product_id=str(product.id),
                    max_concurrent=2,
                    base_url=base_url
                )
                
                if downloaded_urls:
                    print(f"[OK] Успешно загружено {len(downloaded_urls)} изображений:")
                    for i, url in enumerate(downloaded_urls, 1):
                        print(f"  {i}. {url}")
                    
                    # Обновляем изображения товара
                    product.images = downloaded_urls
                    await db.commit()
                    print()
                    print(f"[OK] Изображения товара обновлены в базе данных")
                else:
                    print("[WARNING] Не удалось загрузить изображения")
                    print("[INFO] Проверьте:")
                    print("  1. Доступность базового URL")
                    print("  2. Правильность путей к изображениям")
                    print("  3. Логи сервера для деталей ошибок")
        
    except Exception as e:
        print(f"[ERROR] Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_image_download())
