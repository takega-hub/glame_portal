"""
Сервис для загрузки и парсинга CommerceML XML файлов из 1С по URL.
CommerceML - стандартный формат обмена данными между 1С и интернет-магазинами.
"""
import httpx
import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from io import BytesIO

logger = logging.getLogger(__name__)


class CommerceMLXMLService:
    """Сервис для работы с CommerceML XML файлами из 1С"""
    
    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    async def _ensure_client(self) -> None:
        """Создает HTTP клиент если его нет"""
        if self.client:
            return
        self.client = httpx.AsyncClient(timeout=120.0, verify=True)
    
    async def download_xml_from_url(self, url: str) -> bytes:
        """
        Скачивает XML файл по URL
        
        Args:
            url: URL для скачивания XML файла
        
        Returns:
            Бинарные данные XML файла
        """
        await self._ensure_client()
        
        try:
            logger.info(f"Скачивание XML файла с URL: {url}")
            response = await self.client.get(url)
            response.raise_for_status()
            
            logger.info(f"XML файл успешно скачан ({len(response.content)} байт)")
            return response.content
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP ошибка при скачивании XML: {e.response.status_code}")
            raise ValueError(f"Не удалось скачать XML файл: HTTP {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Ошибка запроса при скачивании XML: {e}")
            raise ValueError(f"Ошибка при скачивании XML файла: {str(e)}")
        except Exception as e:
            logger.error(f"Неожиданная ошибка при скачивании XML: {e}", exc_info=True)
            raise
    
    def parse_groups(self, xml_content: bytes) -> List[Dict[str, Any]]:
        """
        Парсинг групп каталога из CommerceML XML
        
        Args:
            xml_content: Бинарные данные XML файла
        
        Returns:
            Список групп в формате словарей [{'external_id': '...', 'name': '...', 'parent_id': '...'}, ...]
        """
        try:
            root = ET.fromstring(xml_content)
            
            namespaces = {
                '': 'urn:1C.ru:commerceml_210',
                'xs': 'http://www.w3.org/2001/XMLSchema',
                'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            }
            
            groups = []
            
            # Ищем Классификатор (стандартная структура CommerceML)
            classifier = root.find('{urn:1C.ru:commerceml_210}Классификатор')
            if classifier is None:
                # Пробуем без namespace
                classifier = root.find('.//Классификатор')
            
            # Если Классификатор не найден, пробуем искать Группы в Каталоге (альтернативная структура)
            if classifier is None:
                logger.info("Классификатор не найден, ищем Группы в Каталоге")
                catalog = root.find('.//{urn:1C.ru:commerceml_210}Каталог')
                if catalog is None:
                    catalog = root.find('.//Каталог')
                
                if catalog is None:
                    logger.warning("Ни Классификатор, ни Каталог не найдены в XML")
                    return groups
                
                # Ищем Группы в Каталоге
                groups_section = catalog.find('{urn:1C.ru:commerceml_210}Группы')
                if groups_section is None:
                    groups_section = catalog.find('Группы')
            else:
                # Ищем Группы в Классификаторе (стандартная структура)
                groups_section = classifier.find('{urn:1C.ru:commerceml_210}Группы')
                if groups_section is None:
                    groups_section = classifier.find('Группы')
            
            if groups_section is None:
                logger.info("Раздел Группы не найден ни в Классификаторе, ни в Каталоге")
                return groups
            
            # Парсим каждую группу (рекурсивно обрабатываем вложенные)
            # Пробуем с полным namespace в теге
            group_elems = groups_section.findall('{urn:1C.ru:commerceml_210}Группа')
            if not group_elems:
                # Пробуем без namespace
                group_elems = groups_section.findall('Группа')
            
            logger.info(f"Найдено элементов Группа в XML: {len(group_elems)}")
            
            for group_elem in group_elems:
                parsed_groups = self._parse_group_element(group_elem, namespaces)
                groups.extend(parsed_groups)
            
            logger.info(f"Найдено {len(groups)} групп каталога в XML (включая вложенные)")
            return groups
            
        except Exception as e:
            logger.error(f"Ошибка парсинга групп из XML: {e}", exc_info=True)
            return []
    
    def _parse_group_element(self, group_elem: ET.Element, namespaces: Dict[str, str], parent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Парсит элемент группы из XML (рекурсивно обрабатывает вложенные группы)
        
        Args:
            group_elem: XML элемент группы
            namespaces: Словарь namespaces для поиска
            parent_id: ID родительской группы (для вложенных групп)
        
        Returns:
            Список групп (текущая + все вложенные)
        """
        groups = []
        
        # Ид группы (пробуем с полным namespace в теге)
        id_elem = group_elem.find('{urn:1C.ru:commerceml_210}Ид')
        if id_elem is None:
            # Пробуем без namespace
            id_elem = group_elem.find('Ид')
        
        if id_elem is None or not id_elem.text:
            return groups
        
        external_id = id_elem.text.strip()
        
        # Наименование (пробуем с полным namespace в теге)
        name_elem = group_elem.find('{urn:1C.ru:commerceml_210}Наименование')
        if name_elem is None:
            # Пробуем без namespace
            name_elem = group_elem.find('Наименование')
        
        if name_elem is None or not name_elem.text:
            return groups
        
        name = name_elem.text.strip()
        
        # Создаем текущую группу
        group_data = {
            'external_id': external_id,
            'name': name,
        }
        if parent_id:
            group_data['parent_id'] = parent_id
        
        groups.append(group_data)
        
        # Ищем вложенные группы (элементы <Группа> внутри текущей <Группа>)
        child_group_elems = group_elem.findall('{urn:1C.ru:commerceml_210}Группа')
        if not child_group_elems:
            child_group_elems = group_elem.findall('Группа')
        
        for child_group_elem in child_group_elems:
            # Проверяем, что это полноценная группа с <Наименование>, а не просто ссылка
            child_name_elem = child_group_elem.find('{urn:1C.ru:commerceml_210}Наименование')
            if child_name_elem is None:
                child_name_elem = child_group_elem.find('Наименование')
            
            if child_name_elem is not None and child_name_elem.text:
                # Это вложенная группа - парсим рекурсивно
                nested_groups = self._parse_group_element(child_group_elem, namespaces, parent_id=external_id)
                groups.extend(nested_groups)
        
        return groups
    
    def parse_commerceml_xml(self, xml_content: bytes) -> List[Dict[str, Any]]:
        """
        Парсинг CommerceML XML из бинарных данных
        
        Args:
            xml_content: Бинарные данные XML файла
        
        Returns:
            Список товаров в формате словарей
        """
        try:
            # Парсим XML из байтов
            root = ET.fromstring(xml_content)
            
            # Определяем namespace CommerceML
            # В примере используется: xmlns="urn:1C.ru:commerceml_210"
            namespaces = {
                '': 'urn:1C.ru:commerceml_210',  # Базовый namespace
                'xs': 'http://www.w3.org/2001/XMLSchema',
                'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            }
            
            products = []
            
            # Ищем каталог товаров (с полным namespace)
            catalog = root.find('.//{urn:1C.ru:commerceml_210}Каталог')
            if catalog is None:
                # Пробуем без namespace
                catalog = root.find('.//Каталог')
            
            if catalog is None:
                logger.warning("Элемент Каталог не найден в XML")
                return products
            
            # Ищем раздел Товары в Каталоге
            products_section = catalog.find('{urn:1C.ru:commerceml_210}Товары')
            if products_section is None:
                products_section = catalog.find('Товары')
            
            # Ищем все товары
            product_elems = []
            if products_section is not None:
                # Ищем в секции Товары
                product_elems = products_section.findall('{urn:1C.ru:commerceml_210}Товар')
                if not product_elems:
                    product_elems = products_section.findall('Товар')
            else:
                # Если секции Товары нет, ищем Товар напрямую в Каталоге
                product_elems = catalog.findall('{urn:1C.ru:commerceml_210}Товар')
                if not product_elems:
                    product_elems = catalog.findall('Товар')
            
            # Если не нашли в Каталоге, ищем везде
            if not product_elems:
                product_elems = root.findall('.//{urn:1C.ru:commerceml_210}Товар')
                if not product_elems:
                    product_elems = root.findall('.//Товар')
            
            logger.info(f"Найдено {len(product_elems)} товаров в XML")
            
            # Убираем дубликаты по ID
            seen_ids = set()
            unique_products = []
            for elem in product_elems:
                # Ищем Ид с полным namespace
                product_id_elem = elem.find('{urn:1C.ru:commerceml_210}Ид')
                if product_id_elem is None:
                    product_id_elem = elem.find('Ид')
                
                if product_id_elem is not None and product_id_elem.text:
                    product_id = product_id_elem.text.strip()
                    if product_id and product_id not in seen_ids:
                        seen_ids.add(product_id)
                        unique_products.append(elem)
            
            logger.info(f"После удаления дубликатов: {len(unique_products)} товаров")
            
            # Парсим каждый товар
            for product_elem in unique_products:
                try:
                    product_data = self._parse_product_element(product_elem, namespaces)
                    if product_data:
                        products.append(product_data)
                except Exception as e:
                    logger.warning(f"Ошибка парсинга товара: {e}")
                    continue
            
            logger.info(f"Успешно распарсено {len(products)} товаров из CommerceML XML")
            return products
            
        except ET.ParseError as e:
            logger.error(f"Ошибка парсинга XML: {e}")
            # Пытаемся показать начало файла для отладки
            try:
                preview = xml_content[:500].decode('utf-8', errors='ignore')
                logger.error(f"Начало XML файла: {preview}")
            except:
                pass
            raise ValueError(f"Неверный формат XML файла: {str(e)}")
        except Exception as e:
            logger.error(f"Ошибка при обработке CommerceML XML: {e}", exc_info=True)
            raise
    
    def _parse_product_element(self, product_elem: ET.Element, namespaces: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Парсит элемент товара из XML"""
        product_data = {}
        
        # Функция для поиска элемента с namespace и без
        def find_elem(parent, tag):
            elem = parent.find(f'{{urn:1C.ru:commerceml_210}}{tag}')
            if elem is None:
                elem = parent.find(tag)
            return elem
        
        # Ид товара (уникальный идентификатор)
        id_elem = find_elem(product_elem, 'Ид')
        if id_elem is not None and id_elem.text:
            product_data['id'] = id_elem.text.strip()
            product_data['external_id'] = id_elem.text.strip()
        
        # Артикул
        article_elem = find_elem(product_elem, 'Артикул')
        if article_elem is not None and article_elem.text:
            product_data['article'] = article_elem.text.strip()
            product_data['external_code'] = article_elem.text.strip()
        
        # Код (внутренний код 1С)
        code_elem = find_elem(product_elem, 'Код')
        if code_elem is not None and code_elem.text:
            product_data['code_1c'] = code_elem.text.strip()
        
        # Наименование
        name_elem = find_elem(product_elem, 'Наименование')
        if name_elem is not None and name_elem.text:
            product_data['name'] = name_elem.text.strip()
        
        # Описание
        desc_elem = find_elem(product_elem, 'Описание')
        if desc_elem is not None and desc_elem.text:
            # Декодируем HTML entities если есть
            description = desc_elem.text.strip()
            # Заменяем HTML entities
            description = description.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
            product_data['description'] = description
            product_data['full_description'] = description
        
        # Картинки (изображения)
        images = []
        # Ищем все элементы Картинка (может быть несколько)
        image_elems = product_elem.findall('{urn:1C.ru:commerceml_210}Картинка')
        if not image_elems:
            image_elems = product_elem.findall('Картинка')
        
        for img_elem in image_elems:
            if img_elem.text:
                img_url = img_elem.text.strip()
                if img_url:
                    images.append(img_url)
        
        if images:
            product_data['images'] = images
            logger.debug(f"Найдено {len(images)} изображений для товара {product_data.get('name', 'unknown')}")
        
        # Группы (категории) - ссылка на группу каталога
        # Товар может быть в нескольких группах
        groups_elem = find_elem(product_elem, 'Группы')
        group_ids = []
        if groups_elem is not None:
            # Ищем элементы Ид внутри Группы
            for group_id_elem in groups_elem.findall('{urn:1C.ru:commerceml_210}Ид') or groups_elem.findall('Ид'):
                if group_id_elem.text:
                    group_ids.append(group_id_elem.text.strip())
        
        # Категория (если указана напрямую) - добавляем к группам
        category_elem = find_elem(product_elem, 'Категория')
        if category_elem is not None and category_elem.text:
            category_id = category_elem.text.strip()
            if category_id not in group_ids:
                group_ids.append(category_id)
        
        # Сохраняем все группы товара
        if group_ids:
            product_data['groups_external_ids'] = group_ids
            # Для обратной совместимости сохраняем первую группу как category_external_id
            product_data['category_external_id'] = group_ids[0]
        
        # Штрихкод
        barcode_elem = find_elem(product_elem, 'Штрихкод')
        if barcode_elem is not None and barcode_elem.text:
            product_data['barcode'] = barcode_elem.text.strip()
        
        # Характеристики товара (ХарактеристикиТовара) - основные характеристики
        characteristics = {}
        char_elem = find_elem(product_elem, 'ХарактеристикиТовара')
        if char_elem is not None:
            char_item_elems = char_elem.findall('{urn:1C.ru:commerceml_210}ХарактеристикаТовара')
            if not char_item_elems:
                char_item_elems = char_elem.findall('ХарактеристикаТовара')
            
            for char_item_elem in char_item_elems:
                char_name_elem = find_elem(char_item_elem, 'Наименование')
                char_value_elem = find_elem(char_item_elem, 'Значение')
                
                if char_name_elem is not None and char_value_elem is not None:
                    char_name = char_name_elem.text.strip() if char_name_elem.text else None
                    char_value = char_value_elem.text.strip() if char_value_elem.text else None
                    
                    if char_name and char_value:
                        characteristics[char_name] = char_value
        
        # Значения свойств (ЗначенияСвойств) - дополнительные свойства
        props_elem = find_elem(product_elem, 'ЗначенияСвойств')
        specifications = {}
        characteristic_id = None
        
        if props_elem is not None:
            prop_elems = props_elem.findall('{urn:1C.ru:commerceml_210}ЗначенияСвойства')
            if not prop_elems:
                prop_elems = props_elem.findall('ЗначенияСвойства')
            
            for prop_elem in prop_elems:
                prop_id_elem = find_elem(prop_elem, 'Ид')
                prop_value_elem = find_elem(prop_elem, 'Значение')
                
                if prop_id_elem is not None and prop_value_elem is not None:
                    prop_id = prop_id_elem.text.strip() if prop_id_elem.text else None
                    prop_value = prop_value_elem.text.strip() if prop_value_elem.text else None
                    
                    if prop_id and prop_value:
                        # Сохраняем ID характеристики (если это характеристика товара)
                        # В CommerceML характеристика обычно имеет определенный ID свойства
                        specifications[prop_id] = prop_value
                        
                        # Если это характеристика товара (не просто свойство), сохраняем её ID
                        # Обычно характеристика определяется по типу свойства
                        # Пока сохраняем все свойства, позже можно будет определить, какое из них характеристика
        
        # Объединяем характеристики и свойства в specifications
        if characteristics:
            # Добавляем характеристики в specifications с префиксом для различения
            for char_name, char_value in characteristics.items():
                specifications[f"char_{char_name}"] = char_value
            # Также сохраняем отдельно для удобства
            product_data['characteristics'] = characteristics
        
        # Сохраняем ID характеристики, если он есть в external_id (для вариантов)
        # Это будет использоваться для связи с предложениями в offers.xml
        
        if specifications:
            product_data['specifications'] = specifications
            # Сохраняем ID первой характеристики, если есть (для вариантов)
            if characteristic_id:
                product_data['characteristic_id'] = characteristic_id
        
        # Значения реквизитов
        requisites_elem = find_elem(product_elem, 'ЗначенияРеквизитов')
        if requisites_elem is not None:
            req_elems = requisites_elem.findall('{urn:1C.ru:commerceml_210}ЗначениеРеквизита')
            if not req_elems:
                req_elems = requisites_elem.findall('ЗначениеРеквизита')
            
            for req_elem in req_elems:
                name_elem = find_elem(req_elem, 'Наименование')
                value_elem = find_elem(req_elem, 'Значение')
                
                if name_elem is not None and value_elem is not None:
                    req_name = name_elem.text.strip() if name_elem.text else None
                    req_value = value_elem.text.strip() if value_elem.text else None
                    
                    if req_name and req_value:
                        # Сохраняем важные реквизиты
                        if 'Полное наименование' in req_name:
                            product_data['full_name'] = req_value
                        elif 'ВидНоменклатуры' in req_name:
                            product_data['product_type'] = req_value
        
        # Статус активности
        product_data['is_active'] = True
        
        # Добавляем товар только если есть хотя бы ID или артикул
        if product_data.get('id') or product_data.get('article'):
            return product_data
        
        return None
    
    def parse_offers_xml(self, xml_content: bytes) -> Dict[str, Dict[str, Any]]:
        """
        Парсинг offers.xml для получения цен, остатков и артикулов характеристик
        
        Args:
            xml_content: Бинарные данные offers.xml файла
        
        Returns:
            Словарь {offer_id: {price, quantity, article, barcode, ...}}
            где offer_id может быть "product_id" или "product_id#characteristic_id"
        """
        try:
            root = ET.fromstring(xml_content)
            offers_dict = {}
            
            # Ищем раздел Предложения
            offers_section = root.find('.//{urn:1C.ru:commerceml_210}Предложения')
            if offers_section is None:
                offers_section = root.find('.//Предложения')
            
            if offers_section is None:
                logger.warning("Раздел Предложения не найден в offers.xml")
                # Пробуем найти все Предложение напрямую в корне
                offer_elems = root.findall('.//{urn:1C.ru:commerceml_210}Предложение')
                if not offer_elems:
                    offer_elems = root.findall('.//Предложение')
                logger.info(f"Найдено {len(offer_elems)} предложений напрямую в корне XML")
            else:
                # Парсим все предложения из раздела Предложения
                # Используем .// для поиска всех вложенных Предложение, а не только прямых дочерних
                offer_elems = offers_section.findall('.//{urn:1C.ru:commerceml_210}Предложение')
                if not offer_elems:
                    offer_elems = offers_section.findall('.//Предложение')
                
                # Если не нашли вложенные, пробуем прямые дочерние
                if not offer_elems:
                    offer_elems = offers_section.findall('{urn:1C.ru:commerceml_210}Предложение')
                    if not offer_elems:
                        offer_elems = offers_section.findall('Предложение')
                
                logger.info(f"Найдено {len(offer_elems)} предложений в разделе Предложения")
            
            # Если всё ещё не нашли, пробуем найти все Предложение в документе
            if not offer_elems:
                offer_elems = root.findall('.//{urn:1C.ru:commerceml_210}Предложение')
                if not offer_elems:
                    offer_elems = root.findall('.//Предложение')
                logger.info(f"Найдено {len(offer_elems)} предложений во всём документе")
            
            for offer_elem in offer_elems:
                try:
                    offer_data = self._parse_offer_element(offer_elem)
                    if offer_data and offer_data.get('id'):
                        offers_dict[offer_data['id']] = offer_data
                    else:
                        # Логируем, если предложение не распарсилось
                        id_elem = offer_elem.find('{urn:1C.ru:commerceml_210}Ид')
                        if id_elem is None:
                            id_elem = offer_elem.find('Ид')
                        offer_id = id_elem.text.strip() if id_elem is not None and id_elem.text else "unknown"
                        logger.warning(f"Предложение {offer_id} не распарсено или не имеет ID")
                except Exception as e:
                    logger.warning(f"Ошибка парсинга предложения: {e}", exc_info=True)
                    continue
            
            logger.info(f"Успешно распарсено {len(offers_dict)} предложений из {len(offer_elems)} найденных в offers.xml")
            
            # Если распарсено меньше, чем найдено, логируем предупреждение
            if len(offers_dict) < len(offer_elems):
                logger.warning(f"Внимание: найдено {len(offer_elems)} предложений, но распарсено только {len(offers_dict)}. Возможно, некоторые предложения не имеют ID или произошла ошибка парсинга.")
            
            return offers_dict
            
        except ET.ParseError as e:
            logger.error(f"Ошибка парсинга offers.xml: {e}")
            raise ValueError(f"Неверный формат offers.xml: {str(e)}")
        except Exception as e:
            logger.error(f"Ошибка при обработке offers.xml: {e}", exc_info=True)
            raise
    
    def _parse_offer_element(self, offer_elem: ET.Element) -> Optional[Dict[str, Any]]:
        """Парсит элемент предложения из offers.xml"""
        offer_data = {}
        
        def find_elem(parent, tag):
            elem = parent.find(f'{{urn:1C.ru:commerceml_210}}{tag}')
            if elem is None:
                elem = parent.find(tag)
            return elem
        
        # Ид предложения (может быть product_id или product_id#characteristic_id)
        id_elem = find_elem(offer_elem, 'Ид')
        if id_elem is not None and id_elem.text:
            offer_id = id_elem.text.strip()
            offer_data['id'] = offer_id
            
            # Разделяем на product_id и characteristic_id если есть #
            if '#' in offer_id:
                parts = offer_id.split('#', 1)
                offer_data['product_id'] = parts[0]
                offer_data['characteristic_id'] = parts[1]
            else:
                offer_data['product_id'] = offer_id
                offer_data['characteristic_id'] = None
        
        # Артикул (артикул характеристики, если есть)
        article_elem = find_elem(offer_elem, 'Артикул')
        if article_elem is not None and article_elem.text:
            offer_data['article'] = article_elem.text.strip()
        
        # Штрихкод
        barcode_elem = find_elem(offer_elem, 'Штрихкод')
        if barcode_elem is not None and barcode_elem.text:
            offer_data['barcode'] = barcode_elem.text.strip()
        
        # Характеристики товара (из offers.xml)
        characteristics = {}
        char_elem = find_elem(offer_elem, 'ХарактеристикиТовара')
        if char_elem is not None:
            char_item_elems = char_elem.findall('{urn:1C.ru:commerceml_210}ХарактеристикаТовара')
            if not char_item_elems:
                char_item_elems = char_elem.findall('ХарактеристикаТовара')
            
            for char_item_elem in char_item_elems:
                char_name_elem = find_elem(char_item_elem, 'Наименование')
                char_value_elem = find_elem(char_item_elem, 'Значение')
                
                if char_name_elem is not None and char_value_elem is not None:
                    char_name = char_name_elem.text.strip() if char_name_elem.text else None
                    char_value = char_value_elem.text.strip() if char_value_elem.text else None
                    
                    if char_name and char_value:
                        characteristics[char_name] = char_value
        
        if characteristics:
            offer_data['characteristics'] = characteristics
            logger.debug(f"Найдено {len(characteristics)} характеристик для предложения {offer_data.get('id', 'unknown')}: {list(characteristics.keys())}")
        
        # Цены
        prices_elem = find_elem(offer_elem, 'Цены')
        if prices_elem is not None:
            price_elems = prices_elem.findall('{urn:1C.ru:commerceml_210}Цена')
            if not price_elems:
                price_elems = prices_elem.findall('Цена')
            
            # Берем первую цену (обычно розничная)
            for price_elem in price_elems:
                price_value_elem = find_elem(price_elem, 'ЦенаЗаЕдиницу')
                if price_value_elem is not None and price_value_elem.text:
                    try:
                        price_value = float(price_value_elem.text.strip())
                        # Цены из 1С в рублях, конвертируем в копейки
                        # Например: 7490 руб = 749000 копеек
                        offer_data['price'] = int(price_value * 100)
                        break
                    except (ValueError, TypeError):
                        continue
        
        # Остатки (общее количество)
        stocks_elem = find_elem(offer_elem, 'Остатки')
        if stocks_elem is not None:
            stock_elems = stocks_elem.findall('{urn:1C.ru:commerceml_210}Остаток')
            if not stock_elems:
                stock_elems = stocks_elem.findall('Остаток')
            
            total_quantity = 0
            for stock_elem in stock_elems:
                quantity_elem = find_elem(stock_elem, 'Количество')
                if quantity_elem is not None and quantity_elem.text:
                    try:
                        quantity = float(quantity_elem.text.strip())
                        total_quantity += quantity
                    except (ValueError, TypeError):
                        continue
            
            offer_data['quantity'] = int(total_quantity)
        
        # Остатки по складам (элементы <Склад>)
        store_stocks = {}
        store_elems = offer_elem.findall('{urn:1C.ru:commerceml_210}Склад')
        if not store_elems:
            store_elems = offer_elem.findall('Склад')
        
        for store_elem in store_elems:
            store_id_attr = store_elem.get('ИдСклада')
            quantity_attr = store_elem.get('КоличествоНаСкладе')
            if store_id_attr and quantity_attr:
                try:
                    store_stocks[store_id_attr] = float(quantity_attr)
                except (ValueError, TypeError):
                    pass
        
        if store_stocks:
            offer_data['store_stocks'] = store_stocks
            # Если общее количество не было найдено, суммируем по складам
            if 'quantity' not in offer_data:
                offer_data['quantity'] = int(sum(store_stocks.values()))
        
        # Картинки (изображения варианта) - может быть несколько элементов <Картинка>
        images = []
        # Ищем все элементы Картинка (может быть несколько)
        image_elems = offer_elem.findall('{urn:1C.ru:commerceml_210}Картинка')
        if not image_elems:
            image_elems = offer_elem.findall('Картинка')
        
        for img_elem in image_elems:
            if img_elem.text:
                img_url = img_elem.text.strip()
                if img_url and img_url not in images:
                    images.append(img_url)
        
        if images:
            offer_data['images'] = images
            offer_data['image'] = images[0]  # Первая картинка для обратной совместимости
            logger.debug(f"Найдено {len(images)} изображений для предложения {offer_data.get('id', 'unknown')}")
        
        return offer_data if offer_data.get('id') else None
    
    def parse_stores_from_offers_xml(self, xml_content: bytes) -> List[Dict[str, Any]]:
        """
        Парсинг раздела Склады из offers.xml для получения информации о магазинах/складах
        
        Args:
            xml_content: Бинарные данные offers.xml файла
        
        Returns:
            Список складов [{'external_id': '...', 'name': '...'}, ...]
        """
        stores = []
        
        try:
            root = ET.fromstring(xml_content)
            
            def find_elem(parent, tag):
                elem = parent.find(f'{{urn:1C.ru:commerceml_210}}{tag}')
                if elem is None:
                    elem = parent.find(tag)
                return elem
            
            # Ищем раздел Склады
            stores_section = root.find('.//{urn:1C.ru:commerceml_210}Склады')
            if stores_section is None:
                stores_section = root.find('.//Склады')
            
            if stores_section is None:
                return stores
            
            # Парсим все склады
            store_elems = stores_section.findall('{urn:1C.ru:commerceml_210}Склад')
            if not store_elems:
                store_elems = stores_section.findall('Склад')
            
            for store_elem in store_elems:
                try:
                    # Ид склада (external_id)
                    id_elem = find_elem(store_elem, 'Ид')
                    if id_elem is None or not id_elem.text:
                        continue
                    
                    external_id = id_elem.text.strip()
                    
                    # Наименование склада
                    name_elem = find_elem(store_elem, 'Наименование')
                    name = name_elem.text.strip() if name_elem is not None and name_elem.text else external_id
                    
                    stores.append({
                        'external_id': external_id,
                        'name': name
                    })
                    
                except Exception as e:
                    logger.warning(f"Ошибка парсинга склада: {e}")
                    continue
            
            logger.info(f"Распарсено {len(stores)} складов из offers.xml")
            return stores
            
        except ET.ParseError as e:
            logger.error(f"Ошибка парсинга offers.xml (раздел Склады): {e}")
            return stores
        except Exception as e:
            logger.error(f"Ошибка при обработке раздела Склады в offers.xml: {e}", exc_info=True)
            return stores
    
    async def load_and_parse_xml(self, url: str) -> List[Dict[str, Any]]:
        """
        Загружает XML по URL и парсит его
        
        Args:
            url: URL для скачивания XML файла
        
        Returns:
            Список товаров в формате словарей
        """
        xml_content = await self.download_xml_from_url(url)
        return self.parse_commerceml_xml(xml_content)
    
    async def load_and_parse_offers(self, url: str) -> Dict[str, Dict[str, Any]]:
        """
        Загружает offers.xml по URL и парсит его
        
        Args:
            url: URL для скачивания offers.xml файла
        
        Returns:
            Словарь предложений {offer_id: {price, quantity, article, ...}}
        """
        xml_content = await self.download_xml_from_url(url)
        return self.parse_offers_xml(xml_content)
