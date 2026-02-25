"""
Сервис для загрузки изображений товаров из 1С через OData mediaresource.
Изображения хранятся в бинарном виде в базе данных 1С и доступны через отдельные запросы.
"""
import httpx
import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)


class OneCImagesService:
    """Сервис для работы с изображениями товаров из 1С"""
    
    def __init__(
        self,
        api_url: Optional[str] = None,
        api_token: Optional[str] = None,
    ):
        self.api_url = api_url or os.getenv("ONEC_API_URL")
        self.api_token = api_token or os.getenv("ONEC_API_TOKEN")
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def _ensure_client(self) -> None:
        if self.client:
            return
        if not self.api_url:
            raise ValueError("ONEC_API_URL не настроен")

        # Базовые заголовки без Authorization - добавляем его в каждом запросе отдельно
        # чтобы можно было использовать разные заголовки для разных типов запросов
        headers = {"Accept": "*/*"}
        if self.api_token:
            if self.api_token.startswith("Basic "):
                headers["Authorization"] = self.api_token
            else:
                headers["Authorization"] = f"Basic {self.api_token}"

        self.client = httpx.AsyncClient(timeout=120.0, headers=headers, verify=True)

    async def fetch_attached_files(
        self,
        owner_key: str,
        collection: str = "Catalog_НоменклатураПрисоединенныеФайлы"
    ) -> List[Dict[str, Any]]:
        """
        Получить список присоединенных файлов для товара/характеристики.
        
        Args:
            owner_key: Ref_Key владельца файла (товара или характеристики)
            collection: Коллекция присоединенных файлов
        
        Returns:
            Список метаданных файлов
        """
        await self._ensure_client()
        
        # Фильтруем по ВладелецФайла_Key
        url = f"{self.api_url.rstrip('/')}/{collection}"
        params = {
            "$filter": f"ВладелецФайла_Key eq guid'{owner_key}'",
            "$orderby": "ИндексКартинки asc"  # Сортируем по индексу картинки
        }
        
        try:
            # Для OData может быть XML или JSON, пробуем оба варианта
            headers = {"Accept": "application/json, application/atom+xml, */*"}
            if self.api_token:
                if self.api_token.startswith("Basic "):
                    headers["Authorization"] = self.api_token
                else:
                    headers["Authorization"] = f"Basic {self.api_token}"
            
            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()
            
            # Проверяем Content-Type
            content_type = response.headers.get("Content-Type", "").lower()
            
            # Пробуем парсить как JSON
            try:
                data = response.json()
                files = data.get("value", [])
                logger.info(f"Найдено {len(files)} присоединенных файлов для {owner_key}")
                return files
            except ValueError:
                # Если не JSON, пробуем парсить как XML (Atom Feed)
                if "xml" in content_type or "atom" in content_type:
                    try:
                        import xml.etree.ElementTree as ET
                        root = ET.fromstring(response.content)
                        
                        # Парсим Atom Feed
                        files = []
                        # Ищем все entry элементы
                        for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
                            file_data = {}
                            # Извлекаем свойства из m:properties
                            props = entry.find(".//{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}properties")
                            if props is not None:
                                for prop in props:
                                    # Убираем namespace из имени тега
                                    tag_name = prop.tag.split("}")[-1] if "}" in prop.tag else prop.tag
                                    file_data[tag_name] = prop.text
                            
                            if file_data.get("Ref_Key"):
                                files.append(file_data)
                        
                        logger.info(f"Найдено {len(files)} присоединенных файлов для {owner_key} (из XML)")
                        return files
                    except Exception as e:
                        logger.warning(f"Не удалось распарсить XML ответ для {collection}: {e}")
                        return []
                else:
                    logger.warning(f"Неожиданный Content-Type для {collection}: {content_type}")
                    return []
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Коллекция {collection} недоступна (404)")
                return []
            # Логируем детали ошибки
            try:
                error_text = e.response.text[:500]  # Первые 500 символов
                logger.error(f"HTTP ошибка {e.response.status_code} при получении файлов из {collection}: {error_text}")
            except:
                logger.error(f"HTTP ошибка {e.response.status_code} при получении файлов из {collection}")
            return []
        except ValueError as e:
            # Ошибка парсинга JSON
            logger.error(f"Ошибка парсинга JSON при получении присоединенных файлов из {collection}: {e}")
            try:
                # Пробуем посмотреть, что вернул сервер
                response_text = response.text[:500] if 'response' in locals() else "ответ недоступен"
                logger.debug(f"Ответ сервера (первые 500 символов): {response_text}")
            except:
                pass
            return []
        except Exception as e:
            logger.error(f"Ошибка при получении присоединенных файлов из {collection}: {e}", exc_info=True)
            return []

    def _extract_media_link_from_xml(self, xml_content: bytes, api_url: str) -> Optional[str]:
        """
        Извлекает ссылку на бинарные данные файла из XML метаданных.
        
        Args:
            xml_content: XML содержимое ответа от 1С
            api_url: Базовый URL API 1С
        
        Returns:
            Полный URL для скачивания файла или None
        """
        import xml.etree.ElementTree as ET
        
        try:
            root = ET.fromstring(xml_content)
            
            # Пространства имен для поиска
            namespaces = {
                'atom': 'http://www.w3.org/2005/Atom',
                'ds': 'http://schemas.microsoft.com/ado/2007/08/dataservices'
            }
            
            # Получаем xml:base из корневого элемента
            xml_base = root.get('{http://www.w3.org/XML/1998/namespace}base')
            if not xml_base:
                # Если xml:base нет, используем базовый URL API
                xml_base = api_url.rstrip('/')
            
            # Логируем все ссылки для отладки
            all_links = []
            for link in root.findall('.//{http://www.w3.org/2005/Atom}link'):
                rel = link.get('rel', '')
                href = link.get('href', '')
                all_links.append((rel, href))
            
            logger.debug(f"Найдено ссылок в метаданных: {len(all_links)}")
            for rel, href in all_links:
                logger.debug(f"  - rel: {rel[:100] if rel else 'N/A'}, href: {href[:100] if href else 'N/A'}")
            
            # Ищем ссылку на медиаресурс ФайлХранилище
            for link in root.findall('.//{http://www.w3.org/2005/Atom}link'):
                rel = link.get('rel', '')
                if rel and 'mediaresource/ФайлХранилище' in rel:
                    media_url = link.get('href', '')
                    if media_url:
                        logger.debug(f"Найдена ссылка на медиаресурс: {media_url}")
                        
                        # Проверяем, полный это URL или относительный
                        if media_url.startswith('http'):
                            return media_url
                        elif media_url.startswith('/'):
                            # Абсолютный путь от корня сервера
                            # Извлекаем базовый URL до /odata
                            if '/odata' in xml_base:
                                base_parts = xml_base.split('/odata')
                                base_url = base_parts[0] + '/odata'
                            else:
                                base_url = xml_base.rstrip('/')
                            return f"{base_url}{media_url}"
                        else:
                            # Относительный путь - используем xml:base
                            return f"{xml_base.rstrip('/')}/{media_url.lstrip('/')}"
            
            return None
        except Exception as e:
            logger.error(f"Ошибка парсинга XML: {e}", exc_info=True)
            return None

    async def download_file_from_storage(
        self,
        file_ref_key: str,
        collection: str = "Catalog_НоменклатураПрисоединенныеФайлы"
    ) -> Optional[bytes]:
        """
        Скачать бинарный файл из хранилища 1С через mediaresource ссылку.
        
        Правильный алгоритм для 1С OData:
        1. Получить метаданные файла с правильными заголовками (Accept: application/atom+xml)
        2. Извлечь ссылку на медиаресурс из XML
        3. Скачать файл по медиассылке с правильными заголовками (Accept: application/octet-stream)
        
        Args:
            file_ref_key: Ref_Key файла в коллекции присоединенных файлов
            collection: Коллекция присоединенных файлов
        
        Returns:
            Бинарные данные файла или None
        """
        await self._ensure_client()
        
        try:
            # Шаг 1: Получаем метаданные записи через Atom Feed
            metadata_url = f"{self.api_url.rstrip('/')}/{collection}(guid'{file_ref_key}')"
            
            logger.debug(f"Запрос метаданных: GET {metadata_url}")
            
            # Запрашиваем Atom Feed для получения ссылки на медиаресурс
            # Важно: добавляем Authorization в заголовки запроса
            metadata_headers = {
                "Accept": "application/atom+xml",
                "X-Requested-With": "XMLHttpRequest"
            }
            # Добавляем Authorization, если есть
            if self.api_token:
                if self.api_token.startswith("Basic "):
                    metadata_headers["Authorization"] = self.api_token
                else:
                    metadata_headers["Authorization"] = f"Basic {self.api_token}"
            
            response = await self.client.get(metadata_url, headers=metadata_headers)
            response.raise_for_status()
            
            logger.debug(f"Метаданные получены. Статус: {response.status_code}, Content-Type: {response.headers.get('Content-Type')}")
            
            # Шаг 2: Извлекаем ссылку на медиаресурс из XML
            media_url = self._extract_media_link_from_xml(response.content, self.api_url)
            
            if not media_url:
                logger.warning(f"Медиассылка не найдена в XML для файла {file_ref_key}")
                # Пробуем альтернативные варианты
                alternatives = [
                    f"{metadata_url}/ФайлХранилище/$value",
                    f"{metadata_url}/ФайлХранилище",
                ]
                for alt_url in alternatives:
                    logger.debug(f"Пробуем альтернативный URL: {alt_url}")
                    try:
                        test_response = await self.client.get(
                            alt_url,
                            headers={"Accept": "application/octet-stream", "X-Requested-With": "XMLHttpRequest"}
                        )
                        if test_response.status_code == 200 and test_response.content and len(test_response.content) > 0:
                            media_url = alt_url
                            logger.info(f"Альтернативный URL работает: {alt_url}")
                            break
                    except:
                        continue
                
                if not media_url:
                    logger.error(f"Не удалось найти рабочий URL для файла {file_ref_key}")
                    return None
            else:
                logger.info(f"Используем медиассылку: {media_url}")
            
            # Шаг 3: Скачиваем файл по медиассылке
            # Важно: добавляем Authorization в заголовки запроса
            file_headers = {
                "Accept": "application/octet-stream, */*",
                "X-Requested-With": "XMLHttpRequest"
            }
            # Добавляем Authorization, если есть
            if self.api_token:
                if self.api_token.startswith("Basic "):
                    file_headers["Authorization"] = self.api_token
                else:
                    file_headers["Authorization"] = f"Basic {self.api_token}"
            
            # Пробуем несколько вариантов URL для скачивания
            download_urls = [media_url]
            # Если нет /$value, пробуем добавить его
            if not media_url.endswith('/$value'):
                download_urls.append(f"{media_url}/$value")
            # Если есть /$value, пробуем без него
            elif media_url.endswith('/$value'):
                download_urls.insert(0, media_url[:-7])  # Убираем /$value
            
            file_data = None
            for download_url in download_urls:
                logger.debug(f"Пробуем скачать файл по URL: {download_url}")
                try:
                    file_response = await self.client.get(download_url, headers=file_headers)
                    file_response.raise_for_status()
                    
                    content_length = file_response.headers.get('Content-Length', 'неизвестно')
                    content_type = file_response.headers.get('Content-Type', 'неизвестно')
                    
                    logger.debug(f"Ответ: статус={file_response.status_code}, Content-Type={content_type}, Content-Length={content_length}, размер данных={len(file_response.content)} байт")
                    
                    if file_response.content and len(file_response.content) > 0:
                        file_data = file_response.content
                        logger.info(f"Файл успешно скачан по URL: {download_url} ({len(file_data)} байт)")
                        break
                    else:
                        logger.debug(f"Файл пустой по URL: {download_url}")
                except Exception as e:
                    logger.debug(f"Ошибка при скачивании по URL {download_url}: {e}")
                    continue
            
            if not file_data:
                logger.warning(f"Файл {file_ref_key} пустой или не удалось скачать")
                return None
            
            # Проверяем сигнатуры изображений
            image_signatures = [
                b'\xff\xd8\xff',  # JPEG
                b'\x89PNG',        # PNG
                b'GIF87a',         # GIF
                b'GIF89a',         # GIF
                b'RIFF',           # WebP
            ]
            is_image = any(file_data.startswith(sig) for sig in image_signatures)
            
            if is_image:
                logger.info(f"Файл {file_ref_key} успешно загружен ({len(file_data)} байт, определен как изображение)")
                return file_data
            else:
                # Все равно возвращаем, если размер больше 100 байт (может быть изображение с неправильным Content-Type)
                if len(file_data) > 100:
                    logger.info(f"Возвращаем файл несмотря на отсутствие сигнатуры изображения (размер: {len(file_data)} байт, первые байты: {file_data[:20].hex()})")
                    return file_data
                logger.warning(f"Файл {file_ref_key} не является изображением (первые байты: {file_data[:20].hex()})")
                return None
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Файл {file_ref_key} не найден (404)")
                return None
            # Логируем детали ошибки
            try:
                error_text = e.response.text[:500] if hasattr(e.response, 'text') else str(e.response.content[:500])
                logger.error(f"HTTP ошибка {e.response.status_code} при загрузке файла {file_ref_key}: {error_text}")
            except:
                logger.error(f"HTTP ошибка {e.response.status_code} при загрузке файла {file_ref_key}")
            return None
        except Exception as e:
            logger.error(f"Ошибка при загрузке файла {file_ref_key}: {e}", exc_info=True)
            return None

    async def get_images_for_product(
        self,
        product_ref_key: str,
        characteristic_ref_key: Optional[str] = None
    ) -> List[str]:
        """
        Получить изображения для товара или характеристики.
        Приоритет: изображения характеристики, затем изображения основного товара.
        
        Args:
            product_ref_key: Ref_Key товара
            characteristic_ref_key: Ref_Key характеристики (опционально)
        
        Returns:
            Список URL изображений (data:image или base64)
        """
        images: List[str] = []
        
        # Сначала ищем изображения характеристики
        if characteristic_ref_key:
            char_files = await self.fetch_attached_files(
                characteristic_ref_key,
                collection="Catalog_ХарактеристикиНоменклатурыПрисоединенныеФайлы"
            )
            for file_meta in char_files:
                file_ref = file_meta.get("Ref_Key")
                if file_ref:
                    file_data = await self.download_file_from_storage(
                        file_ref,
                        collection="Catalog_ХарактеристикиНоменклатурыПрисоединенныеФайлы"
                    )
                    if file_data:
                        # Конвертируем в base64 data URL
                        import base64
                        extension = file_meta.get("Расширение", "jpeg").lower()
                        mime_type = f"image/{extension}" if extension in ["jpeg", "jpg", "png", "gif", "webp"] else "image/jpeg"
                        base64_data = base64.b64encode(file_data).decode("utf-8")
                        data_url = f"data:{mime_type};base64,{base64_data}"
                        images.append(data_url)
                        logger.info(f"Добавлено изображение характеристики: {file_meta.get('Description', 'без названия')}")
        
        # Затем ищем изображения основного товара
        product_files = await self.fetch_attached_files(
            product_ref_key,
            collection="Catalog_НоменклатураПрисоединенныеФайлы"
        )
        for file_meta in product_files:
            file_ref = file_meta.get("Ref_Key")
            if file_ref:
                file_data = await self.download_file_from_storage(
                    file_ref,
                    collection="Catalog_НоменклатураПрисоединенныеФайлы"
                )
                if file_data:
                    import base64
                    extension = file_meta.get("Расширение", "jpeg").lower()
                    mime_type = f"image/{extension}" if extension in ["jpeg", "jpg", "png", "gif", "webp"] else "image/jpeg"
                    base64_data = base64.b64encode(file_data).decode("utf-8")
                    data_url = f"data:{mime_type};base64,{base64_data}"
                    images.append(data_url)
                    logger.info(f"Добавлено изображение товара: {file_meta.get('Description', 'без названия')}")
        
        return images
