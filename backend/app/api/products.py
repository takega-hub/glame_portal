from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, String, cast, text, bindparam, case
from sqlalchemy.dialects.postgresql import JSONB
from typing import List, Optional, Dict
from pydantic import BaseModel
import logging
import asyncio
import json
import os
from app.database.connection import get_db
from app.models.product import Product
from app.models.product_catalog_section import ProductCatalogSection
from app.services.onec_products_service import OneCProductsService
from app.services.onec_stock_service import OneCStockService
from app.services.sync_progress_service import get_sync_progress_service
from app.services.onec_images_service import OneCImagesService
from app.services.yml_images_service import YMLImagesService
from app.services.commerceml_xml_service import CommerceMLXMLService
from app.services.product_images_download_service import ProductImagesDownloadService
from uuid import UUID

router = APIRouter()
logger = logging.getLogger(__name__)


async def get_product_stock(db: AsyncSession, product_id: UUID) -> float | None:
    """
    Вычисляет общий остаток товара (сумма по всем складам)
    
    Args:
        db: Сессия базы данных
        product_id: ID товара
        
    Returns:
        Общий остаток товара или None, если остатков нет
    """
    from app.models.product_stock import ProductStock
    result = await db.execute(
        select(func.sum(ProductStock.available_quantity))
        .where(ProductStock.product_id == product_id)
    )
    total_stock = result.scalar_one_or_none()
    return float(total_stock) if total_stock is not None else None


class ProductResponse(BaseModel):
    id: str
    name: str
    brand: str | None
    price: int
    category: str | None
    images: List[str]
    tags: List[str]
    description: str | None
    article: str | None = None
    vendor_code: str | None = None
    barcode: str | None = None
    unit: str | None = None
    weight: float | None = None
    volume: float | None = None
    country: str | None = None
    warranty: str | None = None
    full_description: str | None = None
    specifications: dict | None = None
    external_id: str | None = None
    external_code: str | None = None
    is_active: bool = True
    sync_status: str | None = None
    sync_metadata: dict | None = None
    stock: float | None = None  # Общий остаток товара (сумма по всем складам)

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    name: str
    brand: str | None = None
    price: int
    category: str | None = None
    images: List[str] = []
    tags: List[str] = []
    description: str | None = None


class ProductVariantsResponse(BaseModel):
    base: ProductResponse
    variants: List[ProductResponse]
    parent_external_id: str | None = None


class PagedProductsResponse(BaseModel):
    items: List[ProductResponse]
    total: int
    skip: int
    limit: int


@router.get("/characteristics/values")
async def get_characteristics_values(
    db: AsyncSession = Depends(get_db),
):
    """
    Получить все доступные значения характеристик товаров.
    Возвращает словарь, где ключ - название характеристики, значение - список уникальных значений.
    """
    try:
        # Получаем все товары с specifications
        # Используем полный объект Product, чтобы получить доступ к specifications
        result = await db.execute(
            select(Product).where(
                Product.specifications.isnot(None),
                Product.is_active == True
            )
        )
        products = result.scalars().all()
        
        # Собираем все характеристики
        characteristics: Dict[str, set] = {}
        
        for product in products:
            if product.specifications:
                specs = product.specifications
                # specifications уже является словарем (JSON поле из БД)
                if isinstance(specs, dict):
                    for key, value in specs.items():
                        # Пропускаем служебные поля
                        if key in ['parent_external_id', 'characteristic_id', 'quantity', 'barcode']:
                            continue
                        
                        if key not in characteristics:
                            characteristics[key] = set()
                        
                        if value and isinstance(value, (str, int, float)):
                            characteristics[key].add(str(value))
        
        # Преобразуем в список и сортируем
        result_dict = {}
        for key, values in characteristics.items():
            result_dict[key] = sorted(list(values))
        
        return result_dict
        
    except Exception as e:
        logger.error(f"Ошибка при получении значений характеристик: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при получении значений характеристик: {str(e)}")


@router.get("/paged", response_model=PagedProductsResponse)
async def get_products_paged(
    skip: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
    category: Optional[str] = None,
    brand: Optional[str] = None,
    tags: Optional[str] = None,
    search: Optional[str] = None,
    # Фильтры по характеристикам (из specifications)
    material: Optional[str] = None,
    vstavka: Optional[str] = None,  # Вставка
    pokrytie: Optional[str] = None,  # Покрытие
    razmer: Optional[str] = None,  # Размер
    tip_zamka: Optional[str] = None,  # Тип замка
    color: Optional[str] = None,  # Цвет
    in_stock: Optional[bool] = None,
    # Универсальный фильтр по характеристикам (JSON строка вида {"Характеристика": "Значение"})
    specs: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Постраничная выдача товаров с total.

    Важно: limit ограничен 100, поэтому для >100 товаров используем skip/limit.
    
    Параметры поиска:
    - search: поиск по названию товара (name) и артикулу (external_code)
    """
    try:
        filters = [Product.is_active == True]
        
        # ПОКАЗЫВАЕМ ВАРИАНТЫ вместо основных товаров
        # Варианты содержат все характеристики (Бренд, Цвет, Размер и т.д.)
        # Основные товары часто не имеют характеристик
        # 
        # Стратегия: показываем товары с характеристиками (варианты)
        # или товары без parent_external_id (основные товары без вариантов)
        variant_filter = or_(
            # Показываем варианты (имеют parent_external_id и характеристики)
            and_(
                Product.specifications.isnot(None),
                cast(Product.specifications["parent_external_id"], String).isnot(None),
                cast(Product.specifications["parent_external_id"], String) != ""
            ),
            # Показываем основные товары БЕЗ вариантов (нет parent_external_id)
            or_(
                Product.specifications.is_(None),
                cast(Product.specifications["parent_external_id"], String).is_(None),
                cast(Product.specifications["parent_external_id"], String) == ""
            )
        )
        filters.append(variant_filter)
        
        if category:
            # Фильтр по категории (название раздела каталога)
            # Товар может быть в нескольких группах, поэтому используем JOIN через промежуточную таблицу
            from app.models.catalog_section import CatalogSection
            category_filter = category.strip()
            # Используем подзапрос для поиска товаров, связанных с разделом каталога
            section_subquery = select(ProductCatalogSection.product_id).join(
                CatalogSection, ProductCatalogSection.catalog_section_id == CatalogSection.id
            ).where(CatalogSection.name.ilike(category_filter))
            filters.append(Product.id.in_(section_subquery))
            logger.info(f"Фильтр по категории (разделу): '{category_filter}'")
        if brand:
            # Бренд может быть в поле brand или в specifications['Бренд']
            # Проверяем оба варианта
            brand_filter = brand.strip()
            brand_filters = []
            # Фильтр по полю brand (точное совпадение, регистронезависимое)
            brand_filters.append(
                and_(
                    Product.brand.isnot(None),
                    func.lower(Product.brand) == func.lower(brand_filter)
                )
            )
            # Фильтр по specifications['Бренд'] (точное совпадение, регистронезависимое)
            # Используем прямой SQL для надежной работы с JSONB
            brand_sql = text("LOWER(specifications->>'Бренд') = LOWER(:brand_value)").bindparams(brand_value=brand_filter)
            brand_filters.append(
                and_(
                    Product.specifications.isnot(None),
                    brand_sql
                )
            )
            filters.append(or_(*brand_filters))
            logger.info(f"Фильтр по бренду: '{brand_filter}'")
        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            for tag in tag_list:
                filters.append(Product.tags.contains([tag]))

        if in_stock:
            from app.models.product_stock import ProductStock
            stock_subquery = (
                select(ProductStock.product_id)
                .group_by(ProductStock.product_id)
                .having(func.sum(ProductStock.available_quantity) > 0)
            )
            filters.append(Product.id.in_(stock_subquery))
            logger.info("Фильтр по наличию: только товары с количеством > 0")
        
        # Фильтры по характеристикам из specifications
        # Используем прямой SQL оператор ->> для извлечения текста из JSONB
        # Это более надежный способ работы с JSONB в PostgreSQL
        if material:
            material_filter = material.strip()
            material_sql = text("LOWER(specifications->>'Материал') = LOWER(:material_value)").bindparams(material_value=material_filter)
            filters.append(
                and_(
                    Product.specifications.isnot(None),
                    material_sql
                )
            )
            logger.debug(f"Фильтр по материалу: '{material_filter}'")
        if vstavka:
            vstavka_filter = vstavka.strip()
            vstavka_sql = text("LOWER(specifications->>'Вставка') = LOWER(:vstavka_value)").bindparams(vstavka_value=vstavka_filter)
            filters.append(
                and_(
                    Product.specifications.isnot(None),
                    vstavka_sql
                )
            )
            logger.debug(f"Фильтр по вставке: '{vstavka_filter}'")
        if pokrytie:
            pokrytie_filter = pokrytie.strip()
            # Фильтр по покрытию - проверяем только в основных товарах (варианты уже исключены)
            # Используем прямой SQL оператор ->> для извлечения текста из JSONB
            # Это более надежный способ работы с JSONB в PostgreSQL
            pokrytie_sql = text("LOWER(specifications->>'Покрытие') = LOWER(:pokrytie_value)").bindparams(pokrytie_value=pokrytie_filter)
            pokrytie_condition = and_(
                Product.specifications.isnot(None),
                pokrytie_sql
            )
            filters.append(pokrytie_condition)
            logger.info(f"Фильтр по покрытию: '{pokrytie_filter}'")
        if razmer:
            razmer_filter = razmer.strip()
            razmer_sql = text("LOWER(specifications->>'Размер') = LOWER(:razmer_value)").bindparams(razmer_value=razmer_filter)
            filters.append(
                and_(
                    Product.specifications.isnot(None),
                    razmer_sql
                )
            )
            logger.debug(f"Фильтр по размеру: '{razmer_filter}'")
        if tip_zamka:
            tip_zamka_filter = tip_zamka.strip()
            tip_zamka_sql = text("LOWER(specifications->>'Тип замка') = LOWER(:tip_zamka_value)").bindparams(tip_zamka_value=tip_zamka_filter)
            filters.append(
                and_(
                    Product.specifications.isnot(None),
                    tip_zamka_sql
                )
            )
            logger.debug(f"Фильтр по типу замка: '{tip_zamka_filter}'")
        if color:
            color_filter = color.strip()
            color_sql = text("LOWER(specifications->>'Цвет') = LOWER(:color_value)").bindparams(color_value=color_filter)
            filters.append(
                and_(
                    Product.specifications.isnot(None),
                    color_sql
                )
            )
            logger.debug(f"Фильтр по цвету: '{color_filter}'")
        
        # Универсальный фильтр по характеристикам (JSON строка)
        if specs:
            try:
                specs_dict = json.loads(specs)
                if isinstance(specs_dict, dict):
                    for spec_key, spec_value in specs_dict.items():
                        if spec_key and spec_value:
                            filters.append(
                                cast(Product.specifications[spec_key], String) == str(spec_value).strip()
                            )
            except json.JSONDecodeError:
                logger.warning(f"Неверный формат JSON в параметре specs: {specs}")
        
        if search:
            search_term = f"%{search.strip()}%"
            # Поиск по названию, артикулу (article) и external_code
            search_filters = [Product.name.ilike(search_term)]
            # Добавляем поиск по артикулу (article)
            search_filters.append(
                and_(
                    Product.article.isnot(None),
                    Product.article.ilike(search_term)
                )
            )
            # Добавляем поиск по external_code
            search_filters.append(
                and_(
                    Product.external_code.isnot(None),
                    Product.external_code.ilike(search_term)
                )
            )
            filters.append(or_(*search_filters))

        # Логируем количество фильтров для отладки
        logger.debug(f"Применено фильтров: {len(filters)}")
        if pokrytie:
            logger.debug(f"Фильтр по покрытию активен: '{pokrytie}'")
        
        # ДЕДУПЛИКАЦИЯ ВАРИАНТОВ
        # Для каждого parent_external_id показываем только один вариант (первый по ID)
        # Используем подзапрос с ROW_NUMBER для выбора первого варианта из группы
        from sqlalchemy import literal_column
        
        # Подзапрос для выбора одного варианта на группу (parent_external_id)
        # ROW_NUMBER() OVER (PARTITION BY parent_external_id ORDER BY id) = 1
        # Для товаров без parent_external_id (основные товары) показываем все
        
        # Применяем фильтры и получаем список ID товаров
        base_query = select(Product).where(*filters)
        
        # Добавляем дедупликацию через Python (так как DISTINCT ON сложен в SQLAlchemy)
        # Альтернативный подход: выбираем все варианты, затем группируем
        result = await db.execute(base_query)
        all_products = result.scalars().all()
        
        # Группируем по parent_external_id и берем первый вариант из каждой группы
        seen_parents = set()
        deduplicated_products = []
        
        for product in all_products:
            parent_id = None
            if product.specifications and isinstance(product.specifications, dict):
                parent_id = product.specifications.get('parent_external_id')
            
            # Если это вариант (имеет parent_id)
            if parent_id:
                # Показываем только первый вариант из группы
                if parent_id not in seen_parents:
                    seen_parents.add(parent_id)
                    deduplicated_products.append(product)
            else:
                # Основной товар без вариантов - всегда показываем
                deduplicated_products.append(product)
        
        # Применяем пагинацию после дедупликации
        total = len(deduplicated_products)
        products = deduplicated_products[skip:skip + limit]
        
        if category:
            logger.info(f"Фильтр по категории '{category}': найдено {total} товаров (после дедупликации)")
        if pokrytie:
            logger.info(f"Фильтр по покрытию '{pokrytie}': найдено {total} товаров (после дедупликации)")
        if brand:
            logger.info(f"Фильтр по бренду '{brand}': найдено {total} товаров (после дедупликации)")
        
        # Дополнительное логирование для отладки
        if pokrytie and len(products) == 0 and total > 0:
            logger.warning(f"Фильтр по покрытию '{pokrytie}': total={total}, но products={len(products)}. Возможна проблема с пагинацией.")
        elif pokrytie:
            logger.debug(f"Фильтр по покрытию '{pokrytie}': возвращено {len(products)} товаров из {total}")
        
        # Логируем категории найденных товаров для диагностики
        if category and products:
            sample_categories = list(set([p.category for p in products[:10] if p.category]))
            logger.debug(f"Примеры категорий найденных товаров: {sample_categories}")
        elif category and not products:
            # Если товары не найдены, проверяем какие категории есть в базе
            all_categories_result = await db.execute(
                select(func.distinct(Product.category)).where(Product.is_active == True).limit(10)
            )
            all_categories = [row[0] for row in all_categories_result if row[0]]
            logger.warning(f"Товары с категорией '{category}' не найдены. Доступные категории в БД: {all_categories}")

        # Получаем остатки для всех товаров одним запросом
        from app.models.product_stock import ProductStock
        product_ids = [p.id for p in products]
        stocks_result = await db.execute(
            select(
                ProductStock.product_id,
                func.sum(ProductStock.available_quantity).label('total_stock')
            )
            .where(ProductStock.product_id.in_(product_ids))
            .group_by(ProductStock.product_id)
        )
        stocks_dict = {row[0]: float(row[1]) for row in stocks_result.all()}
        
        items = [
            ProductResponse(
                id=str(p.id),
                name=p.name,
                brand=p.brand,
                price=p.price,
                category=p.category,
                images=p.images or [],
                tags=p.tags or [],
                description=p.description,
                article=p.article if hasattr(p, "article") else None,
                vendor_code=p.vendor_code if hasattr(p, "vendor_code") else None,
                barcode=p.barcode if hasattr(p, "barcode") else None,
                unit=p.unit if hasattr(p, "unit") else None,
                weight=p.weight if hasattr(p, "weight") else None,
                volume=p.volume if hasattr(p, "volume") else None,
                country=p.country if hasattr(p, "country") else None,
                warranty=p.warranty if hasattr(p, "warranty") else None,
                full_description=p.full_description if hasattr(p, "full_description") else None,
                specifications=p.specifications if hasattr(p, "specifications") else None,
                external_id=p.external_id if hasattr(p, "external_id") else None,
                external_code=p.external_code if hasattr(p, "external_code") else None,
                is_active=p.is_active if hasattr(p, "is_active") else True,
                sync_status=p.sync_status if hasattr(p, "sync_status") else None,
                sync_metadata=p.sync_metadata if hasattr(p, "sync_metadata") else None,
                stock=stocks_dict.get(p.id)
            )
            for p in products
        ]

        return PagedProductsResponse(items=items, total=total, skip=skip, limit=limit)
    except Exception as e:
        logger.error(f"Ошибка при получении товаров (paged): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке товаров: {str(e)}")


@router.get("/", response_model=List[ProductResponse])
async def get_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    category: Optional[str] = None,
    brand: Optional[str] = None,
    tags: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Получение списка товаров с фильтрацией.
    
    Параметры поиска:
    - search: поиск по названию товара (name) и артикулу (external_code)
    """
    try:
        query = select(Product).where(Product.is_active == True)
        
        # Исключаем варианты товаров из списка (показываем только основные товары)
        # Варианты имеют parent_external_id в specifications
        query = query.where(
            or_(
                Product.specifications.is_(None),
                cast(Product.specifications["parent_external_id"], String).is_(None),
                cast(Product.specifications["parent_external_id"], String) == ""
            )
        )
        
        if category:
            # Фильтр по категории (название раздела каталога)
            # Используем ilike для регистронезависимого поиска
            query = query.where(Product.category.ilike(category.strip()))
        if brand:
            query = query.where(Product.brand == brand)
        if tags:
            tag_list = tags.split(",")
            for tag in tag_list:
                query = query.where(Product.tags.contains([tag]))
        if search:
            search_term = f"%{search.strip()}%"
            # Поиск по названию, артикулу (article) и external_code
            search_filters = [Product.name.ilike(search_term)]
            # Добавляем поиск по артикулу (article)
            search_filters.append(
                and_(
                    Product.article.isnot(None),
                    Product.article.ilike(search_term)
                )
            )
            # Добавляем поиск по external_code
            search_filters.append(
                and_(
                    Product.external_code.isnot(None),
                    Product.external_code.ilike(search_term)
                )
            )
            query = query.where(or_(*search_filters))
        
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        products = result.scalars().all()
        
        # Получаем остатки для всех товаров одним запросом
        from app.models.product_stock import ProductStock
        product_ids = [p.id for p in products]
        stocks_result = await db.execute(
            select(
                ProductStock.product_id,
                func.sum(ProductStock.available_quantity).label('total_stock')
            )
            .where(ProductStock.product_id.in_(product_ids))
            .group_by(ProductStock.product_id)
        )
        stocks_dict = {row[0]: float(row[1]) for row in stocks_result.all()}
        
        # Преобразуем в ProductResponse
        return [ProductResponse(
            id=str(p.id),
            name=p.name,
            brand=p.brand,
            price=p.price,
            category=p.category,
            images=p.images or [],
            tags=p.tags or [],
            description=p.description,
            article=p.article if hasattr(p, 'article') else None,
            vendor_code=p.vendor_code if hasattr(p, 'vendor_code') else None,
            barcode=p.barcode if hasattr(p, 'barcode') else None,
            unit=p.unit if hasattr(p, 'unit') else None,
            weight=p.weight if hasattr(p, 'weight') else None,
            volume=p.volume if hasattr(p, 'volume') else None,
            country=p.country if hasattr(p, 'country') else None,
            warranty=p.warranty if hasattr(p, 'warranty') else None,
            full_description=p.full_description if hasattr(p, 'full_description') else None,
            specifications=p.specifications if hasattr(p, 'specifications') else None,
            external_id=p.external_id if hasattr(p, 'external_id') else None,
            external_code=p.external_code if hasattr(p, 'external_code') else None,
            is_active=p.is_active if hasattr(p, 'is_active') else True,
            sync_status=p.sync_status if hasattr(p, 'sync_status') else None,
            sync_metadata=p.sync_metadata if hasattr(p, 'sync_metadata') else None,
            stock=stocks_dict.get(p.id)
        ) for p in products]
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Ошибка при получении товаров: {e}", exc_info=True)
        error_msg = str(e)
        
        # Более понятные сообщения об ошибках
        if "does not exist" in error_msg.lower() or "relation" in error_msg.lower():
            detail = "Таблица товаров не существует. Выполните миграцию БД: alembic upgrade head"
        elif "connection" in error_msg.lower() or "connect" in error_msg.lower():
            detail = "Не удалось подключиться к базе данных. Проверьте, что Docker контейнеры запущены."
        else:
            detail = f"Ошибка при загрузке товаров: {error_msg}"
        
        raise HTTPException(
            status_code=500,
            detail=detail
        )


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # Вычисляем остаток товара
        stock = await get_product_stock(db, product.id)
        
        # Возвращаем в том же формате, что и список, чтобы избежать проблем сериализации (UUID/JSON)
        return ProductResponse(
            id=str(product.id),
            name=product.name,
            brand=product.brand,
            price=product.price,
            category=product.category,
            images=product.images or [],
            tags=product.tags or [],
            description=product.description,
            article=product.article if hasattr(product, 'article') else None,
            vendor_code=product.vendor_code if hasattr(product, 'vendor_code') else None,
            barcode=product.barcode if hasattr(product, 'barcode') else None,
            unit=product.unit if hasattr(product, 'unit') else None,
            weight=product.weight if hasattr(product, 'weight') else None,
            volume=product.volume if hasattr(product, 'volume') else None,
            country=product.country if hasattr(product, 'country') else None,
            warranty=product.warranty if hasattr(product, 'warranty') else None,
            full_description=product.full_description if hasattr(product, 'full_description') else None,
            specifications=product.specifications if hasattr(product, 'specifications') else None,
            external_id=product.external_id if hasattr(product, 'external_id') else None,
            external_code=product.external_code if hasattr(product, 'external_code') else None,
            is_active=product.is_active if hasattr(product, 'is_active') else True,
            sync_status=product.sync_status if hasattr(product, 'sync_status') else None,
            sync_metadata=product.sync_metadata if hasattr(product, 'sync_metadata') else None,
            stock=stock
        )
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Ошибка при получении товара {product_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке товара: {str(e)}")


@router.get("/{product_id}/has-variants", response_model=dict)
async def has_product_variants(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Проверяет, есть ли у товара варианты"""
    try:
        result = await db.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        # Определяем parent_external_id
        parent_external_id = product.external_id
        if product.specifications and isinstance(product.specifications, dict):
            parent_id = product.specifications.get("parent_external_id")
            if parent_id and parent_id != "00000000-0000-0000-0000-000000000000":
                parent_external_id = parent_id
                # Если это вариант, ищем основной товар
                base_result = await db.execute(
                    select(Product).where(Product.external_id == parent_id)
                )
                base_product = base_result.scalar_one_or_none()
                if base_product:
                    parent_external_id = base_product.external_id
        
        # Ищем варианты
        if parent_external_id:
            # Ищем варианты по parent_external_id в specifications
            # Также проверяем sync_metadata для обратной совместимости
            variants_result = await db.execute(
                select(Product).where(
                    and_(
                        or_(
                            cast(Product.specifications["parent_external_id"], String) == parent_external_id,
                            # Также проверяем sync_metadata для обратной совместимости
                            cast(Product.sync_metadata["parent_external_id"], String) == parent_external_id
                        ),
                        Product.is_active == True,
                        Product.id != product_id  # Исключаем сам товар
                    )
                )
            )
            variants = variants_result.scalars().all()
            logger.info(f"Найдено {len(variants)} вариантов для товара {product.name} (parent_external_id={parent_external_id})")
            
            # Логируем найденные варианты для диагностики
            if variants:
                variant_articles = [v.article for v in variants if v.article]
                logger.info(f"Найденные варианты (артикулы): {variant_articles}")
            else:
                # Проверяем, есть ли товары с таким parent_external_id в других местах
                all_variants_check = await db.execute(
                    select(Product).where(
                        and_(
                            Product.is_active == True,
                            Product.id != product_id
                        )
                    )
                )
                all_products = all_variants_check.scalars().all()
                logger.debug(f"Всего товаров в БД (кроме текущего): {len(all_products)}")
                
                # Проверяем, есть ли товары с parent_external_id в specifications
                for p in all_products[:10]:  # Проверяем первые 10 для диагностики
                    if p.specifications and isinstance(p.specifications, dict):
                        p_parent = p.specifications.get("parent_external_id")
                        if p_parent:
                            logger.debug(f"Товар {p.article} имеет parent_external_id={p_parent} в specifications")
            return {"has_variants": len(variants) > 0, "variants_count": len(variants)}
        
        return {"has_variants": False, "variants_count": 0}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при проверке вариантов товара: {e}", exc_info=True)
        return {"has_variants": False, "variants_count": 0}


@router.get("/{product_id}/variants", response_model=ProductVariantsResponse)
async def get_product_variants(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await db.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        specifications = product.specifications or {}
        parent_external_id = None
        if isinstance(specifications, dict):
            parent_external_id = (
                specifications.get("parent_external_id")
                or specifications.get("Parent_Key")
                or specifications.get("parent_key")
            )
        if parent_external_id == "00000000-0000-0000-0000-000000000000":
            parent_external_id = None

        base_product = product
        if parent_external_id:
            base_result = await db.execute(
                select(Product).where(Product.external_id == parent_external_id)
            )
            base_candidate = base_result.scalars().first()
            if base_candidate:
                base_product = base_candidate
        else:
            parent_external_id = product.external_id

        variants: List[Product] = []
        if parent_external_id:
            # Ищем варианты по parent_external_id в specifications
            # Также проверяем sync_metadata для обратной совместимости
            variants_result = await db.execute(
                select(Product).where(
                    and_(
                        or_(
                            cast(Product.specifications["parent_external_id"], String) == parent_external_id,
                            # Также проверяем sync_metadata для обратной совместимости
                            cast(Product.sync_metadata["parent_external_id"], String) == parent_external_id
                        ),
                        Product.is_active == True
                    )
                )
            )
            variants = variants_result.scalars().all()
            
            # Дополнительный поиск: если варианты не найдены, ищем по артикулу
            # Варианты обычно имеют артикул вида "71136-G", где "71136" - артикул основного товара
            if not variants and product.article:
                base_article = product.article.strip()
                logger.info(f"Варианты не найдены по parent_external_id, ищем по артикулу (базовый артикул: {base_article})")
                
                # Ищем товары, артикул которых начинается с базового артикула и содержит дефис или другую букву
                # Например: 71136-G, 71136-S и т.д.
                article_variants_result = await db.execute(
                    select(Product).where(
                        and_(
                            Product.article.isnot(None),
                            Product.article != base_article,  # Исключаем сам основной товар
                            or_(
                                Product.article.like(f"{base_article}-%"),  # 71136-G, 71136-S
                                Product.article.like(f"{base_article}_%"),  # 71136_G, 71136_S
                                Product.article.like(f"{base_article} %"),  # 71136 G, 71136 S
                            ),
                            Product.is_active == True,
                            Product.id != product_id  # Исключаем сам товар
                        )
                    )
                )
                article_variants = article_variants_result.scalars().all()
                
                if article_variants:
                    logger.info(f"Найдено {len(article_variants)} вариантов по артикулу: {[v.article for v in article_variants]}")
                    # Проверяем, что у них правильный parent_external_id или устанавливаем его
                    for variant in article_variants:
                        if variant.specifications and isinstance(variant.specifications, dict):
                            variant_parent = variant.specifications.get("parent_external_id")
                            if variant_parent != parent_external_id:
                                # Обновляем parent_external_id если он неправильный
                                logger.warning(f"Обновляем parent_external_id для варианта {variant.article}: {variant_parent} -> {parent_external_id}")
                                variant.specifications["parent_external_id"] = parent_external_id
                                await db.flush()
                        else:
                            # Если specifications нет, создаем его
                            variant.specifications = {"parent_external_id": parent_external_id}
                            await db.flush()
                    
                    variants = article_variants
                    await db.commit()
            
            # Если текущий товар - это вариант (есть parent_external_id), убеждаемся, что он включен в список вариантов
            if parent_external_id and product.id not in [v.id for v in variants]:
                # Текущий товар - это вариант, но он не в списке, добавляем его
                variants.append(product)
                logger.info(f"Добавлен текущий товар {product.name} (ID: {product.id}) в список вариантов")
            
            logger.info(f"Найдено {len(variants)} вариантов для товара {product.name} (parent_external_id={parent_external_id})")
            
            # Логируем найденные варианты для диагностики
            if variants:
                variant_articles = [v.article for v in variants if v.article]
                logger.info(f"Найденные варианты (артикулы): {variant_articles}")
            else:
                logger.warning(f"Варианты не найдены для parent_external_id={parent_external_id}. Проверяем все товары с parent_external_id...")
                # Проверяем все товары для диагностики
                all_products_check = await db.execute(
                    select(Product).where(Product.is_active == True)
                )
                all_products = all_products_check.scalars().all()
                logger.debug(f"Всего товаров в БД: {len(all_products)}")
                
                # Проверяем, есть ли товары с parent_external_id в specifications
                found_parents = []
                for p in all_products:
                    if p.specifications and isinstance(p.specifications, dict):
                        p_parent = p.specifications.get("parent_external_id")
                        if p_parent == parent_external_id:
                            found_parents.append(p.article or p.name)
                
                if found_parents:
                    logger.warning(f"Найдены товары с parent_external_id={parent_external_id}: {found_parents[:5]}")
                else:
                    logger.warning(f"Товары с parent_external_id={parent_external_id} не найдены в specifications")

        # Получаем остатки для всех товаров (базовый + варианты)
        from app.models.product_stock import ProductStock
        all_product_ids = [base_product.id] + [v.id for v in variants]
        stocks_result = await db.execute(
            select(
                ProductStock.product_id,
                func.sum(ProductStock.available_quantity).label('total_stock')
            )
            .where(ProductStock.product_id.in_(all_product_ids))
            .group_by(ProductStock.product_id)
        )
        stocks_dict = {row[0]: float(row[1]) for row in stocks_result.all()}
        
        def _to_response(p: Product) -> ProductResponse:
            return ProductResponse(
                id=str(p.id),
                name=p.name,
                brand=p.brand,
                price=p.price,
                category=p.category,
                images=p.images or [],
                tags=p.tags or [],
                description=p.description,
                article=p.article if hasattr(p, "article") else None,
                vendor_code=p.vendor_code if hasattr(p, "vendor_code") else None,
                barcode=p.barcode if hasattr(p, "barcode") else None,
                unit=p.unit if hasattr(p, "unit") else None,
                weight=p.weight if hasattr(p, "weight") else None,
                volume=p.volume if hasattr(p, "volume") else None,
                country=p.country if hasattr(p, "country") else None,
                warranty=p.warranty if hasattr(p, "warranty") else None,
                full_description=p.full_description if hasattr(p, "full_description") else None,
                specifications=p.specifications if hasattr(p, "specifications") else None,
                external_id=p.external_id if hasattr(p, "external_id") else None,
                external_code=p.external_code if hasattr(p, "external_code") else None,
                is_active=p.is_active if hasattr(p, "is_active") else True,
                sync_status=p.sync_status if hasattr(p, "sync_status") else None,
                sync_metadata=p.sync_metadata if hasattr(p, "sync_metadata") else None,
                stock=stocks_dict.get(p.id)
            )

        return ProductVariantsResponse(
            base=_to_response(base_product),
            variants=[_to_response(v) for v in variants],
            parent_external_id=parent_external_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении вариантов товара: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке вариантов: {str(e)}")


@router.post("/", response_model=ProductResponse)
async def create_product(product: ProductCreate, db: AsyncSession = Depends(get_db)):
    db_product = Product(**product.dict())
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)
    return db_product


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    product: ProductCreate,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    db_product = result.scalar_one_or_none()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    for key, value in product.dict().items():
        setattr(db_product, key, value)
    
    await db.commit()
    await db.refresh(db_product)
    return db_product


@router.delete("/delete-all", response_model=dict)
async def delete_all_products(
    confirm: str = Query("false", description="Подтверждение удаления всех товаров (true/false)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Удаление всех товаров из базы данных.
    Требует подтверждения через параметр confirm=true
    """
    # Преобразуем строку в boolean
    confirm_bool = confirm.lower() in ("true", "1", "yes")
    
    if not confirm_bool:
        raise HTTPException(
            status_code=400,
            detail="Для удаления всех товаров необходимо указать confirm=true"
        )
    
    try:
        from app.models.product_stock import ProductStock
        
        # Сначала удаляем все остатки из product_stocks
        logger.info("Удаление остатков из product_stocks...")
        stocks_result = await db.execute(select(ProductStock))
        stocks = stocks_result.scalars().all()
        
        stocks_count = len(stocks)
        if stocks_count > 0:
            for stock in stocks:
                await db.delete(stock)
            await db.flush()  # Сохраняем удаление остатков перед удалением товаров
            logger.info(f"Удалено {stocks_count} записей остатков")
        
        # Получаем все товары
        result = await db.execute(select(Product))
        all_products = result.scalars().all()
        
        count = len(all_products)
        
        if count == 0:
            await db.commit()
            return {
                "message": "Товары не найдены",
                "deleted_count": 0,
                "stocks_deleted_count": stocks_count
            }
        
        # Удаляем все товары
        logger.info(f"Удаление {count} товаров...")
        for product in all_products:
            await db.delete(product)
        
        await db.commit()
        
        logger.warning(f"Удалено {count} товаров и {stocks_count} записей остатков из базы данных")
        
        return {
            "message": f"Удалено {count} товаров и {stocks_count} записей остатков",
            "deleted_count": count,
            "stocks_deleted_count": stocks_count
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка при удалении всех товаров: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при удалении товаров: {str(e)}"
        )


@router.delete("/{product_id}")
async def delete_product(product_id: UUID, db: AsyncSession = Depends(get_db)):
    from app.models.product_stock import ProductStock
    
    result = await db.execute(select(Product).where(Product.id == product_id))
    db_product = result.scalar_one_or_none()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Сначала удаляем остатки товара
    stocks_result = await db.execute(
        select(ProductStock).where(ProductStock.product_id == product_id)
    )
    stocks = stocks_result.scalars().all()
    for stock in stocks:
        await db.delete(stock)
    
    # Затем удаляем товар
    await db.delete(db_product)
    await db.commit()
    return {
        "message": "Product deleted successfully",
        "stocks_deleted": len(stocks)
    }


@router.delete("/test/all", response_model=dict)
async def delete_test_products(db: AsyncSession = Depends(get_db)):
    """
    Удаление тестовых товаров (товаров без external_id)
    """
    try:
        # Находим все товары без external_id (тестовые товары)
        result = await db.execute(
            select(Product).where(Product.external_id.is_(None))
        )
        test_products = result.scalars().all()
        
        count = len(test_products)
        
        if count == 0:
            return {
                "message": "Тестовые товары не найдены",
                "deleted_count": 0
            }
        
        # Удаляем все тестовые товары
        for product in test_products:
            await db.delete(product)
        
        await db.commit()
        
        return {
            "message": f"Удалено {count} тестовых товаров",
            "deleted_count": count
        }
    except Exception as e:
        await db.rollback()
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Ошибка при удалении тестовых товаров: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при удалении тестовых товаров: {str(e)}"
        )


# УДАЛЕНО: Фоновая задача синхронизации через OData API (_run_sync_task)
# УДАЛЕНО: Endpoint POST /api/products/sync-1c
# Товары теперь загружаются только через XML (CommerceML)
# OData API используется только для покупателей и продаж


@router.post("/sync-xml", response_model=dict)
async def sync_products_from_xml_url(
    background_tasks: BackgroundTasks,
    xml_url: str = Query(..., description="URL для скачивания CommerceML XML файла"),
    update_existing: bool = Query(True, description="Обновлять существующие товары"),
    async_mode: bool = Query(True, description="Асинхронный режим (с отслеживанием прогресса)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Синхронизация каталога товаров из 1С через CommerceML XML файл по URL.
    
    Загружает XML файл по указанной ссылке, парсит его и импортирует товары в базу данных.
    
    Если async_mode=True (по умолчанию), синхронизация запускается в фоне с отслеживанием прогресса.
    Используйте GET /api/products/sync-1c/status для получения статуса.
    """
    if async_mode:
        # Асинхронный режим с отслеживанием прогресса
        progress_service = get_sync_progress_service()
        task_id = await progress_service.create_task(
            task_type="products_xml",
            total=0,
            description=f"Синхронизация товаров из XML: {xml_url}"
        )
        
        # Запускаем в фоне через asyncio.create_task (для async функций)
        # Важно: используем create_task вместо background_tasks.add_task для async функций
        asyncio.create_task(
            _run_xml_sync_task(
                task_id=task_id,
                xml_url=xml_url,
                update_existing=update_existing,
            )
        )
        logger.info(f"✓ Фоновая задача синхронизации XML запущена через asyncio.create_task: {task_id}")
        
        return {
            "status": "started",
            "message": "Синхронизация из XML запущена в фоновом режиме",
            "task_id": task_id,
            "status_url": f"/api/products/sync-1c/status?task_id={task_id}",
        }
    else:
        # Синхронный режим
        try:
            async with CommerceMLXMLService() as xml_service:
                # 1. Парсим группы каталога и товары
                xml_content = await xml_service.download_xml_from_url(xml_url)
                groups_data = xml_service.parse_groups(xml_content)
                products_data = xml_service.parse_commerceml_xml(xml_content)
                
                # 2. Пытаемся загрузить offers.xml (цены и остатки) из .env
                offers_data = {}
                offers_url = os.getenv("ONEC_XML_OFFERS_URL")
                if offers_url:
                    try:
                        offers_data = await xml_service.load_and_parse_offers(offers_url)
                        logger.info(f"Загружено {len(offers_data)} предложений из offers.xml: {offers_url}")
                    except Exception as e:
                        logger.warning(f"Не удалось загрузить offers.xml из {offers_url}: {e}. Продолжаем без цен и остатков.")
                else:
                    logger.info("ONEC_XML_OFFERS_URL не указан в .env, пропускаем загрузку offers.xml")
            
            # 3. Импортируем группы
            products_service = OneCProductsService(db)
            groups_result = await products_service.import_groups_from_xml(groups_data)
            
            # 4. Импортируем товары с предложениями
            products_result = await products_service.import_products_from_xml(
                products_data,
                offers_data=offers_data if offers_data else None,
                update_existing=update_existing
            )
            
            return {
                "status": "success",
                "message": "Синхронизация из XML завершена",
                "groups": groups_result,
                "products": products_result,
            }
        except Exception as e:
            logger.error(f"Ошибка синхронизации из XML: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Ошибка синхронизации из XML: {str(e)}"
            )


async def _run_xml_sync_task(
    task_id: str,
    xml_url: str,
    update_existing: bool,
):
    """Фоновая задача для синхронизации из XML"""
    from app.database.connection import AsyncSessionLocal
    
    progress_service = get_sync_progress_service()
    
    try:
        logger.info(f"=== Начало фоновой задачи синхронизации XML (task_id={task_id}) ===")
        logger.info(f"URL: {xml_url}")
        logger.info(f"Задача добавлена в background_tasks, начинаем выполнение...")
        
        # Первое обновление прогресса
        try:
            await progress_service.update_task(
                task_id=task_id,
                status="running",
                stage="download",
                stage_description="Скачивание import.xml...",
                progress=1,
            )
            logger.info(f"✓ Прогресс обновлен: 1% - Скачивание import.xml...")
        except Exception as update_error:
            logger.error(f"✗ Ошибка при обновлении прогресса: {update_error}", exc_info=True)
            raise
        
        # Скачиваем и парсим XML
        async with CommerceMLXMLService() as xml_service:
            logger.info(f"Начинаем скачивание XML: {xml_url}")
            await progress_service.update_task(
                task_id=task_id,
                stage="download",
                stage_description="Скачивание import.xml (это может занять несколько минут)...",
                progress=2,
            )
            
            xml_content = await xml_service.download_xml_from_url(xml_url)
            logger.info(f"XML скачан: {len(xml_content)} байт")
            
            await progress_service.update_task(
                task_id=task_id,
                stage="parse",
                stage_description="Парсинг групп каталога...",
                progress=3,
            )
            groups_data = xml_service.parse_groups(xml_content)
            logger.info(f"Найдено групп: {len(groups_data)}")
            
            await progress_service.update_task(
                task_id=task_id,
                stage="parse",
                stage_description="Парсинг товаров...",
                progress=4,
            )
            products_data = xml_service.parse_commerceml_xml(xml_content)
            logger.info(f"Найдено товаров: {len(products_data)}")
            
            # Пытаемся загрузить offers.xml (цены и остатки) из .env
            offers_data = {}
            offers_url = os.getenv("ONEC_XML_OFFERS_URL")
            if offers_url:
                try:
                    await progress_service.update_task(
                        task_id=task_id,
                        stage="download",
                        stage_description="Скачивание offers.xml...",
                        progress=5,
                    )
                    logger.info(f"Пытаемся загрузить offers.xml: {offers_url}")
                    offers_data = await xml_service.load_and_parse_offers(offers_url)
                    logger.info(f"Загружено {len(offers_data)} предложений из offers.xml: {offers_url}")
                except Exception as e:
                    logger.warning(f"Не удалось загрузить offers.xml из {offers_url}: {e}. Продолжаем без цен и остатков.")
            else:
                logger.info("ONEC_XML_OFFERS_URL не указан в .env, пропускаем загрузку offers.xml")
        
        await progress_service.update_task(
            task_id=task_id,
            stage="import_groups",
            stage_description=f"Импорт {len(groups_data)} групп каталога...",
            progress=6,
        )
        
        # Импортируем группы и товары
        async with AsyncSessionLocal() as db:
            products_service = OneCProductsService(db)
            
            # 1. Импортируем группы
            logger.info(f"Начинаем импорт {len(groups_data)} групп")
            groups_result = await products_service.import_groups_from_xml(groups_data)
            logger.info(f"Группы импортированы: создано {groups_result.get('created', 0)}, обновлено {groups_result.get('updated', 0)}")
            
            await progress_service.update_task(
                task_id=task_id,
                stage="import_products",
                stage_description=f"Импорт {len(products_data)} товаров с вариантами...",
                progress=10,
                total=len(products_data),
            )
            
            # 2. Импортируем товары с предложениями
            logger.info(f"Начинаем импорт {len(products_data)} товаров (предложений: {len(offers_data) if offers_data else 0})")
            result = await products_service.import_products_from_xml(
                products_data,
                offers_data=offers_data if offers_data else None,
                update_existing=update_existing,
                progress_callback=lambda current, total_prod: progress_service.update_task(
                    task_id=task_id,
                    current=current,
                    progress=10 + int((current / total_prod) * 90) if total_prod > 0 else 10,
                    stage_description=f"Импорт товара {current} из {total_prod}",
                ),
            )
            logger.info(f"Импорт товаров завершен: создано {result.get('created', 0)}, обновлено {result.get('updated', 0)}, вариантов {result.get('variants_created', 0)}")
            
            # 3. Синхронизируем остатки из offers.xml, если он был загружен
            if offers_data:
                try:
                    await progress_service.update_task(
                        task_id=task_id,
                        stage="sync_stocks",
                        stage_description="Синхронизация остатков из offers.xml...",
                        progress=95,
                    )
                    from app.services.onec_stock_service import OneCStockService
                    async with OneCStockService(db) as stock_service:
                        stock_stats = await stock_service.sync_stocks_from_offers_data(offers_data)
                        logger.info(f"Синхронизация остатков завершена: {stock_stats}")
                        result["stocks"] = stock_stats
                except Exception as e:
                    logger.warning(f"Не удалось синхронизировать остатки: {e}", exc_info=True)
                    result["stocks_error"] = str(e)
        
        logger.info(f"Задача {task_id} успешно завершена")
        await progress_service.update_task(
            task_id=task_id,
            status="completed",
            progress=100,
            stage="completed",
            stage_description="Синхронизация завершена успешно",
            result={
                "groups": groups_result,
                "products": result,
            },
        )
        
        # Запускаем фоновую задачу для скачивания изображений с отслеживанием прогресса
        logger.info("Запуск фоновой задачи для скачивания изображений...")
        # Передаем базовый URL для построения абсолютных URL из относительных
        base_url = xml_url.rsplit('/', 1)[0] if '/' in xml_url else None
        # Создаем отдельную задачу для отслеживания прогресса загрузки изображений
        images_task_id = await progress_service.create_task(
            task_type="images_download",
            total=0,
            description="Загрузка изображений товаров"
        )
        asyncio.create_task(_download_product_images_background(base_url, images_task_id))
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка в фоновой задаче синхронизации XML (task_id={task_id}): {error_msg}", exc_info=True)
        try:
            await progress_service.update_task(
                task_id=task_id,
                status="failed",
                stage="failed",
                stage_description=f"Ошибка: {error_msg[:200]}",
                error=error_msg,
            )
        except Exception as update_error:
            logger.error(f"Не удалось обновить статус задачи после ошибки: {update_error}")
    finally:
        # Закрываем соединение с БД если нужно
        pass


@router.get("/sync-1c/status", response_model=dict)
async def get_sync_status(
    task_id: Optional[str] = Query(None, description="ID задачи синхронизации"),
    task_type: Optional[str] = Query("products_xml", description="Тип задачи: products_xml или images_download"),
):
    """
    Получить статус синхронизации товаров через XML или загрузки изображений.
    Если task_id не указан, возвращает статус последней задачи указанного типа.
    
    Примечание: задачи хранятся в памяти и теряются при перезапуске сервера.
    Если задача не найдена, возможно, сервер был перезапущен или задача была удалена.
    """
    progress_service = get_sync_progress_service()
    
    try:
        if task_id:
            task = await progress_service.get_task(task_id)
            if not task:
                # Пробуем получить последнюю задачу для информации
                latest_task = await progress_service.get_latest_task(task_type)
                if latest_task:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Задача {task_id} не найдена. Возможно, сервер был перезапущен. Последняя задача: {latest_task.get('task_id')}"
                    )
                else:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Задача {task_id} не найдена. Возможно, сервер был перезапущен или задача была удалена. Нет активных задач синхронизации."
                    )
        else:
            task = await progress_service.get_latest_task(task_type)
            if not task:
                task_type_name = "синхронизации товаров" if task_type == "products_xml" else "загрузки изображений"
                raise HTTPException(
                    status_code=404,
                    detail=f"Нет активных задач {task_type_name}. Запустите синхронизацию через POST /api/products/sync-xml"
                )
        
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении статуса задачи: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при получении статуса: {str(e)}")


@router.post("/sync-images", response_model=dict)
async def sync_product_images(
    product_id: Optional[UUID] = Query(None, description="ID товара для синхронизации изображений (если не указан, синхронизируются все товары без изображений)"),
    use_yml: bool = Query(True, description="Использовать YML как резервный источник изображений"),
    db: AsyncSession = Depends(get_db),
):
    """
    Синхронизация изображений для товаров из 1С и YML.
    
    Приоритет:
    1. Изображения из 1С (через mediaresource ссылки)
    2. Изображения из YML (по артикулу)
    
    Если product_id указан, синхронизируются изображения только для этого товара.
    Если не указан, синхронизируются все товары без изображений.
    """
    try:
        if product_id:
            # Синхронизация для одного товара
            result = await db.execute(select(Product).where(Product.id == product_id))
            product = result.scalar_one_or_none()
            if not product:
                raise HTTPException(status_code=404, detail="Товар не найден")
            
            products = [product]
        else:
            # Синхронизация для всех товаров без изображений
            result = await db.execute(
                select(Product).where(
                    or_(
                        Product.images.is_(None),
                        Product.images == [],
                        func.json_array_length(Product.images) == 0
                    )
                )
            )
            products = result.scalars().all()
        
        synced_count = 0
        errors = []
        
        for product in products:
            try:
                # Загружаем изображения из 1С
                images = []
                if product.external_id:
                    try:
                        async with OneCImagesService() as images_service:
                            # Получаем Ref_Key характеристики из specifications
                            characteristic_ref_key = None
                            if product.specifications and isinstance(product.specifications, dict):
                                char_ref = product.specifications.get("characteristic_ref_key")
                                if char_ref:
                                    characteristic_ref_key = char_ref
                            
                            onec_images = await images_service.get_images_for_product(
                                product_ref_key=product.external_id,
                                characteristic_ref_key=characteristic_ref_key
                            )
                            if onec_images:
                                images.extend(onec_images)
                                logger.info(f"Загружено {len(onec_images)} изображений из 1С для товара {product.name}")
                    except Exception as e:
                        logger.warning(f"Не удалось загрузить изображения из 1С для товара {product.name}: {e}")
                
                # Если изображений из 1С нет и разрешено использовать YML, загружаем из YML
                if not images and use_yml and product.article:
                    try:
                        async with YMLImagesService() as yml_service:
                            yml_images = await yml_service.get_images_by_article(product.article)
                            if yml_images:
                                images.extend(yml_images)
                                logger.info(f"Загружено {len(yml_images)} изображений из YML для товара {product.name}")
                    except Exception as e:
                        logger.warning(f"Не удалось загрузить изображения из YML для товара {product.name}: {e}")
                
                # Обновляем изображения товара
                if images:
                    product.images = images
                    synced_count += 1
                    logger.info(f"Обновлены изображения для товара {product.name}: {len(images)} изображений")
                else:
                    logger.debug(f"Изображения не найдены для товара {product.name} (article: {product.article}, external_id: {product.external_id})")
            
            except Exception as e:
                error_msg = f"Ошибка синхронизации изображений для товара {product.name}: {e}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)
        
        await db.commit()
        
        return {
            "status": "completed",
            "synced_count": synced_count,
            "total_processed": len(products),
            "errors": errors[:20],
            "error_count": len(errors),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка синхронизации изображений: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка синхронизации изображений: {str(e)}")


async def _download_product_images_background(base_url: Optional[str] = None, task_id: Optional[str] = None):
    """Фоновая задача для скачивания изображений товаров с отслеживанием прогресса"""
    from app.database.connection import AsyncSessionLocal
    from app.services.sync_progress_service import get_sync_progress_service
    
    progress_service = get_sync_progress_service()
    
    logger.info("=== Начало фоновой задачи скачивания изображений ===")
    if base_url:
        if not base_url.endswith("/"):
            base_url = f"{base_url}/"
        logger.info(f"Базовый URL для изображений: {base_url}")
    
    try:
        if task_id:
            await progress_service.update_task(
                task_id=task_id,
                status="running",
                stage="initializing",
                stage_description="Инициализация загрузки изображений...",
                progress=1,
            )
        
        async with AsyncSessionLocal() as db:
            from sqlalchemy import or_, func
            
            if task_id:
                await progress_service.update_task(
                    task_id=task_id,
                    stage="searching",
                    stage_description="Поиск товаров с изображениями для загрузки...",
                    progress=2,
                )
            
            # Находим товары с URL изображений, которые еще не скачаны (URL начинается с http или относительный путь)
            safe_images = case(
                (func.jsonb_typeof(Product.images) == "array", Product.images),
                else_=text("'[]'::jsonb")
            )
            result = await db.execute(
                select(Product).where(
                    Product.is_active == True,
                    Product.images.isnot(None),
                    func.jsonb_array_length(safe_images) > 0
                )
            )
            products = result.scalars().all()
            
            logger.info(f"Найдено {len(products)} товаров для скачивания изображений")
            
            # Подсчитываем общее количество изображений для прогресса
            total_images = 0
            for product in products:
                if product.images and isinstance(product.images, list):
                    for img_url in product.images:
                        if isinstance(img_url, str):
                            if img_url.startswith('http') or ('/' in img_url and not img_url.startswith('/static')):
                                total_images += 1
            
            logger.info(f"Всего изображений для загрузки: {total_images}")
            
            if task_id and total_images > 0:
                await progress_service.update_task(
                    task_id=task_id,
                    total=total_images,
                    current=0,
                    stage="downloading",
                    stage_description=f"Загрузка {total_images} изображений для {len(products)} товаров...",
                    progress=5,
                )
            
            async with ProductImagesDownloadService() as download_service:
                downloaded_count = 0
                error_count = 0
                downloaded_images = 0
                
                for idx, product in enumerate(products):
                    try:
                        if not product.images or not isinstance(product.images, list):
                            continue
                        
                        # Проверяем, есть ли URL изображений, которые нужно скачать
                        urls_to_download = []
                        for img_url in product.images:
                            if isinstance(img_url, str):
                                if img_url.startswith('http') or ('/' in img_url and not img_url.startswith('/static')):
                                    urls_to_download.append(img_url)
                        
                        if not urls_to_download:
                            continue
                        
                        # Скачиваем изображения с отслеживанием прогресса
                        async def download_with_progress(url: str) -> Optional[str]:
                            result = await download_service.download_image(url, str(product.id), base_url)
                            if result and task_id:
                                nonlocal downloaded_images
                                downloaded_images += 1
                                await progress_service.update_task(
                                    task_id=task_id,
                                    current=downloaded_images,
                                    progress=5 + int((downloaded_images / total_images) * 90) if total_images > 0 else 5,
                                    stage_description=f"Загружено {downloaded_images} из {total_images} изображений ({downloaded_count + 1}/{len(products)} товаров)",
                                )
                            return result
                        
                        # Скачиваем изображения параллельно, но с ограничением
                        semaphore = asyncio.Semaphore(3)  # Максимум 3 одновременные загрузки
                        async def download_with_semaphore(url: str) -> Optional[str]:
                            async with semaphore:
                                return await download_with_progress(url)
                        
                        tasks = [download_with_semaphore(url) for url in urls_to_download]
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        
                        downloaded_urls = []
                        for result in results:
                            if isinstance(result, Exception):
                                logger.error(f"Ошибка при скачивании изображения: {result}")
                            elif result:
                                downloaded_urls.append(result)
                        
                        if downloaded_urls:
                            # Обновляем список изображений: заменяем URL на скачанные
                            updated_images = []
                            url_index = 0
                            for img_url in product.images:
                                if img_url in urls_to_download and url_index < len(downloaded_urls):
                                    updated_images.append(downloaded_urls[url_index])
                                    url_index += 1
                                else:
                                    updated_images.append(img_url)
                            
                            product.images = updated_images
                            downloaded_count += 1
                            logger.info(f"Обновлены изображения для товара {product.name}: {len(downloaded_urls)} скачано")
                        
                        # Коммитим каждые 10 товаров
                        if downloaded_count % 10 == 0:
                            await db.commit()
                            logger.info(f"Промежуточный коммит: обработано {downloaded_count} товаров")
                    
                    except Exception as e:
                        error_count += 1
                        logger.error(f"Ошибка при скачивании изображений для товара {product.name}: {e}", exc_info=True)
                        continue
                
                await db.commit()
                logger.info(f"=== Фоновая задача скачивания изображений завершена ===")
                logger.info(f"Скачано изображений для {downloaded_count} товаров, ошибок: {error_count}")
                
                if task_id:
                    await progress_service.update_task(
                        task_id=task_id,
                        status="completed",
                        progress=100,
                        stage="completed",
                        stage_description=f"Загрузка завершена: {downloaded_count} товаров обновлено, {downloaded_images} изображений загружено",
                        result={
                            "products_updated": downloaded_count,
                            "images_downloaded": downloaded_images,
                            "errors": error_count,
                        },
                    )
    
    except Exception as e:
        logger.error(f"Критическая ошибка в фоновой задаче скачивания изображений: {e}", exc_info=True)
        if task_id:
            try:
                await progress_service.update_task(
                    task_id=task_id,
                    status="failed",
                    stage="failed",
                    stage_description=f"Ошибка: {str(e)[:200]}",
                    error=str(e),
                )
            except Exception as update_error:
                logger.error(f"Не удалось обновить статус задачи после ошибки: {update_error}")
