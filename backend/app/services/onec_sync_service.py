"""
Сервис для синхронизации каталога товаров с 1С
Поддерживает несколько способов получения данных:
- Импорт из JSON файлов
- Импорт из CommerceML XML файлов (стандартный формат 1С)
- Синхронизация через YML (Yandex Market Language) формат
- Синхронизация остатков из offers.xml по URL из переменной окружения ONEC_XML_OFFERS_URL
"""
import httpx
import json
import logging
import xml.etree.ElementTree as ET
import base64
import tempfile
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select
from app.models.product import Product
from uuid import UUID

logger = logging.getLogger(__name__)


class OneCSyncService:
    """Сервис синхронизации с 1С"""
    
    def __init__(self, db: AsyncSession, api_url: Optional[str] = None, api_token: Optional[str] = None):
        """
        Инициализация сервиса синхронизации
        
        Args:
            db: Сессия базы данных
            api_url: URL REST API 1С (если используется)
            api_token: Токен авторизации для API 1С
        """
        self.db = db
        self.api_url = api_url
        self.api_token = api_token
        self.client = None  # Будет создан при необходимости
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    def _map_1c_to_product(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Маппинг данных из 1С в формат нашей модели Product
        
        Пример структуры данных из 1С:
        {
            "id": "uuid-1c",
            "code": "00001",
            "name": "Колье Antura",
            "brand": "Antura",
            "price": 8900.00,
            "category": "necklace",
            "images": ["url1", "url2"],
            "tags": ["романтичный", "вечерний"],
            "description": "Описание товара",
            "is_active": true
        }
        """
        # Конвертируем цену в копейки, если она пришла в рублях
        price = item.get("price", 0)
        if isinstance(price, float):
            price = int(price * 100)
        elif isinstance(price, (int, str)):
            price = int(float(price) * 100) if float(price) < 10000 else int(price)
        
        return {
            "external_id": item.get("id") or item.get("uuid"),
            "external_code": item.get("external_code") or item.get("code") or item.get("article"),
            "name": item.get("name") or item.get("title", ""),
            "brand": item.get("brand") or item.get("vendor"),
            "price": price,
            "category": item.get("category") or item.get("type"),
            "images": item.get("images") or item.get("image_urls") or [],
            "tags": item.get("tags") or item.get("attributes", []),
            "description": item.get("description") or item.get("comment"),
            "is_active": item.get("is_active", True) if "is_active" in item else True,
            "sync_status": "synced",
            "sync_metadata": {
                "last_sync": datetime.now(timezone.utc).isoformat(),
                "source": "1c",
                "sync_method": "api" if self.api_url else "file"
            }
        }
    
    # УДАЛЕНО: Метод fetch_from_api для товаров
    # Товары теперь загружаются только через XML (CommerceML)
    # REST API используется только для покупателей и продаж
    # 
    # async def fetch_from_api(self, endpoint: str = "/api/products") -> List[Dict[str, Any]]:
    #     ...
    
    # УДАЛЕНО: Все методы синхронизации с Tilda (fetch_from_tilda, _try_fetch_tilda_url, sync_from_tilda)
    # Работаем только с файлами выгрузки 1С
    
    def _find_element(self, parent, tag_name: str, namespaces: Dict[str, str] = None) -> Optional[ET.Element]:
        """Универсальный поиск элемента с учетом namespace или без"""
        # Сначала пробуем без namespace
        elem = parent.find(tag_name)
        if elem is not None:
            return elem
        
        # Пробуем с разными namespace
        if namespaces:
            for ns_prefix, ns_url in namespaces.items():
                elem = parent.find(f'{{{ns_url}}}{tag_name}')
                if elem is not None:
                    return elem
                elem = parent.find(f'{ns_prefix}:{tag_name}', namespaces)
                if elem is not None:
                    return elem
        
        # Пробуем найти в любом namespace
        for elem in parent.iter():
            if elem.tag.endswith('}' + tag_name) or elem.tag == tag_name:
                return elem
        
        return None
    
    def _find_all_elements(self, parent, tag_name: str, namespaces: Dict[str, str] = None) -> List[ET.Element]:
        """Универсальный поиск всех элементов с учетом namespace или без"""
        results = []
        
        # Сначала пробуем без namespace
        results.extend(parent.findall(tag_name))
        
        # Пробуем с разными namespace
        if namespaces:
            for ns_prefix, ns_url in namespaces.items():
                results.extend(parent.findall(f'{{{ns_url}}}{tag_name}'))
                results.extend(parent.findall(f'{ns_prefix}:{tag_name}', namespaces))
        
        # Пробуем найти в любом namespace через iter
        for elem in parent.iter():
            if elem.tag.endswith('}' + tag_name) or elem.tag == tag_name:
                if elem not in results:
                    results.append(elem)
        
        return results
    
    def _get_text(self, elem: Optional[ET.Element]) -> Optional[str]:
        """Безопасное получение текста из элемента"""
        return elem.text if elem is not None and elem.text else None
    
    def parse_commerceml_xml(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Парсинг CommerceML XML файла из 1С
        
        CommerceML - стандартный формат обмена данными между 1С и интернет-магазинами.
        Поддерживает файлы import.xml (каталог товаров) и offers.xml (цены и остатки).
        
        Args:
            file_path: Путь к XML файлу CommerceML
            
        Returns:
            Список товаров в формате словарей
        """
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # Определяем namespace CommerceML (могут быть разные версии)
            namespaces = {
                'cml': 'http://v8.1c.ru/8.3/MDClasses',
                'cat': 'http://v8.1c.ru/8.1/data/core/catalog',
                'ent': 'http://v8.1c.ru/8.1/data/enterprise/current',
                'comm': 'http://v8.1c.ru/8.1/data/enterprise/current',
            }
            
            products = []
            
            # Парсим каталог товаров (import.xml)
            # Ищем все товары в документе (пробуем разные варианты)
            product_elems = []
            product_elems.extend(self._find_all_elements(root, 'Товар', namespaces))
            product_elems.extend(root.findall('.//Товар'))
            
            # Убираем дубликаты
            seen = set()
            unique_products = []
            for elem in product_elems:
                elem_id = id(elem)
                if elem_id not in seen:
                    seen.add(elem_id)
                    unique_products.append(elem)
            
            for product_elem in unique_products:
                product_data = {}
                
                # Ид товара (уникальный идентификатор)
                product_id = self._get_text(self._find_element(product_elem, 'Ид', namespaces))
                if product_id:
                    product_data['id'] = product_id
                
                # Артикул
                article = self._get_text(self._find_element(product_elem, 'Артикул', namespaces))
                if article:
                    product_data['code'] = article
                
                # Наименование
                name = self._get_text(self._find_element(product_elem, 'Наименование', namespaces))
                if name:
                    product_data['name'] = name
                
                # Описание
                description = self._get_text(self._find_element(product_elem, 'Описание', namespaces))
                if description:
                    product_data['description'] = description
                
                # Группы (категории) - ищем в элементе Группы
                groups = []
                groups_elem = self._find_element(product_elem, 'Группы', namespaces)
                if groups_elem is not None:
                    for group in self._find_all_elements(groups_elem, 'Ид', namespaces):
                        group_id = self._get_text(group)
                        if group_id:
                            groups.append(group_id)
                
                # Также пробуем найти группу напрямую
                group_elem = self._find_element(product_elem, 'Группа', namespaces)
                if group_elem is not None:
                    group_id = self._get_text(self._find_element(group_elem, 'Ид', namespaces))
                    if group_id and group_id not in groups:
                        groups.append(group_id)
                
                # Берем первую группу как категорию
                if groups:
                    product_data['category'] = groups[0]
                
                # Картинки
                images = []
                for img_elem in self._find_all_elements(product_elem, 'Картинка', namespaces):
                    img_text = self._get_text(img_elem)
                    if img_text:
                        images.append(img_text)
                product_data['images'] = images
                
                # Характеристики товара (используем как теги)
                tags = []
                props_elem = self._find_element(product_elem, 'ХарактеристикиТовара', namespaces)
                if props_elem is not None:
                    for prop in self._find_all_elements(props_elem, 'ХарактеристикаТовара', namespaces):
                        name_prop = self._get_text(self._find_element(prop, 'Наименование', namespaces))
                        value_prop = self._get_text(self._find_element(prop, 'Значение', namespaces))
                        if name_prop and value_prop:
                            tags.append(f"{name_prop}: {value_prop}")
                
                # Бренд - ищем в свойствах товара
                brand = None
                props_values = self._find_all_elements(product_elem, 'ЗначениеСвойства', namespaces)
                for prop in props_values:
                    prop_id_elem = self._find_element(prop, 'Ид', namespaces)
                    prop_value_elem = self._find_element(prop, 'Значение', namespaces)
                    prop_id = self._get_text(prop_id_elem)
                    prop_value = self._get_text(prop_value_elem)
                    
                    if prop_id and prop_value and 'бренд' in prop_id.lower():
                        brand = prop_value
                        break
                
                # Также пробуем найти бренд в наименовании товара или в других полях
                if not brand and name:
                    # Можно добавить логику извлечения бренда из наименования
                    pass
                
                if brand:
                    product_data['brand'] = brand
                
                # Статус активности
                product_data['is_active'] = True
                
                # Добавляем товар только если есть хотя бы ID или код
                if product_data.get('id') or product_data.get('code'):
                    products.append(product_data)
            
            # Если это файл offers.xml, парсим цены и остатки
            # Ищем предложения (цены)
            offers_dict = {}
            offer_elems = []
            offer_elems.extend(self._find_all_elements(root, 'Предложение', namespaces))
            offer_elems.extend(root.findall('.//Предложение'))
            
            # Убираем дубликаты
            seen_offers = set()
            unique_offers = []
            for elem in offer_elems:
                elem_id = id(elem)
                if elem_id not in seen_offers:
                    seen_offers.add(elem_id)
                    unique_offers.append(elem)
            
            for offer_elem in unique_offers:
                offer_id_elem = self._find_element(offer_elem, 'Ид', namespaces)
                if offer_id_elem is None:
                    continue
                
                offer_id = self._get_text(offer_id_elem)
                if not offer_id:
                    continue
                
                # Цены
                prices_elem = self._find_element(offer_elem, 'Цены', namespaces)
                if prices_elem is not None:
                    for price_elem in self._find_all_elements(prices_elem, 'Цена', namespaces):
                        price_value_elem = self._find_element(price_elem, 'ЦенаЗаЕдиницу', namespaces)
                        price_value = self._get_text(price_value_elem)
                        if price_value:
                            try:
                                offers_dict[offer_id] = float(price_value)
                            except ValueError:
                                pass
            
            # Объединяем цены с товарами
            for product in products:
                product_id = product.get('id')
                if product_id and product_id in offers_dict:
                    product['price'] = offers_dict[product_id]
            
            logger.info(f"Распарсено {len(products)} товаров из CommerceML файла")
            return products
            
        except ET.ParseError as e:
            logger.error(f"Ошибка парсинга XML файла: {e}")
            # Пытаемся прочитать начало файла для отладки
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    file_preview = f.read(500)
            except Exception:
                file_preview = "Не удалось прочитать файл"
            
            raise ValueError(
                f"Неверный формат XML файла:\n\n"
                f"Ошибка: {str(e)}\n\n"
                f"Начало файла:\n{file_preview}\n\n"
                f"Возможные причины:\n"
                f"1. Файл не является валидным XML\n"
                f"2. Файл поврежден или неполный\n"
                f"3. Неправильная кодировка файла\n"
                f"4. Файл содержит HTML вместо XML"
            )
        except Exception as e:
            logger.error(f"Ошибка при обработке CommerceML файла: {e}", exc_info=True)
            raise
    
    def parse_yml_xml(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Парсинг YML (Yandex Market Language) XML файла
        
        YML - формат экспорта товаров для Яндекс.Маркет и других маркетплейсов.
        Структура: yml_catalog -> shop -> offers -> offer
        
        Args:
            file_path: Путь к YML XML файлу
            
        Returns:
            Список товаров в формате словарей
        """
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            products = []
            
            # Ищем shop -> offers -> offer
            shop_elem = root.find('.//shop')
            if shop_elem is None:
                shop_elem = root.find('shop')
            
            if shop_elem is None:
                error_msg = "Не найден элемент shop в YML файле. Проверьте формат файла - должен быть yml_catalog -> shop -> offers"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Получаем категории для маппинга
            categories = {}
            for cat_elem in shop_elem.findall('.//category'):
                cat_id = cat_elem.get('id')
                cat_name = cat_elem.text
                if cat_id and cat_name:
                    categories[cat_id] = cat_name
            
            # Парсим offers
            offers_elem = shop_elem.find('offers')
            if offers_elem is None:
                offers_elem = shop_elem.find('.//offers')
            
            if offers_elem is None:
                error_msg = "Не найден элемент offers в YML файле. Проверьте формат файла - должен быть shop -> offers -> offer"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            for offer_elem in offers_elem.findall('offer'):
                try:
                    product_data = {}
                    
                    # ID товара
                    offer_id = offer_elem.get('id')
                    if offer_id:
                        product_data['id'] = offer_id
                        product_data['external_id'] = offer_id
                    
                    # group_id (для вариантов товара)
                    group_id = offer_elem.get('group_id')
                    if group_id:
                        product_data['group_id'] = group_id
                    
                    # Название
                    name_elem = offer_elem.find('name')
                    if name_elem is not None and name_elem.text:
                        product_data['name'] = name_elem.text.strip()
                    
                    # Артикул (vendorCode)
                    vendor_code_elem = offer_elem.find('vendorCode')
                    if vendor_code_elem is not None and vendor_code_elem.text:
                        product_data['code'] = vendor_code_elem.text.strip()
                        product_data['external_code'] = vendor_code_elem.text.strip()
                    
                    # Цена
                    price_elem = offer_elem.find('price')
                    if price_elem is not None and price_elem.text:
                        try:
                            price = float(price_elem.text.strip())
                            # Конвертируем в копейки
                            product_data['price'] = int(price * 100)
                        except ValueError:
                            pass
                    
                    # Валюта
                    currency_elem = offer_elem.find('currencyId')
                    if currency_elem is not None and currency_elem.text:
                        product_data['currency'] = currency_elem.text.strip()
                    
                    # Категория
                    category_id_elem = offer_elem.find('categoryId')
                    if category_id_elem is not None and category_id_elem.text:
                        category_id = category_id_elem.text.strip()
                        product_data['category'] = categories.get(category_id, category_id)
                    
                    # Изображение
                    picture_elem = offer_elem.find('picture')
                    if picture_elem is not None and picture_elem.text:
                        product_data['images'] = [picture_elem.text.strip()]
                    else:
                        product_data['images'] = []
                    
                    # URL товара
                    url_elem = offer_elem.find('url')
                    if url_elem is not None and url_elem.text:
                        product_data['url'] = url_elem.text.strip()
                    
                    # Количество (остаток)
                    count_elem = offer_elem.find('count')
                    if count_elem is not None and count_elem.text:
                        try:
                            count = int(count_elem.text.strip())
                            product_data['is_active'] = count > 0
                            product_data['stock'] = count
                        except ValueError:
                            product_data['is_active'] = True
                    else:
                        product_data['is_active'] = True
                    
                    # Штрихкод
                    barcode_elem = offer_elem.find('barcode')
                    if barcode_elem is not None and barcode_elem.text:
                        product_data['barcode'] = barcode_elem.text.strip()
                    
                    # Параметры (характеристики товара)
                    tags = []
                    brand = None
                    for param_elem in offer_elem.findall('param'):
                        param_name = param_elem.get('name', '')
                        param_value = param_elem.text.strip() if param_elem.text else ''
                        
                        if param_name and param_value:
                            # Ищем бренд в параметрах
                            if 'бренд' in param_name.lower() or 'brand' in param_name.lower():
                                brand = param_value
                            else:
                                tags.append(f"{param_name}: {param_value}")
                    
                    if brand:
                        product_data['brand'] = brand
                    
                    if tags:
                        product_data['tags'] = tags
                    else:
                        product_data['tags'] = []
                    
                    # Описание (может быть в отдельном элементе description)
                    description_elem = offer_elem.find('description')
                    if description_elem is not None and description_elem.text:
                        product_data['description'] = description_elem.text.strip()
                    
                    # Метаданные синхронизации
                    product_data['sync_status'] = 'synced'
                    product_data['sync_metadata'] = {
                        'last_sync': datetime.now(timezone.utc).isoformat(),
                        'source': 'yml',
                        'sync_method': 'url'
                    }
                    
                    # Добавляем товар только если есть хотя бы ID или название
                    if product_data.get('id') or product_data.get('name'):
                        products.append(product_data)
                except Exception as e:
                    logger.warning(f"Ошибка при парсинге offer в YML: {e}")
                    continue
            
            logger.info(f"Распарсено {len(products)} товаров из YML файла")
            return products
            
        except ET.ParseError as e:
            logger.error(f"Ошибка парсинга YML XML файла: {e}")
            raise ValueError(f"Неверный формат YML XML файла: {e}")
        except Exception as e:
            logger.error(f"Ошибка при парсинге YML файла: {e}", exc_info=True)
            raise
    
    async def fetch_from_yml_url(self, yml_url: str) -> List[Dict[str, Any]]:
        """
        Получение данных из YML файла по URL
        
        Args:
            yml_url: URL к YML XML файлу
            
        Returns:
            Список товаров из YML
        """
        try:
            # Создаем временный клиент если его нет
            if not self.client:
                self.client = httpx.AsyncClient(timeout=120.0, follow_redirects=True)
            
            logger.info(f"Загрузка YML файла с URL: {yml_url}")
            response = await self.client.get(yml_url)
            response.raise_for_status()
            
            # Проверяем Content-Type
            content_type = response.headers.get("content-type", "").lower()
            if "xml" not in content_type and not response.text.strip().startswith("<?xml"):
                logger.warning(f"Неожиданный Content-Type: {content_type}")
            
            # Сохраняем ответ во временный файл для парсинга
            with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.xml') as tmp_file:
                tmp_file.write(response.content)
                tmp_file_path = tmp_file.name
            
            try:
                # Парсим YML XML
                products = self.parse_yml_xml(tmp_file_path)
                logger.info(f"Получено {len(products)} товаров из YML")
                return products
            finally:
                # Удаляем временный файл
                if os.path.exists(tmp_file_path):
                    try:
                        os.unlink(tmp_file_path)
                    except Exception as e:
                        logger.warning(f"Не удалось удалить временный файл: {e}")
                        
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            response_text = e.response.text[:200] if e.response.text else ""
            
            if status_code == 404:
                logger.error(f"YML файл не найден: {yml_url}")
                raise ValueError(f"YML файл не найден (404): {yml_url}")
            elif status_code == 403:
                logger.error("Доступ запрещен к YML файлу")
                raise ValueError("Доступ запрещен к YML файлу")
            else:
                logger.error(f"HTTP ошибка при получении YML файла: {status_code}, ответ: {response_text}")
                raise ValueError(f"Ошибка при обращении к YML файлу (HTTP {status_code}): {response_text or 'Неизвестная ошибка'}")
        except httpx.HTTPError as e:
            logger.error(f"Ошибка при получении YML файла: {e}")
            raise ValueError(f"Ошибка сети при обращении к YML файлу: {str(e)}")
        except Exception as e:
            logger.error(f"Неожиданная ошибка при работе с YML: {e}", exc_info=True)
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Ошибка при синхронизации с YML: {str(e)}")
    
    def load_from_file(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Загрузка данных из файла (JSON или XML CommerceML)
        
        Args:
            file_path: Путь к файлу с данными из 1С (JSON или XML)
            
        Returns:
            Список товаров из файла
        """
        try:
            # Определяем тип файла по расширению
            if file_path.lower().endswith('.xml'):
                return self.parse_commerceml_xml(file_path)
            elif file_path.lower().endswith('.json'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Поддерживаем разные форматы файла
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return data.get("products") or data.get("items") or data.get("data", [])
                else:
                    logger.warning(f"Неожиданный формат файла: {type(data)}")
                    return []
            else:
                raise ValueError(f"Неподдерживаемый формат файла. Используйте .json или .xml")
        except FileNotFoundError:
            logger.error(f"Файл не найден: {file_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON файла: {e}")
            raise
    
    async def sync_products(
        self,
        products_data: List[Dict[str, Any]],
        update_existing: bool = True,
        deactivate_missing: bool = False
    ) -> Dict[str, Any]:
        """
        Синхронизация товаров в базу данных
        
        Args:
            products_data: Список товаров для синхронизации
            update_existing: Обновлять ли существующие товары
            deactivate_missing: Деактивировать товары, которых нет в новых данных
            
        Returns:
            Статистика синхронизации
        """
        stats = {
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "deactivated": 0
        }
        
        synced_external_ids = set()
        
        for item_data in products_data:
            try:
                mapped_data = self._map_1c_to_product(item_data)
                external_id = mapped_data.get("external_id")
                
                if not external_id:
                    logger.warning(f"Товар без external_id пропущен: {mapped_data.get('name')}")
                    stats["skipped"] += 1
                    continue
                
                synced_external_ids.add(external_id)
                
                # Ищем существующий товар по external_id
                result = await self.db.execute(
                    select(Product).where(Product.external_id == external_id)
                )
                existing_product = result.scalar_one_or_none()
                
                if existing_product:
                    if update_existing:
                        # Обновляем существующий товар
                        for key, value in mapped_data.items():
                            if key != "external_id":  # Не обновляем external_id
                                setattr(existing_product, key, value)
                        existing_product.updated_at = datetime.now(timezone.utc)
                        stats["updated"] += 1
                    else:
                        stats["skipped"] += 1
                else:
                    # Создаем новый товар
                    new_product = Product(**mapped_data)
                    self.db.add(new_product)
                    stats["created"] += 1
                
            except Exception as e:
                logger.error(f"Ошибка при синхронизации товара: {e}", exc_info=True)
                stats["errors"] += 1
        
        # Деактивируем товары, которых нет в новых данных
        if deactivate_missing:
            if synced_external_ids:
                stmt = select(Product).where(
                    and_(
                        Product.external_id.isnot(None),
                        ~Product.external_id.in_(synced_external_ids),
                        Product.is_active == True
                    )
                )
            else:
                # Если новых данных нет — считаем, что всё "missing"
                stmt = select(Product).where(
                    and_(
                        Product.external_id.isnot(None),
                        Product.is_active == True
                    )
                )
            res = await self.db.execute(stmt)
            missing_products = res.scalars().all()
            
            for product in missing_products:
                product.is_active = False
                product.sync_status = "pending"
                stats["deactivated"] += 1
        
        try:
            await self.db.commit()
            logger.info(f"Синхронизация завершена: {stats}")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Ошибка при сохранении изменений: {e}")
            raise
        
        return stats
    
    # УДАЛЕНО: Метод sync_from_api для товаров
    # Товары теперь загружаются только через XML (CommerceML)
    # REST API используется только для покупателей и продаж
    
    async def sync_from_file(
        self,
        file_path: str,
        update_existing: bool = True,
        deactivate_missing: bool = False,
        sync_stocks: bool = True
    ) -> Dict[str, Any]:
        """
        Полная синхронизация из файла
        
        Args:
            file_path: Путь к JSON или XML файлу
            update_existing: Обновлять ли существующие товары
            deactivate_missing: Деактивировать отсутствующие товары
            sync_stocks: Синхронизировать ли остатки из offers.xml по URL из .env
            
        Returns:
            Статистика синхронизации
        """
        products_data = self.load_from_file(file_path)
        stats = await self.sync_products(
            products_data=products_data,
            update_existing=update_existing,
            deactivate_missing=deactivate_missing
        )
        
        # Синхронизируем остатки из offers.xml по URL из .env, если включено
        if sync_stocks:
            offers_url = os.getenv("ONEC_XML_OFFERS_URL")
            if offers_url:
                try:
                    from app.services.onec_stock_service import OneCStockService
                    logger.info(f"Синхронизация остатков из offers.xml: {offers_url}")
                    async with OneCStockService(self.db) as stock_service:
                        stock_stats = await stock_service.sync_stocks_from_xml(offers_url)
                        stats["stock_sync"] = stock_stats
                        logger.info(f"Синхронизация остатков завершена: {stock_stats}")
                except Exception as e:
                    logger.warning(f"Не удалось синхронизировать остатки из offers.xml: {e}", exc_info=True)
                    stats["stock_sync_error"] = str(e)
            else:
                logger.info("ONEC_XML_OFFERS_URL не указан в .env, пропускаем синхронизацию остатков")
        
        return stats
    
    # УДАЛЕНО: async def sync_from_tilda - работаем только с файлами выгрузки 1С
    
    async def sync_from_yml(
        self,
        yml_url: str,
        update_existing: bool = True,
        deactivate_missing: bool = False
    ) -> Dict[str, Any]:
        """
        Полная синхронизация из YML файла по URL
        
        Args:
            yml_url: URL к YML XML файлу
            update_existing: Обновлять ли существующие товары
            deactivate_missing: Деактивировать отсутствующие товары
            
        Returns:
            Статистика синхронизации
        """
        products_data = await self.fetch_from_yml_url(yml_url)
        return await self.sync_products(
            products_data=products_data,
            update_existing=update_existing,
            deactivate_missing=deactivate_missing
        )
