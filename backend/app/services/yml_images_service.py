"""
Сервис для загрузки изображений товаров из YML файла.
Используется как резервный источник изображений, если в 1С изображения недоступны.
"""
import httpx
import logging
import os
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class YMLImagesService:
    """Сервис для работы с изображениями товаров из YML файла"""
    
    def __init__(
        self,
        yml_url: Optional[str] = None,
    ):
        self.yml_url = yml_url or os.getenv(
            "YML_URL",
            "https://glamejewelry.ru/tstore/yml/b743eb13397ad6a83d95caf72d40b7b2.yml"
        )
        self.client: Optional[httpx.AsyncClient] = None
        self._yml_cache: Optional[Dict[str, Dict[str, Any]]] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def _ensure_client(self) -> None:
        if self.client:
            return
        self.client = httpx.AsyncClient(timeout=120.0, verify=True)

    async def fetch_yml(self) -> Dict[str, Dict[str, Any]]:
        """
        Загрузить и распарсить YML файл.
        
        Returns:
            Словарь {vendorCode: {article, images, ...}}
        """
        if self._yml_cache:
            return self._yml_cache
        
        await self._ensure_client()
        
        try:
            response = await self.client.get(self.yml_url)
            response.raise_for_status()
            
            # Парсим XML
            root = ET.fromstring(response.content)
            
            products: Dict[str, Dict[str, Any]] = {}
            
            # Ищем все offer элементы (без namespace, так как YML обычно не использует namespace)
            offers = root.findall(".//offer")
            for offer in offers:
                vendor_code_elem = offer.find("vendorCode")
                if vendor_code_elem is None or vendor_code_elem.text is None:
                    continue
                
                vendor_code = vendor_code_elem.text.strip()
                
                # Получаем изображение
                picture_elem = offer.find("picture")
                images = []
                if picture_elem is not None and picture_elem.text:
                    images.append(picture_elem.text.strip())
                
                # Получаем дополнительные данные для сопоставления
                name_elem = offer.find("name")
                name = name_elem.text.strip() if name_elem is not None and name_elem.text else None
                
                products[vendor_code] = {
                    "vendorCode": vendor_code,
                    "images": images,
                    "name": name,
                    "offer_id": offer.get("id"),
                }
            
            self._yml_cache = products
            logger.info(f"Загружено {len(products)} товаров из YML")
            return products
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке YML файла: {e}", exc_info=True)
            return {}

    async def get_images_by_article(
        self,
        article: str
    ) -> List[str]:
        """
        Получить изображения для товара по артикулу.
        
        Args:
            article: Артикул товара (vendorCode в YML)
        
        Returns:
            Список URL изображений
        """
        yml_data = await self.fetch_yml()
        
        if not article:
            return []
        
        # Ищем точное совпадение по артикулу
        product = yml_data.get(article)
        if product:
            images = product.get("images", [])
            if images:
                logger.info(f"Найдено {len(images)} изображений в YML для артикула {article}")
                return images
        
        # Пробуем частичное совпадение (если артикул с суффиксом -G, -S и т.д.)
        article_base = article.rstrip("-GS")
        for vendor_code, product_data in yml_data.items():
            if vendor_code.startswith(article_base) or article_base in vendor_code:
                images = product_data.get("images", [])
                if images:
                    logger.info(f"Найдено {len(images)} изображений в YML для артикула {article} (частичное совпадение: {vendor_code})")
                    return images
        
        logger.debug(f"Изображения не найдены в YML для артикула {article}")
        return []

    async def get_images_by_articles(
        self,
        articles: List[str]
    ) -> Dict[str, List[str]]:
        """
        Получить изображения для нескольких товаров по артикулам.
        
        Args:
            articles: Список артикулов
        
        Returns:
            Словарь {article: [images]}
        """
        yml_data = await self.fetch_yml()
        result: Dict[str, List[str]] = {}
        
        for article in articles:
            if not article:
                continue
            
            # Ищем точное совпадение
            product = yml_data.get(article)
            if product:
                images = product.get("images", [])
                if images:
                    result[article] = images
                    continue
            
            # Пробуем частичное совпадение
            article_base = article.rstrip("-GS")
            for vendor_code, product_data in yml_data.items():
                if vendor_code.startswith(article_base) or article_base in vendor_code:
                    images = product_data.get("images", [])
                    if images:
                        result[article] = images
                        break
        
        return result
