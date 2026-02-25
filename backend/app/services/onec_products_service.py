"""
Сервис для работы с каталогом товаров из 1С через CommerceML XML.
OData методы для каталога удалены. Используется только XML импорт.
"""
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Callable, Awaitable

from sqlalchemy import or_, select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.product import Product
from app.models.catalog_section import CatalogSection
from app.models.product_stock import ProductStock
from app.models.product_catalog_section import ProductCatalogSection
from app.services.onec_images_service import OneCImagesService
from app.services.yml_images_service import YMLImagesService

logger = logging.getLogger(__name__)


class OneCProductsService:
    """
    Сервис для импорта товаров из CommerceML XML.
    OData методы удалены - используется только XML импорт.
    """
    def __init__(
        self,
        db: AsyncSession,
    ):
        self.db = db

    # ============================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ (UTILITY METHODS)
    # ============================================================================

    def _extract_ref_key(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, dict):
            return (
                value.get("Ref_Key")
                or value.get("ref_key")
                or value.get("Key")
                or value.get("key")
            )
        return str(value)

    def _get_first(self, item: Dict[str, Any], keys: Iterable[str]) -> Optional[Any]:
        for key in keys:
            if key in item and item[key] not in (None, ""):
                return item[key]
        return None

    def _as_string(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, dict):
            return (
                value.get("Description")
                or value.get("description")
                or value.get("Name")
                or value.get("name")
                or value.get("Presentation")
                or value.get("presentation")
            )
        return str(value)

    def _normalize_price(self, value: Any) -> Optional[int]:
        """
        Нормализует цену из 1С.
        В 1С цены передаются в рублях (например, 7490 = 7490 руб = 749000 копеек).
        Возвращаем цену в копейках как int.
        """
        if value in (None, ""):
            return None
        try:
            number = float(value)
        except (ValueError, TypeError):
            return None
        # Цены из 1С в рублях, конвертируем в копейки (умножаем на 100)
        return int(round(number * 100))

    def _is_empty_guid(self, value: Any) -> bool:
        if value is None:
            return False
        return str(value).strip() == "00000000-0000-0000-0000-000000000000"

    def _is_base64(self, value: str) -> bool:
        if len(value) < 80:
            return False
        return bool(re.fullmatch(r"[A-Za-z0-9+/=\n\r]+", value))

    def _extract_images(self, item: Dict[str, Any]) -> List[str]:
        raw = self._get_first(
            item,
            [
                "images",
                "image_urls",
                "image",
                "Image",
                "Picture",
                "Фотография",
                "Изображение",
                "ФайлКартинки",
            ],
        )
        if not raw:
            return []

        images: List[str] = []
        if isinstance(raw, list):
            candidates = raw
        else:
            candidates = [raw]

        for candidate in candidates:
            if isinstance(candidate, dict):
                candidate = candidate.get("url") or candidate.get("href") or candidate.get("link")
            if not candidate:
                continue
            if isinstance(candidate, str):
                if candidate.startswith("http") or candidate.startswith("data:"):
                    images.append(candidate)
                elif self._is_base64(candidate):
                    images.append(f"data:image/jpeg;base64,{candidate}")
        return images

    # ============================================================================
    # МЕТОДЫ ЗАГРУЗКИ ИЗОБРАЖЕНИЙ
    # ============================================================================

    async def _load_product_images_direct(
        self,
        images_list: List[str],
        external_id: Optional[str],
        article: Optional[str],
        characteristic_ref_key: Optional[str] = None
    ) -> None:
        """
        Загрузить изображения для товара из 1С и YML напрямую в список.
        
        Args:
            images_list: Список для добавления изображений
            external_id: Ref_Key товара в 1С
            article: Артикул товара
            characteristic_ref_key: Ref_Key характеристики (опционально)
        """
        # 1. Пытаемся загрузить из 1С через mediaresource
        if external_id:
            try:
                async with OneCImagesService() as images_service:
                    onec_images = await images_service.get_images_for_product(
                        product_ref_key=external_id,
                        characteristic_ref_key=characteristic_ref_key
                    )
                    if onec_images:
                        images_list.extend(onec_images)
                        logger.info(f"Загружено {len(onec_images)} изображений из 1С (article: {article})")
            except Exception as e:
                logger.warning(f"Не удалось загрузить изображения из 1С (article: {article}): {e}")
        
        # 2. Если изображений из 1С нет, пытаемся загрузить из YML
        if not images_list and article:
            try:
                async with YMLImagesService() as yml_service:
                    yml_images = await yml_service.get_images_by_article(article)
                    if yml_images:
                        images_list.extend(yml_images)
                        logger.info(f"Загружено {len(yml_images)} изображений из YML (article: {article})")
            except Exception as e:
                logger.warning(f"Не удалось загрузить изображения из YML (article: {article}): {e}")

    async def _load_product_images(
        self,
        product: Product,
        external_id: Optional[str],
        article: Optional[str]
    ) -> None:
        """
        Загрузить изображения для товара из 1С и YML.
        Приоритет: 1С (через mediaresource), затем YML.
        
        Если у товара уже есть изображения, загружаются только новые (которых нет в базе).
        
        Args:
            product: Объект товара
            external_id: Ref_Key товара в 1С
            article: Артикул товара
        """
        # Получаем существующие изображения для сравнения
        existing_images = set(product.images) if product.images else set()
        
        images: List[str] = []
        
        # Получаем Ref_Key характеристики из specifications, если есть
        characteristic_ref_key = None
        if product.specifications and isinstance(product.specifications, dict):
            char_ref = product.specifications.get("characteristic_ref_key")
            if char_ref:
                characteristic_ref_key = char_ref
        
        # Если товар сам является характеристикой (имеет characteristic_ref_key = external_id),
        # то ищем изображения для характеристики, а не для основной карточки
        if characteristic_ref_key == external_id:
            # Это характеристика - ищем изображения только для неё
            await self._load_product_images_direct(images, None, article, characteristic_ref_key)
        else:
            # Это основная карточка - ищем изображения для неё и для характеристики (если есть)
            await self._load_product_images_direct(images, external_id, article, characteristic_ref_key)
        
        # Фильтруем - оставляем только новые изображения, которых еще нет
        new_images = [img for img in images if img not in existing_images]
        
        if new_images:
            # Добавляем новые изображения к существующим
            updated_images = list(existing_images) + new_images
            product.images = updated_images
            logger.info(f"Добавлено {len(new_images)} новых изображений для товара {product.name} (было: {len(existing_images)}, стало: {len(updated_images)})")
        elif images:
            # Все изображения уже есть
            logger.debug(f"У товара {product.name} (article: {article}) уже есть все {len(existing_images)} изображений, новых не найдено")
        elif existing_images:
            # Изображения не найдены в 1С/YML, но есть в базе - оставляем как есть
            logger.debug(f"Изображения для товара {product.name} (article: {article}) не найдены в 1С/YML, оставляем существующие {len(existing_images)} изображений")

    # ============================================================================
    # XML ИМПОРТ ГРУПП И ТОВАРОВ (ОСНОВНЫЕ МЕТОДЫ)
    # ============================================================================

    async def import_groups_from_xml(
        self,
        groups_data: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Импорт групп каталога из данных, полученных из CommerceML XML.
        
        Args:
            groups_data: Список словарей с данными групп из XML
        
        Returns:
            Словарь со статистикой импорта
        """
        created = 0
        updated = 0
        skipped = 0
        errors: List[str] = []
        total = len(groups_data)
        
        # Дедупликация по external_id перед импортом (как было в OData версии)
        unique_groups = {}
        for group in groups_data:
            ext_id = group.get('external_id')
            if ext_id and ext_id not in unique_groups:
                unique_groups[ext_id] = group
        
        deduplicated_groups = list(unique_groups.values())
        logger.info(f"Групп после дедупликации: {len(deduplicated_groups)} из {total}")
        
        for group_data in deduplicated_groups:
            try:
                external_id = group_data.get("external_id")
                name = group_data.get("name")
                
                if not external_id or not name:
                    skipped += 1
                    continue
                
                # Ищем существующую группу по external_id
                result = await self.db.execute(
                    select(CatalogSection).where(CatalogSection.external_id == external_id)
                )
                existing_group = result.scalar_one_or_none()
                
                if existing_group:
                    # Обновляем название группы
                    old_name = existing_group.name
                    existing_group.name = name
                    if group_data.get("parent_id"):
                        existing_group.parent_external_id = group_data["parent_id"]
                    existing_group.updated_at = datetime.now(timezone.utc)
                    updated += 1
                    if old_name != name:
                        logger.info(f"Обновлена группа: external_id={external_id}, старое название='{old_name}', новое название='{name}'")
                else:
                    # Создаем новую группу
                    new_group = CatalogSection(
                        external_id=external_id,
                        name=name,
                        parent_external_id=group_data.get("parent_id"),
                        is_active=True,
                        sync_status="synced",
                    )
                    self.db.add(new_group)
                    created += 1
                    logger.info(f"Создана новая группа (раздел каталога): external_id={external_id}, название='{name}'")
                
                # Коммитим каждые 20 групп
                if (created + updated) % 20 == 0:
                    await self.db.commit()
                    
            except Exception as exc:
                error_msg = f"Ошибка импорта группы {group_data.get('name', 'Unknown')}: {exc}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)
        
        await self.db.commit()
        
        return {
            "total": len(deduplicated_groups),
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors[:10],
            "error_count": len(errors),
        }

    async def import_products_from_xml(
        self,
        products_data: List[Dict[str, Any]],
        offers_data: Optional[Dict[str, Dict[str, Any]]] = None,
        update_existing: bool = True,
        progress_callback: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        Импорт товаров из данных, полученных из CommerceML XML.
        
        Args:
            products_data: Список словарей с данными товаров из XML
            offers_data: Словарь предложений из offers.xml {offer_id: {price, quantity, article, ...}}
            update_existing: Обновлять существующие товары
            progress_callback: Callback для обновления прогресса (current, total)
        
        Returns:
            Словарь со статистикой импорта
        """
        created = 0
        updated = 0
        skipped = 0
        variants_created = 0
        errors: List[str] = []
        total = len(products_data)
        
        # Группируем предложения по product_id для быстрого поиска
        offers_by_product: Dict[str, List[Dict[str, Any]]] = {}
        if offers_data:
            for offer_id, offer_info in offers_data.items():
                product_id = offer_info.get('product_id')
                if product_id:
                    if product_id not in offers_by_product:
                        offers_by_product[product_id] = []
                    offers_by_product[product_id].append({
                        **offer_info,
                        'id': offer_id,  # Используем 'id' для совместимости с кодом вариантов
                    })
        
        for idx, product_data in enumerate(products_data):
            # Проверяем состояние транзакции перед началом обработки товара
            try:
                # Пробуем выполнить простой запрос, чтобы проверить состояние транзакции
                await self.db.execute(select(1))
            except Exception as transaction_error:
                # Если транзакция в состоянии ошибки, делаем rollback
                logger.warning(f"Транзакция в состоянии ошибки, выполняем rollback перед товаром {idx + 1}: {transaction_error}")
                try:
                    await self.db.rollback()
                except Exception as rollback_error:
                    logger.error(f"Ошибка при rollback: {rollback_error}")
            
            try:
                # Маппим данные из XML в формат Product
                external_id = product_data.get("id") or product_data.get("external_id")
                article = product_data.get("article") or product_data.get("external_code")
                
                if not external_id and not article:
                    skipped += 1
                    continue
                
                # Ищем существующий товар по external_id или article
                existing_product = None
                try:
                    if external_id:
                        result = await self.db.execute(
                            select(Product).where(Product.external_id == external_id)
                        )
                        existing_product = result.scalar_one_or_none()
                except Exception as query_error:
                    # Если транзакция в состоянии ошибки, делаем rollback
                    logger.warning(f"Ошибка при поиске товара по external_id {external_id}: {query_error}")
                    try:
                        await self.db.rollback()
                        # Повторяем запрос после rollback
                        if external_id:
                            result = await self.db.execute(
                                select(Product).where(Product.external_id == external_id)
                            )
                            existing_product = result.scalar_one_or_none()
                    except Exception as retry_error:
                        logger.error(f"Ошибка при повторном запросе после rollback: {retry_error}")
                        raise
                
                if not existing_product and article:
                    try:
                        result = await self.db.execute(
                            select(Product).where(
                                or_(
                                    Product.article == article,
                                    Product.external_code == article
                                )
                            )
                        )
                        existing_product = result.scalar_one_or_none()
                    except Exception as query_error:
                        # Если транзакция в состоянии ошибки, делаем rollback
                        logger.warning(f"Ошибка при поиске товара по article {article}: {query_error}")
                        try:
                            await self.db.rollback()
                            # Повторяем запрос после rollback
                            if article:
                                result = await self.db.execute(
                                    select(Product).where(
                                        or_(
                                            Product.article == article,
                                            Product.external_code == article
                                        )
                                    )
                                )
                                existing_product = result.scalar_one_or_none()
                        except Exception as retry_error:
                            logger.error(f"Ошибка при повторном запросе после rollback: {retry_error}")
                            raise
                
                # Ищем предложения для этого товара
                product_offers = offers_by_product.get(external_id, []) if external_id else []
                
                # Определяем основное предложение (без характеристики) и варианты (с характеристиками)
                main_offer = None
                variant_offers = []
                
                for offer in product_offers:
                    # Проверяем, есть ли characteristic_id (вариант) или # в id (вариант)
                    offer_id = offer.get('id', '')
                    characteristic_id = offer.get('characteristic_id')
                    
                    # Если в id есть #, это вариант
                    if '#' in offer_id or characteristic_id:
                        variant_offers.append(offer)
                        logger.debug(f"Найден вариант: id={offer_id}, characteristic_id={characteristic_id}, article={offer.get('article')}")
                    else:
                        main_offer = offer
                        logger.debug(f"Найдено основное предложение: id={offer_id}, article={offer.get('article')}")
                
                # Если нет основного предложения, берем первое (если есть)
                if not main_offer and product_offers:
                    # Если все предложения с характеристиками, берем первое как основное
                    if variant_offers:
                        main_offer = variant_offers[0]
                        variant_offers = variant_offers[1:]
                
                # Маппим данные основного товара
                mapped = {
                    "name": product_data.get("name", "Unnamed product"),
                    "article": article,
                    "external_id": external_id,
                    "external_code": product_data.get("code_1c"),
                    "description": product_data.get("description"),
                    "full_description": product_data.get("full_description") or product_data.get("description"),
                    "price": main_offer.get("price", 0) if main_offer else 0,
                    "is_active": product_data.get("is_active", True),
                    "sync_status": "synced",
                    "sync_metadata": {
                        "source": "commerceml_xml",
                        "imported_at": datetime.now(timezone.utc).isoformat(),
                    },
                }
                
                # Изображения
                if product_data.get("images"):
                    mapped["images"] = product_data["images"]
                
                # Извлекаем группы каталога для товара (может быть несколько групп)
                groups_external_ids = product_data.get('groups_external_ids', [])
                # Если groups_external_ids не указаны, но есть category_external_id, используем его
                if not groups_external_ids and product_data.get('category_external_id'):
                    groups_external_ids = [product_data['category_external_id']]
                
                # Категория (используем первую группу для обратной совместимости)
                if groups_external_ids:
                    category_external_id = groups_external_ids[0]
                elif product_data.get("category_external_id"):
                    category_external_id = product_data["category_external_id"]
                else:
                    category_external_id = None
                
                if category_external_id:
                    try:
                        # Ищем раздел каталога по external_id
                        section_result = await self.db.execute(
                            select(CatalogSection).where(
                                CatalogSection.external_id == category_external_id
                            )
                        )
                        section = section_result.scalar_one_or_none()
                        
                        # Если раздел не найден, возможно это вложенная группа
                        # Пробуем найти родительский раздел или использовать fallback на SALE/AGAFI
                        if not section:
                            # Сначала пробуем найти любой раздел из основных (SALE, AGAFI)
                            # Это fallback для случаев, когда группа не была импортирована
                            # Все товары должны быть в SALE или AGAFI согласно требованиям
                            fallback_sections_result = await self.db.execute(
                                select(CatalogSection).where(
                                    CatalogSection.name.in_(["SALE", "AGAFI", "AGafi"])
                                ).limit(1)
                            )
                            fallback_section = fallback_sections_result.scalar_one_or_none()
                            if fallback_section:
                                section = fallback_section
                                logger.warning(
                                    f"Раздел каталога с external_id={category_external_id} не найден для товара {product_data.get('name', 'Unknown')}. "
                                    f"Используется fallback раздел '{fallback_section.name}' (все товары должны быть в SALE или AGAFI)"
                                )
                            else:
                                # Если раздел не найден, проверяем, есть ли вообще разделы в базе
                                all_sections_result = await self.db.execute(
                                    select(func.count(CatalogSection.id))
                                )
                                total_sections = all_sections_result.scalar() or 0
                                
                                if total_sections == 0:
                                    logger.warning(f"В базе данных нет разделов каталога. Убедитесь, что группы были импортированы перед товарами.")
                                else:
                                    # Проверяем, есть ли похожие external_id
                                    similar_sections_result = await self.db.execute(
                                        select(CatalogSection.external_id, CatalogSection.name).limit(5)
                                    )
                                    sample_sections = [(row[0], row[1]) for row in similar_sections_result]
                                    logger.warning(
                                        f"Раздел каталога с external_id={category_external_id} не найден для товара {product_data.get('name', 'Unknown')}. "
                                        f"Всего разделов в БД: {total_sections}. Примеры external_id: {[s[0] for s in sample_sections[:3]]}"
                                    )
                        
                        if section:
                            mapped["category"] = section.name
                            logger.info(f"✓ Найден раздел каталога '{section.name}' (external_id={section.external_id}) для товара {product_data.get('name', 'Unknown')} (category_external_id={category_external_id})")
                    except Exception as section_error:
                        # Если транзакция в состоянии ошибки, делаем rollback
                        await self.db.rollback()
                        logger.warning(f"Ошибка при поиске категории {product_data.get('category_external_id')}, rollback выполнен: {section_error}")
                
                # Если категория не установлена, используем fallback на SALE или AGAFI
                if not mapped.get("category"):
                    try:
                        fallback_sections_result = await self.db.execute(
                            select(CatalogSection).where(
                                CatalogSection.name.in_(["SALE", "AGAFI", "AGafi"])
                            ).limit(1)
                        )
                        fallback_section = fallback_sections_result.scalar_one_or_none()
                        if fallback_section:
                            mapped["category"] = fallback_section.name
                            logger.info(f"✓ Использован fallback раздел '{fallback_section.name}' для товара {product_data.get('name', 'Unknown')} (category_external_id отсутствует или не найден)")
                        else:
                            logger.warning(f"⚠ Fallback раздел не найден для товара {product_data.get('name', 'Unknown')}")
                    except Exception as fallback_error:
                        logger.warning(f"Ошибка при поиске fallback категории: {fallback_error}")
                
                # Характеристики (specifications)
                specifications = product_data.get("specifications", {}) or {}
                if not isinstance(specifications, dict):
                    specifications = {}
                
                # Добавляем характеристики из import.xml (если есть)
                if product_data.get("characteristics"):
                    for char_name, char_value in product_data["characteristics"].items():
                        specifications[char_name] = char_value
                
                # Добавляем характеристики из offers.xml (приоритет - из offers, так как там актуальные данные)
                if main_offer and main_offer.get("characteristics"):
                    for char_name, char_value in main_offer["characteristics"].items():
                        specifications[char_name] = char_value
                
                # Добавляем данные из основного предложения
                if main_offer:
                    if main_offer.get("barcode"):
                        specifications["barcode"] = main_offer["barcode"]
                    if main_offer.get("quantity") is not None:
                        specifications["quantity"] = main_offer["quantity"]
                
                # Добавляем штрихкод из product_data, если есть
                if product_data.get("barcode"):
                    specifications["barcode"] = product_data["barcode"]
                
                if specifications:
                    mapped["specifications"] = specifications
                
                # Логируем категорию товара для диагностики
                if mapped.get("category"):
                    logger.info(f"✓ Товар '{product_data.get('name', 'Unknown')}' будет сохранен с категорией: '{mapped['category']}'")
                else:
                    logger.warning(f"⚠ Товар '{product_data.get('name', 'Unknown')}' будет сохранен БЕЗ категории (category_external_id={product_data.get('category_external_id')})")
                
                base_product = None
                if existing_product:
                    if update_existing:
                        # Обновляем существующий товар
                        for key, value in mapped.items():
                            # Обновляем поле, даже если value is None (для очистки старых значений)
                            # Но для category обновляем только если есть новое значение
                            if key == "category" and value is None:
                                continue  # Не очищаем категорию, если новое значение None
                            setattr(existing_product, key, value)
                        existing_product.updated_at = datetime.now(timezone.utc)
                        updated += 1
                        base_product = existing_product
                        if mapped.get("category"):
                            logger.debug(f"Обновлен товар '{existing_product.name}' с категорией: '{mapped['category']}'")
                    else:
                        skipped += 1
                        base_product = existing_product
                else:
                    # Создаем новый товар
                    new_product = Product(**mapped)
                    self.db.add(new_product)
                    await self.db.flush()  # Получаем ID нового товара
                    created += 1
                    base_product = new_product
                
                # Сохраняем связи товара с группами каталога (many-to-many)
                # groups_external_ids уже определена выше (строка 465)
                if base_product and groups_external_ids:
                    try:
                        # Удаляем старые связи товара с группами
                        await self.db.execute(
                            delete(ProductCatalogSection).where(
                                ProductCatalogSection.product_id == base_product.id
                            )
                        )
                        
                        # Находим разделы каталога по external_id
                        sections_result = await self.db.execute(
                            select(CatalogSection).where(
                                CatalogSection.external_id.in_(groups_external_ids)
                            )
                        )
                        found_sections = sections_result.scalars().all()
                        
                        # Создаем новые связи
                        for section in found_sections:
                            # Проверяем, нет ли уже такой связи
                            existing_link_result = await self.db.execute(
                                select(ProductCatalogSection).where(
                                    (ProductCatalogSection.product_id == base_product.id)
                                    & (ProductCatalogSection.catalog_section_id == section.id)
                                )
                            )
                            existing_link = existing_link_result.scalar_one_or_none()
                            
                            if not existing_link:
                                new_link = ProductCatalogSection(
                                    product_id=base_product.id,
                                    catalog_section_id=section.id
                                )
                                self.db.add(new_link)
                        
                        await self.db.flush()
                        logger.debug(f"Сохранены связи товара {base_product.name} с {len(found_sections)} группами каталога")
                    except Exception as link_error:
                        logger.warning(f"Ошибка при сохранении связей товара с группами каталога: {link_error}")
                        try:
                            await self.db.rollback()
                        except Exception as rollback_exc:
                            logger.error(f"Ошибка при rollback после ошибки сохранения связей: {rollback_exc}")
                
                # Сохраняем остатки в product_stocks (если есть основное предложение с остатками)
                if base_product and main_offer:
                    try:
                        # Сохраняем остатки по складам (если есть)
                        store_stocks = main_offer.get("store_stocks", {})
                        if store_stocks:
                            # Сохраняем остатки по каждому складу
                            for store_id, quantity in store_stocks.items():
                                try:
                                    quantity_float = float(quantity)
                                    
                                    stock_result = await self.db.execute(
                                        select(ProductStock).where(
                                            (ProductStock.product_id == base_product.id)
                                            & (ProductStock.store_id == store_id)
                                        )
                                    )
                                    stock = stock_result.scalar_one_or_none()
                                    
                                    if stock:
                                        stock.quantity = quantity_float
                                        stock.available_quantity = quantity_float
                                    else:
                                        # Создаем новый остаток
                                        new_stock = ProductStock(
                                            product_id=base_product.id,
                                            store_id=store_id,
                                            quantity=quantity_float,
                                            reserved_quantity=0.0,
                                            available_quantity=quantity_float,
                                        )
                                        self.db.add(new_stock)
                                        try:
                                            await self.db.flush()  # Пробуем сохранить сразу
                                        except Exception as flush_exc:
                                            # Если запись уже существует (race condition), обновляем её
                                            if "UniqueViolation" in str(flush_exc) or "duplicate key" in str(flush_exc).lower():
                                                await self.db.rollback()
                                                # Ищем существующую запись и обновляем
                                                stock_result_retry = await self.db.execute(
                                                    select(ProductStock).where(
                                                        (ProductStock.product_id == base_product.id)
                                                        & (ProductStock.store_id == store_id)
                                                    )
                                                )
                                                stock_retry = stock_result_retry.scalar_one_or_none()
                                                if stock_retry:
                                                    stock_retry.quantity = quantity_float
                                                    stock_retry.available_quantity = quantity_float
                                            else:
                                                raise
                                except Exception as store_stock_exc:
                                    logger.warning(f"Ошибка сохранения остатков для товара {product_data.get('name', 'Unknown')} на складе {store_id}: {store_stock_exc}")
                                    try:
                                        await self.db.rollback()
                                    except Exception as rollback_exc:
                                        logger.error(f"Ошибка при rollback после ошибки сохранения остатков: {rollback_exc}")
                        elif main_offer.get("quantity") is not None:
                            # Если нет остатков по складам, сохраняем общее количество в default_store
                            default_store_id = "default_store"
                            quantity = float(main_offer["quantity"])
                            
                            # Ищем существующий остаток
                            stock_result = await self.db.execute(
                                select(ProductStock).where(
                                    (ProductStock.product_id == base_product.id)
                                    & (ProductStock.store_id == default_store_id)
                                )
                            )
                            stock = stock_result.scalar_one_or_none()
                            
                            if stock:
                                stock.quantity = quantity
                                stock.available_quantity = quantity
                            else:
                                # Создаем новый остаток
                                new_stock = ProductStock(
                                    product_id=base_product.id,
                                    store_id=default_store_id,
                                    quantity=quantity,
                                    reserved_quantity=0.0,
                                    available_quantity=quantity,
                                )
                                self.db.add(new_stock)
                                try:
                                    await self.db.flush()  # Пробуем сохранить сразу
                                except Exception as flush_exc:
                                    # Если запись уже существует (race condition), обновляем её
                                    if "UniqueViolation" in str(flush_exc) or "duplicate key" in str(flush_exc).lower():
                                        await self.db.rollback()
                                        # Ищем существующую запись и обновляем
                                        stock_result_retry = await self.db.execute(
                                            select(ProductStock).where(
                                                (ProductStock.product_id == base_product.id)
                                                & (ProductStock.store_id == default_store_id)
                                            )
                                        )
                                        stock_retry = stock_result_retry.scalar_one_or_none()
                                        if stock_retry:
                                            stock_retry.quantity = quantity
                                            stock_retry.available_quantity = quantity
                                    else:
                                        raise
                    except Exception as stock_exc:
                        logger.warning(f"Ошибка сохранения остатков для товара {product_data.get('name', 'Unknown')}: {stock_exc}")
                        try:
                            await self.db.rollback()
                        except Exception as rollback_exc:
                            logger.error(f"Ошибка при rollback после ошибки сохранения остатков: {rollback_exc}")
                
                # Создаем варианты товара (если есть предложения с характеристиками)
                logger.info(f"Товар {product_data.get('name', 'Unknown')} (external_id={external_id}): найдено {len(variant_offers)} вариантов, основное предложение: {main_offer is not None}")
                if variant_offers and base_product:
                    for variant_offer in variant_offers:
                        try:
                            # Создаем вариант товара
                            variant_external_id = variant_offer.get('id')  # product_id#characteristic_id (используем 'id', а не 'offer_id')
                            if not variant_external_id:
                                # Если id нет, но есть product_id и characteristic_id, формируем id
                                variant_product_id = variant_offer.get('product_id', external_id)
                                characteristic_id = variant_offer.get("characteristic_id")
                                if variant_product_id and characteristic_id:
                                    variant_external_id = f"{variant_product_id}#{characteristic_id}"
                                elif variant_product_id:
                                    variant_external_id = f"{variant_product_id}#{variant_offer.get('article', 'variant')}"
                            
                            variant_article = variant_offer.get('article')
                            variant_price = variant_offer.get("price", 0)
                            variant_barcode = variant_offer.get("barcode")
                            variant_quantity = variant_offer.get("quantity", 0)
                            characteristic_id = variant_offer.get("characteristic_id")
                            
                            # Если characteristic_id не был извлечен из id, попробуем извлечь из id
                            if not characteristic_id and variant_external_id and '#' in variant_external_id:
                                parts = variant_external_id.split('#', 1)
                                if len(parts) == 2:
                                    characteristic_id = parts[1]
                            
                            logger.info(f"Создание варианта для товара {product_data.get('name', 'Unknown')}: variant_external_id={variant_external_id}, article={variant_article}, characteristic_id={characteristic_id}, parent_external_id={external_id}")
                            
                            # Убеждаемся, что parent_external_id правильно установлен
                            if not external_id:
                                logger.warning(f"⚠ external_id основного товара пуст, не могу создать вариант для {variant_article}")
                                continue
                            
                            variant_images = variant_offer.get("images") or []
                            if variant_offer.get("image") and variant_offer.get("image") not in variant_images:
                                variant_images.insert(0, variant_offer.get("image"))
                            
                            # Ищем существующий вариант
                            variant_existing = None
                            if variant_external_id:
                                result = await self.db.execute(
                                    select(Product).where(Product.external_id == variant_external_id)
                                )
                                variant_existing = result.scalar_one_or_none()
                            
                            if not variant_existing and variant_article:
                                result = await self.db.execute(
                                    select(Product).where(Product.article == variant_article)
                                )
                                variant_existing = result.scalar_one_or_none()
                            
                            # Создаем или обновляем вариант
                            variant_specs = {
                                "parent_external_id": external_id,  # Ссылка на основной товар - КРИТИЧЕСКИ ВАЖНО!
                                "characteristic_id": characteristic_id,
                                "quantity": variant_quantity,
                            }
                            
                            logger.debug(f"Вариант будет сохранен с parent_external_id={external_id} в specifications")
                            if variant_barcode:
                                variant_specs["barcode"] = variant_barcode
                            
                            # Добавляем характеристики из offers.xml для варианта
                            if variant_offer.get("characteristics"):
                                for char_name, char_value in variant_offer["characteristics"].items():
                                    variant_specs[char_name] = char_value
                            
                            variant_product_for_stock = None
                            
                            if variant_existing:
                                # Обновляем существующий вариант
                                variant_existing.price = variant_price
                                variant_existing.article = variant_article or variant_existing.article
                                if variant_images:
                                    variant_existing.images = variant_images
                                if variant_existing.specifications:
                                    variant_existing.specifications.update(variant_specs)
                                else:
                                    variant_existing.specifications = variant_specs
                                variant_existing.updated_at = datetime.now(timezone.utc)
                                variant_product_for_stock = variant_existing
                            else:
                                # Создаем новый вариант
                                variant_product = Product(
                                    name=product_data.get("name", "Unnamed product"),
                                    article=variant_article,
                                    external_id=variant_external_id,
                                    external_code=product_data.get("code_1c"),
                                    description=product_data.get("description"),
                                    full_description=product_data.get("full_description") or product_data.get("description"),
                                    price=variant_price,
                                    category=mapped.get("category"),
                                    images=variant_images if variant_images else None,
                                    specifications=variant_specs,
                                    is_active=True,
                                    sync_status="synced",
                                    sync_metadata={
                                        "source": "commerceml_xml",
                                        "imported_at": datetime.now(timezone.utc).isoformat(),
                                        "is_variant": True,
                                        "parent_external_id": external_id,
                                    },
                                )
                                self.db.add(variant_product)
                                await self.db.flush()  # Получаем ID варианта
                                variants_created += 1
                                variant_product_for_stock = variant_product
                            
                            # Сохраняем остатки для варианта
                            if variant_product_for_stock:
                                try:
                                    # Сохраняем остатки по складам (если есть)
                                    store_stocks = variant_offer.get("store_stocks", {})
                                    if store_stocks:
                                        # Сохраняем остатки по каждому складу
                                        for store_id, quantity in store_stocks.items():
                                            try:
                                                quantity_float = float(quantity)
                                                
                                                stock_result = await self.db.execute(
                                                    select(ProductStock).where(
                                                        (ProductStock.product_id == variant_product_for_stock.id)
                                                        & (ProductStock.store_id == store_id)
                                                    )
                                                )
                                                stock = stock_result.scalar_one_or_none()
                                                
                                                if stock:
                                                    stock.quantity = quantity_float
                                                    stock.available_quantity = quantity_float
                                                else:
                                                    # Проверяем еще раз перед созданием (на случай параллельной обработки)
                                                    stock_result_check = await self.db.execute(
                                                        select(ProductStock).where(
                                                            (ProductStock.product_id == variant_product_for_stock.id)
                                                            & (ProductStock.store_id == store_id)
                                                        )
                                                    )
                                                    stock_check = stock_result_check.scalar_one_or_none()
                                                    
                                                    if stock_check:
                                                        # Запись появилась между проверками - обновляем её
                                                        stock_check.quantity = quantity_float
                                                        stock_check.available_quantity = quantity_float
                                                    else:
                                                        new_stock = ProductStock(
                                                            product_id=variant_product_for_stock.id,
                                                            store_id=store_id,
                                                            quantity=quantity_float,
                                                            reserved_quantity=0.0,
                                                            available_quantity=quantity_float,
                                                        )
                                                        self.db.add(new_stock)
                                                        try:
                                                            await self.db.flush()  # Пробуем сохранить сразу
                                                        except Exception as flush_exc:
                                                            # Если запись уже существует (race condition), обновляем её
                                                            if "UniqueViolation" in str(flush_exc) or "duplicate key" in str(flush_exc).lower():
                                                                await self.db.rollback()
                                                                # Ищем существующую запись и обновляем
                                                                stock_result_retry = await self.db.execute(
                                                                    select(ProductStock).where(
                                                                        (ProductStock.product_id == variant_product_for_stock.id)
                                                                        & (ProductStock.store_id == store_id)
                                                                    )
                                                                )
                                                                stock_retry = stock_result_retry.scalar_one_or_none()
                                                                if stock_retry:
                                                                    stock_retry.quantity = quantity_float
                                                                    stock_retry.available_quantity = quantity_float
                                                            else:
                                                                raise
                                            except Exception as store_stock_exc:
                                                logger.warning(f"Ошибка сохранения остатков для варианта {variant_article} на складе {store_id}: {store_stock_exc}")
                                                try:
                                                    await self.db.rollback()
                                                except Exception as rollback_exc:
                                                    logger.error(f"Ошибка при rollback после ошибки сохранения остатков варианта: {rollback_exc}")
                                    elif variant_quantity is not None:
                                        # Если нет остатков по складам, сохраняем общее количество в default_store
                                        default_store_id = "default_store"
                                        quantity_float = float(variant_quantity)
                                        
                                        stock_result = await self.db.execute(
                                            select(ProductStock).where(
                                                (ProductStock.product_id == variant_product_for_stock.id)
                                                & (ProductStock.store_id == default_store_id)
                                            )
                                        )
                                        stock = stock_result.scalar_one_or_none()
                                        
                                        if stock:
                                            stock.quantity = quantity_float
                                            stock.available_quantity = quantity_float
                                        else:
                                            new_stock = ProductStock(
                                                product_id=variant_product_for_stock.id,
                                                store_id=default_store_id,
                                                quantity=quantity_float,
                                                reserved_quantity=0.0,
                                                available_quantity=quantity_float,
                                            )
                                            self.db.add(new_stock)
                                            try:
                                                await self.db.flush()  # Пробуем сохранить сразу
                                            except Exception as flush_exc:
                                                # Если запись уже существует (race condition), обновляем её
                                                if "UniqueViolation" in str(flush_exc) or "duplicate key" in str(flush_exc).lower():
                                                    await self.db.rollback()
                                                    # Ищем существующую запись и обновляем
                                                    stock_result_retry = await self.db.execute(
                                                        select(ProductStock).where(
                                                            (ProductStock.product_id == variant_product_for_stock.id)
                                                            & (ProductStock.store_id == default_store_id)
                                                        )
                                                    )
                                                    stock_retry = stock_result_retry.scalar_one_or_none()
                                                    if stock_retry:
                                                        stock_retry.quantity = quantity_float
                                                        stock_retry.available_quantity = quantity_float
                                                else:
                                                    raise
                                except Exception as stock_exc:
                                    logger.warning(f"Ошибка сохранения остатков для варианта {variant_article}: {stock_exc}")
                                    try:
                                        await self.db.rollback()
                                    except Exception as rollback_exc:
                                        logger.error(f"Ошибка при rollback после ошибки сохранения остатков варианта: {rollback_exc}")
                        except Exception as variant_exc:
                            error_msg = f"Ошибка создания варианта для товара {product_data.get('name', 'Unknown')}: {variant_exc}"
                            logger.warning(error_msg)
                            errors.append(error_msg)
                
                # Коммитим каждые 50 товаров
                if (created + updated) % 50 == 0:
                    try:
                        await self.db.commit()
                    except Exception as commit_error:
                        logger.error(f"Ошибка при промежуточном commit: {commit_error}", exc_info=True)
                        try:
                            await self.db.rollback()
                        except Exception as rollback_error:
                            logger.error(f"Ошибка при rollback после промежуточного commit: {rollback_error}")
                
                # Обновляем прогресс
                if progress_callback:
                    await progress_callback(idx + 1, total)
                    
            except Exception as exc:
                error_msg = f"Ошибка импорта товара {product_data.get('name', 'Unknown')}: {exc}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)
                # Делаем rollback при ошибке, чтобы транзакция не оставалась в состоянии ошибки
                try:
                    await self.db.rollback()
                except Exception as rollback_error:
                    logger.warning(f"Ошибка при rollback: {rollback_error}")
                # Продолжаем обработку следующего товара
        
        # Финальный commit для всех успешно обработанных товаров
        try:
            await self.db.commit()
        except Exception as commit_error:
            logger.error(f"Ошибка при финальном commit: {commit_error}", exc_info=True)
            try:
                await self.db.rollback()
            except Exception as rollback_error:
                logger.error(f"Ошибка при rollback после commit: {rollback_error}")

        return {
            "total": total,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "variants_created": variants_created,
            "errors": errors[:20],
            "error_count": len(errors),
        }
