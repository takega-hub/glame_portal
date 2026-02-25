"""
Тест загрузки изображений для товара 71136-S
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from app.models.product import Product
from app.services.product_images_download_service import ProductImagesDownloadService

# Добавляем путь к app
sys.path.insert(0, os.path.dirname(__file__))

# Загружаем .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    print("[ERROR] DATABASE_URL not found")
    sys.exit(1)

async def test_image_download():
    """Тест загрузки изображений"""
    try:
        engine = create_async_engine(DATABASE_URL, echo=False)
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as db:
            # Ищем товар по артикулу
            print("=" * 80)
            print("ПОИСК ТОВАРА С АРТИКУЛОМ 71136-S")
            print("=" * 80)
            print()
            
            result = await db.execute(
                select(Product).where(Product.article == "71136-S")
            )
            product = result.scalar_one_or_none()
            
            if not product:
                print("Товар с артикулом 71136-S не найден в базе")
                return
            
            print(f"Найден товар: {product.name}")
            print(f"  ID: {product.id}")
            print(f"  Артикул: {product.article}")
            print(f"  External ID: {product.external_id}")
            print(f"  Текущие изображения: {product.images if product.images else 'Нет'}")
            print()
            
            # Проверяем, есть ли изображения в specifications или sync_metadata
            if product.specifications:
                print(f"Specifications: {product.specifications}")
            if product.sync_metadata:
                print(f"Sync metadata: {product.sync_metadata}")
            print()
            
            # Запускаем загрузку изображений
            print("=" * 80)
            print("ЗАГРУЗКА ИЗОБРАЖЕНИЙ")
            print("=" * 80)
            print()
            
            # Получаем base_url из переменных окружения
            base_url = os.getenv("ONEC_XML_BASE_URL", "")
            if not base_url:
                # Пытаемся извлечь из ONEC_XML_IMPORT_URL
                import_url = os.getenv("ONEC_XML_IMPORT_URL", "")
                if import_url:
                    from urllib.parse import urlparse
                    parsed = urlparse(import_url)
                    base_url = f"{parsed.scheme}://{parsed.netloc}"
            
            print(f"Base URL для изображений: {base_url}")
            print()
            
            download_service = ProductImagesDownloadService(db, base_url=base_url)
            
            # Загружаем изображения для товара
            downloaded_images = await download_service.download_images_for_product(product)
            
            print(f"Загружено изображений: {len(downloaded_images)}")
            for img in downloaded_images:
                print(f"  - {img}")
            print()
            
            # Обновляем товар в базе
            if downloaded_images:
                product.images = downloaded_images
                await db.commit()
                print("Изображения сохранены в базу данных")
            else:
                print("Изображения не были загружены")
            
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test_image_download())
