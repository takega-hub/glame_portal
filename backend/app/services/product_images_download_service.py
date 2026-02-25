"""
Сервис для фонового скачивания изображений товаров из URL.
Скачивает изображения из XML и сохраняет их локально или в S3.
"""
import httpx
import logging
import os
import hashlib
from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse, urljoin
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

# Настройки хранилища
STORAGE_TYPE = os.getenv("STORAGE_TYPE", "local")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")

# Локальное хранилище (папка static в backend, откуда раздается /static)
BACKEND_ROOT = Path(__file__).resolve().parents[2]
LOCAL_STORAGE_PATH = BACKEND_ROOT / "static" / "product_images"
LOCAL_STORAGE_PATH.mkdir(parents=True, exist_ok=True)


class ProductImagesDownloadService:
    """Сервис для скачивания и сохранения изображений товаров"""
    
    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None
        self.storage_type = STORAGE_TYPE
        self.s3_client = None
        
        # Инициализация S3 если нужно
        if self.storage_type == "s3":
            try:
                import boto3
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=S3_ACCESS_KEY,
                    aws_secret_access_key=S3_SECRET_KEY
                )
                self.s3_bucket_name = S3_BUCKET_NAME
            except ImportError:
                logger.warning("boto3 not installed, falling back to local storage")
                self.storage_type = "local"
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    async def _ensure_client(self) -> None:
        """Создает HTTP клиент если его нет"""
        if self.client:
            return
        self.client = httpx.AsyncClient(timeout=60.0, verify=True, follow_redirects=True)
    
    async def download_image(self, image_url: str, product_id: Optional[str] = None, base_url: Optional[str] = None) -> Optional[str]:
        """
        Скачивает изображение по URL и сохраняет его
        
        Args:
            image_url: URL изображения (может быть относительным или абсолютным)
            product_id: ID товара для логирования
            base_url: Базовый URL для построения абсолютного URL из относительного
        
        Returns:
            URL сохраненного изображения или None в случае ошибки
        """
        try:
            await self._ensure_client()
            
            # Если URL относительный, нужно сделать его абсолютным
            # Обычно в CommerceML это путь типа "import_files/..."
            if not image_url.startswith('http'):
                if base_url:
                    # Строим абсолютный URL на основе базового URL XML
                    absolute_url = urljoin(base_url, image_url)
                    logger.debug(f"Относительный URL преобразован в абсолютный: {image_url} -> {absolute_url}")
                    image_url = absolute_url
                else:
                    # Если базовый URL не указан, не можем скачать относительный URL
                    logger.warning(f"Относительный URL изображения: {image_url}. Базовый URL не указан, пропускаем.")
                    return None
            
            logger.debug(f"Скачивание изображения: {image_url} (товар: {product_id})")
            
            response = await self.client.get(image_url)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "").lower()
            if not content_type.startswith("image/"):
                logger.warning(
                    f"Неверный content-type для изображения {image_url}: {content_type or 'unknown'}"
                )
                return None
            
            if len(response.content) == 0:
                logger.warning(f"Изображение пустое: {image_url}")
                return None
            
            # Определяем расширение файла
            parsed_url = urlparse(image_url)
            file_ext = Path(parsed_url.path).suffix or '.jpg'
            if file_ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                file_ext = '.jpg'
            
            # Генерируем имя файла на основе URL
            url_hash = hashlib.md5(image_url.encode()).hexdigest()[:12]
            filename = f"{url_hash}{file_ext}"
            
            # Сохраняем изображение
            if self.storage_type == "s3":
                saved_url = await self._save_to_s3(response.content, filename)
            else:
                saved_url = await self._save_locally(response.content, filename)
            
            logger.info(f"Изображение скачано и сохранено: {image_url} -> {saved_url}")
            return saved_url
            
        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP ошибка при скачивании изображения {image_url}: {e.response.status_code}")
            return None
        except httpx.RequestError as e:
            logger.warning(f"Ошибка запроса при скачивании изображения {image_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Ошибка при скачивании изображения {image_url}: {e}", exc_info=True)
            return None
    
    async def _save_locally(self, image_data: bytes, filename: str) -> str:
        """Сохранение изображения локально"""
        file_path = LOCAL_STORAGE_PATH / filename
        file_path.write_bytes(image_data)
        return f"/static/product_images/{filename}"
    
    async def _save_to_s3(self, image_data: bytes, filename: str) -> str:
        """Сохранение изображения в S3"""
        if not self.s3_client or not self.s3_bucket_name:
            raise ValueError("S3 не настроен")
        
        key = f"product_images/{filename}"
        self.s3_client.put_object(
            Bucket=self.s3_bucket_name,
            Key=key,
            Body=image_data,
            ContentType='image/jpeg',
            ACL='public-read'
        )
        return f"https://{self.s3_bucket_name}.s3.amazonaws.com/{key}"
    
    async def download_images_for_product(
        self,
        image_urls: List[str],
        product_id: Optional[str] = None,
        max_concurrent: int = 5,
        base_url: Optional[str] = None
    ) -> List[str]:
        """
        Скачивает несколько изображений для товара параллельно
        
        Args:
            image_urls: Список URL изображений
            product_id: ID товара для логирования
            max_concurrent: Максимальное количество одновременных загрузок
        
        Returns:
            Список URL сохраненных изображений
        """
        if not image_urls:
            return []
        
        # Создаем семафор для ограничения параллельных загрузок
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def download_with_semaphore(url: str) -> Optional[str]:
            async with semaphore:
                return await self.download_image(url, product_id, base_url)
        
        # Скачиваем все изображения параллельно
        tasks = [download_with_semaphore(url) for url in image_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Фильтруем успешные результаты
        downloaded_urls = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Ошибка при скачивании изображения: {result}")
            elif result:
                downloaded_urls.append(result)
        
        logger.info(f"Скачано {len(downloaded_urls)} из {len(image_urls)} изображений для товара {product_id}")
        return downloaded_urls
