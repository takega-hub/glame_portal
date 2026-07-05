"""
API администратора: управление покупателями
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, func, literal_column, text, update
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID

logger = logging.getLogger(__name__)

from app.database.connection import get_db
from app.models.user import User
from app.models.purchase_history import PurchaseHistory
from app.models.product import Product
from app.models.loyalty_transaction import LoyaltyTransaction
from app.models.saved_look import SavedLook
from app.models.look import Look
from app.models.customer_favorite_product import CustomerFavoriteProduct
from app.models.customer_segment import CustomerSegment
from app.models.user_segment import UserSegment
from app.models.store import Store
from app.models.live_stylist_conversation import LiveStylistConversation
from app.models.stylist_chat_message import StylistChatMessage
from app.api.dependencies import require_admin
from app.services.loyalty_service import LoyaltyService
from app.services.customer_analytics_service import CustomerAnalyticsService
from app.services.purchase_product_fields import derive_purchase_brand, derive_purchase_category
from app.services.sales_record_filters import is_analytics_eligible_product
try:
    from app.services.customer_sync_service import CustomerSyncService  # type: ignore
except Exception:
    CustomerSyncService = None  # type: ignore
from typing import Dict, Any, Tuple
from app.services.customer_city_refresh_service import CustomerCityRefreshService
from app.services.birthday_crm_service import BirthdayCrmService
from fastapi.responses import StreamingResponse
import io
import pandas as pd
from datetime import datetime, timedelta, timezone

router = APIRouter()


@router.post("/{user_id}/force-sync")
async def force_sync_customer(
    user_id: str,
    days: int = Query(3650, ge=1, le=10000, description="Глубина синхронизации продаж в днях"),
    replace_history: bool = Query(True, description="Очистить текущую историю покупок перед импортом"),
    db: AsyncSession = Depends(get_db)
):
    """Принудительно обновляет покупки, бонусные баллы и связи товаров для одного покупателя."""
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат user_id")

    result = await db.execute(select(User).where(User.id == uid, User.is_customer == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Покупатель не найден")
    if not user.customer_id_1c and not user.discount_card_id_1c:
        raise HTTPException(status_code=400, detail="У покупателя нет идентификаторов 1С для синхронизации")

    try:
        import sys
        from pathlib import Path

        backend_dir = Path(__file__).resolve().parents[3]
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))

        from sync_customer_sales_and_points import (
            DEFAULT_LIMIT,
            fetch_all_customer_sales,
            recalculate_customer_metrics,
            sync_loyalty,
            to_kopecks,
            upsert_purchase,
        )
        from app.services.onec_customers_service import OneCCustomersService
        from app.services.sales_product_link_service import SalesProductLinkService

        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        purchases = []
        source_stats: Dict[str, int] = {}

        async with OneCCustomersService() as onec:
            purchases, source_stats = await fetch_all_customer_sales(
                onec=onec,
                user=user,
                start_date=start_date,
                end_date=None,
                limit=DEFAULT_LIMIT,
            )

            if replace_history:
                old_rows = await db.execute(select(PurchaseHistory).where(PurchaseHistory.user_id == uid))
                for row in old_rows.scalars().all():
                    await db.delete(row)
                await db.flush()

            stats = {"created": 0, "updated": 0, "skipped": 0}
            product_cache: Dict[str, Dict[str, Any]] = {}
            for purchase in purchases:
                status_value = await upsert_purchase(db, user, onec, purchase, product_cache)
                stats[status_value] = stats.get(status_value, 0) + 1

            try:
                loyalty = await sync_loyalty(db, onec, user)
            except Exception as loyalty_error:
                logger.warning(f"Не удалось синхронизировать бонусы для {uid}: {loyalty_error}")
                loyalty = {"updated": False, "balance": int(user.loyalty_points or 0)}

        await recalculate_customer_metrics(db, user)
        from app.services.customer_analytics_service import CustomerAnalyticsService
        await CustomerAnalyticsService(db).refresh_preferred_store_by_count(uid, commit=False)
        link_service = SalesProductLinkService(db)
        link_stats = await link_service.backfill_missing_purchase_product_links(user_id=uid)
        normalized_fields = await link_service.normalize_purchase_product_fields(user_id=uid)
        user.synced_at = datetime.now(timezone.utc)
        await db.commit()

        total_amount = sum(to_kopecks(item.get("Сумма", 0)) for item in purchases) / 100
        return {
            "success": True,
            "message": "Покупки, бонусные баллы и связи товаров обновлены",
            "source": "customer_id_1c + discount_card_id_1c + initial_balances",
            "stats": {
                **stats,
                "fetched": len(purchases),
                "source_stats": source_stats,
                "total_amount": total_amount,
                "linked_products": link_stats,
                "normalized_product_fields": normalized_fields,
                "loyalty_balance": loyalty.get("balance"),
                "loyalty_updated": loyalty.get("updated", False),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Ошибка принудительной синхронизации покупателя {user_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка синхронизации: {e}")


@router.post("/preferred-store/refresh")
async def refresh_preferred_store(
    user_id: Optional[str] = Query(None, description="UUID пользователя; если не указан — для всех"),
    db: AsyncSession = Depends(get_db)
):
    """
    Обновляет предпочитаемый магазин у пользователя(ей) по правилу:
    магазин с максимальным количеством покупок (по store_id_1c).
    """
    service = CustomerAnalyticsService(db)
    updated = 0
    results = []
    try:
        if user_id:
            try:
                uid = UUID(user_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="Неверный формат user_id")
            res = await service.refresh_preferred_store_by_count(uid)
            updated += 1
            results.append(res)
        else:
            rows = await db.execute(select(User.id).where(User.is_customer == True))
            ids = [r[0] for r in rows.all()]
            for uid in ids:
                res = await service.refresh_preferred_store_by_count(uid)
                results.append(res)
                updated += 1
        return {"updated": updated, "results_preview": results[:20]}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logging.getLogger(__name__).error(f"Ошибка refresh_preferred_store: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Ошибка обновления предпочитаемого магазина")

class CustomerListItem(BaseModel):
    id: str
    phone: Optional[str]
    email: Optional[str]
    full_name: Optional[str]
    city: Optional[str]
    birth_date: Optional[str] = None
    gender: Optional[str] = None  # "male", "female", или None
    customer_segment: Optional[str]
    loyalty_points: int
    total_purchases: int
    total_spent: float
    last_purchase_date: Optional[str]

    class Config:
        from_attributes = True


class CustomersListResponse(BaseModel):
    customers: List[CustomerListItem]
    total: int
    limit: int
    offset: int


class CustomerDetailResponse(BaseModel):
    id: str
    phone: Optional[str] = None
    email: Optional[str] = None
    full_name: Optional[str] = None
    city: Optional[str] = None
    birth_date: Optional[str] = None
    gender: Optional[str] = None  # "male", "female", или None
    discount_card_number: Optional[str] = None
    customer_segment: Optional[str] = None
    loyalty_points: int
    total_purchases: int
    total_spent: float
    average_check: Optional[float] = None
    last_purchase_date: Optional[str] = None
    rfm_score: Optional[dict] = None
    purchase_preferences: Optional[dict] = None
    segments: List[dict]
    created_at: str
    preferred_store_name: Optional[str] = None
    preferred_store_share: Optional[float] = None
    store_distribution: Optional[List[dict]] = None

    class Config:
        from_attributes = True


class LoyaltyAdjustRequest(BaseModel):
    points: int
    reason: str
    description: Optional[str] = None


class AdminLoyaltyTransactionItem(BaseModel):
    id: str
    type: str
    points: int
    balance_after: int
    reason: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    source_id: Optional[str] = None
    expires_at: Optional[str] = None
    created_at: str


class AdminLoyaltyResponse(BaseModel):
    balance: int
    transactions: List[AdminLoyaltyTransactionItem]
    program_info: dict
    level_progress: dict
    summary: dict


class AdminSavedLookItem(BaseModel):
    id: str
    look_id: str
    look_name: str
    save_type: str
    notes: Optional[str] = None
    is_purchased: bool
    look_style: Optional[str] = None
    look_mood: Optional[str] = None
    look_description: Optional[str] = None
    look_image_url: Optional[str] = None
    look_image_urls: List[str] = []
    product_ids: List[str] = []
    created_at: Optional[str] = None


class AdminFavoriteProductItem(BaseModel):
    id: str
    name: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    article: Optional[str] = None
    external_code: Optional[str] = None
    price: Optional[float] = None
    image_url: Optional[str] = None
    source: str


class AdminSavedItemsResponse(BaseModel):
    saved_looks: List[AdminSavedLookItem]
    favorite_products: List[AdminFavoriteProductItem]
    source_notes: List[str] = []

@router.post("/cities/refresh")
async def refresh_customer_cities(
    limit: int = Query(1000, ge=1, le=100000),
    only_empty: bool = Query(True),
    user_id: Optional[str] = Query(None),
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db)
):
    service = CustomerCityRefreshService(db)
    if user_id:
        try:
            uid = UUID(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверный формат user_id")
        stats = await service.refresh_for_user(uid)
    else:
        stats = await service.refresh_all(limit=limit, only_empty=only_empty)
    return {"success": True, "stats": stats}


@router.get("", response_model=CustomersListResponse)
async def get_customers(
    segment: Optional[str] = Query(None),
    segment_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort: Optional[str] = Query("total_spent"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Список всех покупателей"""
    try:
        logger.info(f"Получение списка покупателей: segment={segment}, segment_id={segment_id}, search={search}, sort={sort}, limit={limit}, offset={offset}")
        
        # Используем безопасный доступ к колонкам через __table__
        total_spent_col = User.__table__.columns.get("total_spent")
        if total_spent_col is None:
            total_spent_col = literal_column("total_spent")
        
        total_purchases_col = User.__table__.columns.get("total_purchases")
        if total_purchases_col is None:
            total_purchases_col = literal_column("total_purchases")
        
        last_purchase_col = User.__table__.columns.get("last_purchase_date")
        if last_purchase_col is None:
            last_purchase_col = literal_column("last_purchase_date")
        
        created_at_col = User.__table__.columns.get("created_at")
        if created_at_col is None:
            created_at_col = literal_column("created_at")
        
        # Фильтр по is_customer - используем стандартный подход SQLAlchemy
        # Пробуем использовать атрибут модели, если доступен
        try:
            stmt = select(User).where(User.is_customer == True)
        except (AttributeError, Exception) as e:
            # Если атрибут недоступен, используем колонку из таблицы
            logger.warning(f"Не удалось использовать User.is_customer напрямую: {e}, используем колонку таблицы")
            is_customer_col = User.__table__.columns.get("is_customer")
            if is_customer_col is not None:
                stmt = select(User).where(is_customer_col == True)
            else:
                # Последний вариант - literal_column
                stmt = select(User).where(literal_column("is_customer") == True)
        
        # Вспомогательные функции для правил сегментов удалены в пользу app.api.customer_segmentation

        # Фильтр по сегменту (по названию или ID)
        target_segment_obj = None
        
        if segment_id:
            try:
                sid = UUID(segment_id)
                res = await db.execute(select(CustomerSegment).where(CustomerSegment.id == sid))
                target_segment_obj = res.scalar_one_or_none()
            except Exception as e:
                logger.warning(f"Invalid segment_id {segment_id}: {e}")
        
        if not target_segment_obj and segment:
            try:
                # Ищем сегмент в CustomerSegment по названию
                segment_stmt = select(CustomerSegment).where(CustomerSegment.name == segment, CustomerSegment.is_active == True)
                segment_result = await db.execute(segment_stmt)
                target_segment_obj = segment_result.scalar_one_or_none()
            except Exception:
                pass
        
        if target_segment_obj:
            # Для сегментов с правилами фильтруем по правилам
            rules = getattr(target_segment_obj, "rules", None) or {}
            is_auto = getattr(target_segment_obj, "is_auto_generated", False)
            
            try:
                from app.api.customer_segmentation import _normalize_to_segment_rules, _build_select_for_rules
                
                # Нормализуем правила (приводим авто-правила к стандартному формату)
                normalized_rules_model = _normalize_to_segment_rules(rules, is_auto)
                normalized_rules_dict = normalized_rules_model.dict()
                
                # Строим запрос с использованием общей логики
                stmt_rules, _ = _build_select_for_rules(normalized_rules_dict)
                subq = stmt_rules.subquery()
                
                stmt = stmt.where(User.id.in_(select(subq.c.id)))
                logger.info(f"Найден сегмент '{target_segment_obj.name}' (ID: {target_segment_obj.id}), применены правила фильтрации")
            except Exception as e:
                logger.warning(f"Не удалось применить правила сегмента '{target_segment_obj.name}', пробуем через UserSegment: {e}")
                stmt = stmt.join(UserSegment, User.id == UserSegment.user_id, isouter=False).where(UserSegment.segment_id == target_segment_obj.id)
        elif segment:
            # Если не найден объект сегмента, но передано имя - фильтруем по полю customer_segment (обратная совместимость)
            logger.info(f"Сегмент '{segment}' не найден в CustomerSegment, фильтруем по customer_segment")
            try:
                stmt = stmt.where(User.customer_segment == segment)
            except (AttributeError, Exception) as e:
                logger.warning(f"Ошибка при фильтрации по customer_segment '{segment}': {e}, используем колонку таблицы")
                customer_segment_col = User.__table__.columns.get("customer_segment")
                if customer_segment_col is not None:
                    stmt = stmt.where(customer_segment_col == segment)
                else:
                    logger.error(f"Колонка customer_segment не найдена в таблице users")
                    return []
        
        # Поиск - используем прямое обращение к атрибутам модели для ilike
        if search and search.strip():
            search_term = f"%{search.strip()}%"
            search_conditions = []
            
            # Используем прямое обращение к атрибутам модели
            # ilike работает с атрибутами модели напрямую
            # NULL значения автоматически пропускаются (ilike с NULL возвращает NULL, что в WHERE = false)
            try:
                if hasattr(User, 'phone'):
                    search_conditions.append(User.phone.ilike(search_term))
                if hasattr(User, 'email'):
                    search_conditions.append(User.email.ilike(search_term))
                if hasattr(User, 'full_name'):
                    search_conditions.append(User.full_name.ilike(search_term))
                if hasattr(User, 'city'):
                    search_conditions.append(User.city.ilike(search_term))
            except (AttributeError, Exception) as e:
                logger.warning(f"Ошибка при использовании атрибутов модели для поиска: {e}, используем колонки таблицы")
                # Fallback на колонки таблицы
                phone_col = User.__table__.columns.get("phone")
                email_col = User.__table__.columns.get("email")
                full_name_col = User.__table__.columns.get("full_name")
                city_col = User.__table__.columns.get("city")
                
                if phone_col:
                    search_conditions.append(phone_col.ilike(search_term))
                if email_col:
                    search_conditions.append(email_col.ilike(search_term))
                if full_name_col:
                    search_conditions.append(full_name_col.ilike(search_term))
                if city_col:
                    search_conditions.append(city_col.ilike(search_term))
            
            if search_conditions:
                stmt = stmt.where(or_(*search_conditions))
                logger.info(f"Применен поиск: '{search.strip()}' по полям: phone, email, full_name")
        
        # Подсчитываем общее количество записей (до применения limit/offset)
        # Используем distinct count для User.id, чтобы правильно считать при join'ах
        try:
            # Создаем count_stmt на основе тех же условий, но считаем distinct User.id
            count_stmt = select(func.count(func.distinct(User.id)))
            
            # 1. Базовое условие is_customer
            try:
                count_stmt = count_stmt.where(User.is_customer == True)
            except:
                is_customer_col = User.__table__.columns.get("is_customer")
                if is_customer_col:
                    count_stmt = count_stmt.where(is_customer_col == True)
            
            # 2. Фильтр по сегменту
            target_segment_obj_count = None
            if segment_id:
                try:
                    sid = UUID(segment_id)
                    res = await db.execute(select(CustomerSegment).where(CustomerSegment.id == sid))
                    target_segment_obj_count = res.scalar_one_or_none()
                except Exception:
                    pass
            
            if not target_segment_obj_count and segment:
                 try:
                    segment_stmt = select(CustomerSegment).where(CustomerSegment.name == segment, CustomerSegment.is_active == True)
                    segment_result = await db.execute(segment_stmt)
                    target_segment_obj_count = segment_result.scalar_one_or_none()
                 except Exception:
                    pass

            if target_segment_obj_count:
                rules = getattr(target_segment_obj_count, "rules", None) or {}
                is_auto = getattr(target_segment_obj_count, "is_auto_generated", False)
                try:
                    from app.api.customer_segmentation import _normalize_to_segment_rules, _build_select_for_rules
                    
                    normalized_rules_model = _normalize_to_segment_rules(rules, is_auto)
                    normalized_rules_dict = normalized_rules_model.dict()
                    
                    stmt_rules, _ = _build_select_for_rules(normalized_rules_dict)
                    subq = stmt_rules.subquery()
                    
                    # Фильтруем подсчет так же, как и основной запрос
                    count_stmt = count_stmt.where(User.id.in_(select(subq.c.id)))
                except Exception:
                    # Fallback на UserSegment
                    count_stmt = count_stmt.join(UserSegment, User.id == UserSegment.user_id, isouter=False).where(UserSegment.segment_id == target_segment_obj_count.id)
            elif segment:
                try:
                    customer_segment_col = User.__table__.columns.get("customer_segment")
                    if customer_segment_col is not None:
                        count_stmt = count_stmt.where(customer_segment_col == segment)
                    else:
                        count_stmt = count_stmt.where(literal_column("customer_segment") == segment)
                except Exception:
                    pass
            
            # 3. Поиск
            if search and search.strip():
                search_term = f"%{search.strip()}%"
                search_conditions = []
                # Проверяем наличие атрибутов модели перед использованием ilike
                try:
                    if hasattr(User, 'phone'):
                        search_conditions.append(User.phone.ilike(search_term))
                    if hasattr(User, 'email'):
                        search_conditions.append(User.email.ilike(search_term))
                    if hasattr(User, 'full_name'):
                        search_conditions.append(User.full_name.ilike(search_term))
                    if hasattr(User, 'city'):
                        search_conditions.append(User.city.ilike(search_term))
                except Exception:
                    # Fallback на колонки таблицы
                    for col_name in ['phone', 'email', 'full_name', 'city']:
                        col = User.__table__.columns.get(col_name)
                        if col is not None:
                            search_conditions.append(col.ilike(search_term))
                            
                if search_conditions:
                    count_stmt = count_stmt.where(or_(*search_conditions))
            
            # Выполняем подсчет
            count_result = await db.execute(count_stmt)
            total = count_result.scalar() or 0
            
        except Exception as e:
            logger.error(f"Ошибка при подсчете записей: {e}")
            total = 0
        
        # Сортировка - используем __table__.columns для доступа к колонкам
        if sort == "total_spent":
            stmt = stmt.order_by(desc(total_spent_col))
        elif sort == "total_purchases":
            stmt = stmt.order_by(desc(total_purchases_col))
        elif sort == "last_purchase":
            stmt = stmt.order_by(desc(last_purchase_col))
        else:
            stmt = stmt.order_by(desc(created_at_col))
        
        stmt = stmt.limit(limit).offset(offset)
        
        result = await db.execute(stmt)
        users = result.scalars().all()
        
        # Получаем gender через прямое SQL для всех пользователей
        # Это гарантирует, что мы получим данные даже если ORM не видит поле
        user_ids = [u.id for u in users]  # UUID объекты
        gender_map = {}
        if user_ids:
            try:
                from sqlalchemy import text
                # Используем простой подход с IN и правильным форматом для PostgreSQL
                # Преобразуем UUID в строки для запроса
                user_ids_str = [str(uid) for uid in user_ids]
                # Создаем строку с UUID для IN запроса
                uuids_str = ','.join([f"'{uid}'" for uid in user_ids_str])
                gender_query = text(f"""
                    SELECT id::text, gender 
                    FROM users 
                    WHERE id::text IN ({uuids_str})
                """)
                gender_result = await db.execute(gender_query)
                for row in gender_result:
                    gender_map[row[0]] = row[1]
                logger.info(f"✅ Получено gender для {len(gender_map)} пользователей из {len(user_ids)}")
            except Exception as e:
                logger.warning(f"Ошибка при получении gender через SQL: {e}", exc_info=True)
                # Fallback: пробуем через ORM напрямую
                for u in users:
                    try:
                        user_gender = getattr(u, 'gender', None)
                        if user_gender:
                            gender_map[str(u.id)] = user_gender
                    except:
                        pass
        
        # Безопасная обработка данных
        customers = []
        for u in users:
            try:
                # Безопасное получение last_purchase_date
                last_purchase = getattr(u, "last_purchase_date", None)
                last_purchase_str = None
                if last_purchase:
                    if hasattr(last_purchase, 'isoformat'):
                        last_purchase_str = last_purchase.isoformat()
                    else:
                        last_purchase_str = str(last_purchase)

                birth_date = getattr(u, "birth_date", None)
                birth_date_str = birth_date.isoformat() if hasattr(birth_date, "isoformat") else None
                
                # Безопасное получение total_spent (хранится в копейках)
                total_spent_value = getattr(u, "total_spent", 0) or 0
                if isinstance(total_spent_value, (int, float)):
                    total_spent_float = float(total_spent_value) / 100.0
                else:
                    total_spent_float = 0.0
                
                # Извлекаем gender - сначала из карты (SQL), потом из объекта
                user_id_str = str(u.id)
                user_gender = gender_map.get(user_id_str)
                if user_gender is None:
                    # Fallback на getattr
                    user_gender = getattr(u, "gender", None)
                
                customers.append(
                    CustomerListItem(
                        id=user_id_str,
                        phone=getattr(u, "phone", None),
                        email=getattr(u, "email", None),
                        full_name=getattr(u, "full_name", None),
                        city=getattr(u, "city", None),
                        birth_date=birth_date_str,
                        gender=user_gender,
                        customer_segment=getattr(u, "customer_segment", None),
                        loyalty_points=int(getattr(u, "loyalty_points", 0) or 0),
                        total_purchases=int(getattr(u, "total_purchases", 0) or 0),
                        total_spent=total_spent_float,
                        last_purchase_date=last_purchase_str
                    )
                )
            except Exception as e:
                logger.error(f"Ошибка при обработке покупателя {u.id}: {e}", exc_info=True)
                # Пропускаем проблемного покупателя, но продолжаем обработку остальных
                continue
        
        return CustomersListResponse(
            customers=customers,
            total=total,
            limit=limit,
            offset=offset
        )
        
    except Exception as e:
        logger.error(f"Ошибка при получении списка покупателей: {e}", exc_info=True)
        # Возвращаем пустой список вместо ошибки 500, чтобы фронтенд мог работать
        return CustomersListResponse(
            customers=[],
            total=0,
            limit=limit,
            offset=offset
        )


@router.get("/birthday-crm")
async def get_birthday_crm_cards(
    days_ahead: int = Query(3, ge=0, le=30, description="Окно до дня рождения в днях; по ТЗ по умолчанию 3"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Карточки CRM для клиентов с ДР в ближайшие дни.

    Возвращает только черновики поздравлений и рекомендации по бонусу: автоотправка
    клиентам намеренно отключена (`auto_send=false`, `status=draft`).
    """
    try:
        return await BirthdayCrmService(db).get_upcoming_cards(days_ahead=days_ahead, limit=limit)
    except Exception as e:
        logger.exception("Ошибка формирования birthday CRM карточек: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка формирования birthday CRM карточек")


@router.get("/export")
async def export_customers_xlsx_entry(
    segment: Optional[str] = Query(None),
    segment_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    return await export_customers_xlsx(segment=segment, segment_id=segment_id, search=search, db=db)


@router.get("/{user_id}", response_model=CustomerDetailResponse)
async def get_customer_detail(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Детали покупателя. Синхронизация данных из 1С выполняется через общую синхронизацию."""
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат user_id")
    
    is_customer_col = getattr(User, "is_customer", None) or literal_column("is_customer")
    stmt = select(User).where(User.id == uid, is_customer_col == True)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Покупатель не найден")
    
    # Вычисляем предпочтительный магазин (с учётом дедупликации)
    try:
        PACKAGING_THRESHOLD = 500
        base_filter = and_(PurchaseHistory.user_id == uid, PurchaseHistory.total_amount >= PACKAGING_THRESHOLD)
        purchase_q = (
            select(
                PurchaseHistory,
                Store.name.label("store_name")
            )
            .outerjoin(Store, PurchaseHistory.store_id_1c == Store.external_id)
            .where(base_filter)
            .order_by(desc(PurchaseHistory.purchase_date))
        )
        rs = await db.execute(purchase_q)
        raw_rows = rs.all()

        def dedup_key(p):
            doc = p.document_id_1c or ""
            prod = p.product_id_1c or (p.product_article or "")
            ts = p.purchase_date.isoformat() if p.purchase_date else ""
            amt = p.total_amount or 0
            return (doc, prod, ts, amt)

        dedup_map = {}
        for p, sname in raw_rows:
            key = dedup_key(p)
            cur = dedup_map.get(key)
            # предпочитаем вариант с известным магазином
            prefer_new = False
            if cur is None:
                prefer_new = True
            else:
                cur_p, cur_sname = cur
                if (not cur_p.store_id_1c) and p.store_id_1c:
                    prefer_new = True
            if prefer_new:
                dedup_map[key] = (p, sname)

        store_counts = {}
        total_with_store = 0
        for p, sname in dedup_map.values():
            if sname:
                store_counts[sname] = store_counts.get(sname, 0) + 1
                total_with_store += 1

        preferred_store_name = None
        preferred_store_share = None
        distribution = []
        if total_with_store > 0:
            for name, cnt in sorted(store_counts.items(), key=lambda x: (-x[1], x[0])):
                share = round(cnt * 100.0 / total_with_store, 2)
                distribution.append({"store_name": name, "count": cnt, "share_pct": share})
            preferred_store_name, top_cnt = max(store_counts.items(), key=lambda x: x[1])
            preferred_store_share = round(top_cnt * 100.0 / total_with_store, 2)
        else:
            preferred_store_name = getattr(user, "preferred_store_name", None)
            raw_share = getattr(user, "preferred_store_share", None)
            preferred_store_share = (float(raw_share) * 100.0) if raw_share is not None and float(raw_share) <= 1 else raw_share
    except Exception as e:
        logger.warning(f"Не удалось вычислить предпочтительный магазин для {uid}: {e}")
        preferred_store_name = getattr(user, "preferred_store_name", None)
        raw_share = getattr(user, "preferred_store_share", None)
        preferred_store_share = (float(raw_share) * 100.0) if raw_share is not None and float(raw_share) <= 1 else raw_share
        distribution = None

    # Получаем сегменты
    stmt = (
        select(CustomerSegment)
        .join(UserSegment)
        .where(UserSegment.user_id == uid)
    )
    result = await db.execute(stmt)
    segments = result.scalars().all()
    
    # Получаем gender через прямой SQL запрос для надежности
    user_gender = None
    try:
        gender_query = text("SELECT gender FROM users WHERE id = :user_id")
        gender_result = await db.execute(gender_query, {"user_id": str(uid)})
        gender_row = gender_result.first()
        if gender_row:
            user_gender = gender_row[0]
        logger.debug(f"Gender для {uid} из БД: {user_gender}")
    except Exception as e:
        logger.warning(f"Ошибка при получении gender через SQL: {e}, используем getattr")
        user_gender = getattr(user, "gender", None)
    
    return CustomerDetailResponse(
        id=str(user.id),
        phone=getattr(user, "phone", None),
        email=getattr(user, "email", None),
        full_name=getattr(user, "full_name", None),
        city=getattr(user, "city", None),
        birth_date=getattr(user, "birth_date", None).isoformat() if getattr(user, "birth_date", None) else None,
        gender=user_gender,
        discount_card_number=getattr(user, "discount_card_number", None),
        customer_segment=getattr(user, "customer_segment", None),
        loyalty_points=getattr(user, "loyalty_points", 0) or 0,
        total_purchases=getattr(user, "total_purchases", 0) or 0,
        total_spent=(getattr(user, "total_spent", 0) or 0) / 100,
        average_check=(getattr(user, "average_check", None) / 100) if getattr(user, "average_check", None) else None,
        last_purchase_date=getattr(user, "last_purchase_date", None).isoformat() if getattr(user, "last_purchase_date", None) else None,
        rfm_score=getattr(user, "rfm_score", None),
        purchase_preferences=getattr(user, "purchase_preferences", None),
        segments=[{"id": str(s.id), "name": s.name} for s in segments],
        created_at=getattr(user, "created_at", None).isoformat() if getattr(user, "created_at", None) else None,
        preferred_store_name=preferred_store_name,
        preferred_store_share=preferred_store_share,
        store_distribution=distribution
    )


class PurchaseHistoryItem(BaseModel):
    id: str
    purchase_date: str
    product_name: Optional[str]
    product_article: Optional[str]
    quantity: int
    price: float  # в рублях
    total_amount: float  # в рублях
    category: Optional[str]
    brand: Optional[str]
    document_id_1c: Optional[str]
    store_id_1c: Optional[str]  # ID магазина из 1С
    store_name: Optional[str]  # Название магазина
    is_refund: bool = False

    class Config:
        from_attributes = True


class PurchaseHistoryResponse(BaseModel):
    items: List[PurchaseHistoryItem]
    total_count: int
    total_amount: float  # общая сумма в рублях


class StylistDialogMessageItem(BaseModel):
    id: str
    role: str
    sender_name: Optional[str] = None
    text: Optional[str] = None
    attachments: List[dict] = []
    created_at: Optional[str] = None


class StylistDialogItem(BaseModel):
    id: str
    topic: str
    source: Optional[str] = None
    scenario: Optional[str] = None
    status: str
    status_label: str
    assigned_stylist_name: Optional[str] = None
    created_at: Optional[str] = None
    last_message_at: Optional[str] = None
    messages: List[StylistDialogMessageItem]


class StylistDialogsResponse(BaseModel):
    items: List[StylistDialogItem]
    total: int


def _live_stylist_status_label(value: Optional[str]) -> str:
    return {
        "requested": "Запрос",
        "in_progress": "В обработке",
        "completed": "Завершено",
    }.get(str(value or "").strip().lower(), "Запрос")


def _stylist_dialog_topic(conversation: LiveStylistConversation, messages: List[StylistChatMessage]) -> str:
    meta = conversation.meta if isinstance(conversation.meta, dict) else {}
    latest_request = meta.get("latest_request") if isinstance(meta.get("latest_request"), dict) else {}
    request_text = str(latest_request.get("text") or "").strip()
    if request_text:
        return request_text[:160]
    for message in messages:
        if message.role == "user" and (message.text or "").strip():
            return message.text.strip()[:160]
    scenario = str(conversation.scenario or "").strip()
    source = str(conversation.source or "").strip()
    if scenario or source:
        return " / ".join([item for item in [scenario, source] if item])
    return "Диалог со стилистом"


def _product_image_url(product: Product) -> Optional[str]:
    images = product.images if isinstance(product.images, list) else []
    if images:
        first = images[0]
        return str(first) if first else None
    return None


def _look_image_urls(look: Look) -> List[str]:
    urls: List[str] = []
    if look.image_url:
        urls.append(str(look.image_url))
    raw_urls = look.image_urls if isinstance(look.image_urls, list) else []
    for raw in raw_urls:
        value = str(raw) if raw else ""
        if value and value not in urls:
            urls.append(value)
    media_items = look.media_items if isinstance(look.media_items, list) else []
    for item in media_items:
        if not isinstance(item, dict):
            continue
        value = str(item.get("url") or item.get("thumbnail_url") or "")
        if value and value not in urls:
            urls.append(value)
    return urls


def _normalize_uuid_list(raw_items: Any) -> List[UUID]:
    if not isinstance(raw_items, list):
        return []
    result: List[UUID] = []
    seen: set[UUID] = set()
    for raw in raw_items:
        try:
            parsed = UUID(str(raw))
        except Exception:
            continue
        if parsed in seen:
            continue
        seen.add(parsed)
        result.append(parsed)
    return result


async def _get_customer_or_404(db: AsyncSession, uid: UUID) -> User:
    result = await db.execute(select(User).where(User.id == uid, User.is_customer == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Покупатель не найден")
    return user


@router.get("/{user_id}/loyalty", response_model=AdminLoyaltyResponse)
async def get_customer_loyalty(
    user_id: str,
    limit: int = Query(100, ge=1, le=300),
    db: AsyncSession = Depends(get_db)
):
    """Программа лояльности покупателя для админского кабинета."""
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат user_id")

    user = await _get_customer_or_404(db, uid)
    loyalty_service = LoyaltyService(db)
    balance = await loyalty_service.get_loyalty_balance(uid)
    transactions = await loyalty_service.get_loyalty_transactions(uid, limit=limit)
    program_info = loyalty_service.get_loyalty_program_info()
    level_progress = loyalty_service.get_loyalty_level_progress(user.total_spent or 0)

    earned_total = sum(max(0, int(item.points or 0)) for item in transactions)
    spent_total = abs(sum(min(0, int(item.points or 0)) for item in transactions))
    expiring_transactions = [
        item
        for item in transactions
        if item.expires_at and item.points > 0 and item.expires_at > datetime.now(timezone.utc)
    ]

    return AdminLoyaltyResponse(
        balance=balance,
        transactions=[
            AdminLoyaltyTransactionItem(
                id=str(item.id),
                type=item.transaction_type,
                points=int(item.points or 0),
                balance_after=int(item.balance_after or 0),
                reason=item.reason,
                description=item.description,
                source=item.source,
                source_id=item.source_id,
                expires_at=item.expires_at.isoformat() if item.expires_at else None,
                created_at=item.created_at.isoformat() if item.created_at else "",
            )
            for item in transactions
        ],
        program_info=program_info,
        level_progress=level_progress,
        summary={
            "transactions_loaded": len(transactions),
            "earned_points_loaded": earned_total,
            "spent_points_loaded": spent_total,
            "expiring_points_loaded": sum(int(item.points or 0) for item in expiring_transactions),
            "total_spent": (user.total_spent or 0) / 100,
            "total_purchases": int(user.total_purchases or 0),
            "average_check": ((user.average_check or 0) / 100) if user.average_check else 0,
            "discount_card_number": user.discount_card_number,
        },
    )


@router.get("/{user_id}/saved-items", response_model=AdminSavedItemsResponse)
async def get_customer_saved_items(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Сохраненные образы и известные backend избранные товары покупателя."""
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат user_id")

    user = await _get_customer_or_404(db, uid)

    saved_rows = (
        await db.execute(
            select(SavedLook, Look)
            .join(Look, SavedLook.look_id == Look.id)
            .where(SavedLook.user_id == uid)
            .order_by(desc(SavedLook.created_at))
        )
    ).all()

    favorite_rows = (
        await db.execute(
            select(CustomerFavoriteProduct, Product)
            .join(Product, CustomerFavoriteProduct.product_id == Product.id)
            .where(CustomerFavoriteProduct.user_id == uid)
            .order_by(desc(CustomerFavoriteProduct.created_at))
        )
    ).all()

    favorite_products: List[AdminFavoriteProductItem] = [
        AdminFavoriteProductItem(
            id=str(product.id),
            name=product.name,
            brand=product.brand,
            category=product.category,
            article=product.article,
            external_code=product.external_code,
            price=((product.price or 0) / 100) if product.price is not None else None,
            image_url=_product_image_url(product),
            source=row.source or "app",
        )
        for row, product in favorite_rows
    ]

    favorite_product_ids = {UUID(item.id) for item in favorite_products}
    conversations = (
        await db.execute(
            select(LiveStylistConversation)
            .where(LiveStylistConversation.customer_user_id == uid)
            .order_by(desc(LiveStylistConversation.updated_at), desc(LiveStylistConversation.created_at))
        )
    ).scalars().all()
    for conversation in conversations:
        meta = conversation.meta if isinstance(conversation.meta, dict) else {}
        latest_request = meta.get("latest_request") if isinstance(meta.get("latest_request"), dict) else {}
        for product_id in _normalize_uuid_list(latest_request.get("favorite_product_ids") or []):
            if product_id in favorite_product_ids:
                continue
            product = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()
            if not product:
                continue
            favorite_product_ids.add(product_id)
            favorite_products.append(
                AdminFavoriteProductItem(
                    id=str(product.id),
                    name=product.name,
                    brand=product.brand,
                    category=product.category,
                    article=product.article,
                    external_code=product.external_code,
                    price=((product.price or 0) / 100) if product.price is not None else None,
                    image_url=_product_image_url(product),
                    source="live_stylist_request",
                )
            )

    saved_looks: List[AdminSavedLookItem] = []
    for saved_look, look in saved_rows:
        image_urls = _look_image_urls(look)
        product_ids = [str(item) for item in (look.product_ids or []) if item]
        saved_looks.append(
            AdminSavedLookItem(
                id=str(saved_look.id),
                look_id=str(saved_look.look_id),
                look_name=look.name,
                save_type=saved_look.save_type,
                notes=saved_look.notes,
                is_purchased=bool(saved_look.is_purchased),
                look_style=look.style,
                look_mood=look.mood,
                look_description=look.description or look.caption,
                look_image_url=image_urls[0] if image_urls else None,
                look_image_urls=image_urls,
                product_ids=product_ids,
                created_at=saved_look.created_at.isoformat() if saved_look.created_at else None,
            )
        )

    source_notes = []
    source_notes.append("Сохраненные образы загружаются из saved_looks.")
    source_notes.append("Избранные товары загружаются из серверного wishlist приложения.")
    source_notes.append("Товары из старых обращений к стилисту показаны дополнительно, если их нет в wishlist.")

    return AdminSavedItemsResponse(
        saved_looks=saved_looks,
        favorite_products=favorite_products,
        source_notes=source_notes,
    )


@router.get("/{user_id}/purchases", response_model=PurchaseHistoryResponse)
async def get_customer_purchases(
    user_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    exclude_packaging: bool = Query(True, description="Исключить упаковку (товары дешевле 5₽)"),
    db: AsyncSession = Depends(get_db)
):
    """История покупок покупателя"""
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат user_id")
    
    # Проверяем, что пользователь существует
    stmt = select(User).where(User.id == uid, User.is_customer == True)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Покупатель не найден")
    
    # Порог для упаковки: 5 рублей = 500 копеек
    # Возвраты (отрицательные суммы) всегда показываем, даже при активном exclude_packaging
    PACKAGING_THRESHOLD = 500
    base_filter = (PurchaseHistory.user_id == uid)

    # Берём достаточно большую выборку, дедуплицируем в Python, затем пагинируем
    stmt = (
        select(
            PurchaseHistory,
            Store.name.label("store_name"),
            Product.name.label("catalog_product_name"),
            Product.article.label("catalog_product_article"),
            Product.brand.label("product_brand"),
            Product.category.label("product_category"),
        )
        .outerjoin(Store, PurchaseHistory.store_id_1c == Store.external_id)
        .outerjoin(
            Product,
            or_(
                PurchaseHistory.product_id == Product.id,
                and_(PurchaseHistory.product_id.is_(None), PurchaseHistory.product_article == Product.article),
            ),
        )
        .where(base_filter)
        .order_by(desc(PurchaseHistory.purchase_date))
    )
    result = await db.execute(stmt)
    rows = result.all()

    def dedup_key(p):
        doc = p.document_id_1c or ""
        prod = p.product_id_1c or (p.product_article or "")
        ts = p.purchase_date.isoformat() if p.purchase_date else ""
        amt = p.total_amount or 0
        return (doc, prod, ts, amt)

    dedup_map = {}
    total_sum = 0
    for p, sname, pname, particle, pbrand, pcategory in rows:
        key = dedup_key(p)
        cur = dedup_map.get(key)
        prefer_new = False
        if cur is None:
            prefer_new = True
        else:
            cur_p, cur_sname, _, _, _, _ = cur
            if (not cur_p.store_id_1c) and p.store_id_1c:
                prefer_new = True
        if prefer_new:
            dedup_map[key] = (p, sname, pname, particle, pbrand, pcategory)
    deduped_all = sorted(dedup_map.values(), key=lambda x: x[0].purchase_date or "", reverse=True)

    # Сопутствующие товары не участвуют в аналитике покупателя и товарной аналитике.
    # Возвраты показываем, чтобы не терять корректировки, но упаковку/пакеты/сертификаты скрываем.
    deduped_with_accessories = deduped_all
    deduped = [
        (p, s, n, a, b, c)
        for (p, s, n, a, b, c) in deduped_with_accessories
        if not exclude_packaging or (p.total_amount or 0) < 0 or is_analytics_eligible_product(
            product_name=p.product_name or n,
            product_category=p.category or c,
            product_article=p.product_article or a,
            product_id=p.product_id_1c or p.product_id,
            total_amount_kopecks=p.total_amount or 0,
        )
    ]

    total_count = len(deduped)
    total_sum = sum((p.total_amount or 0) for p, _, _, _, _, _ in deduped)

    page = deduped[offset: offset + limit]
    items = []
    for p, store_name, prod_name, prod_article, prod_brand, prod_category in page:
        is_refund = (p.total_amount or 0) < 0
        display_name = p.product_name or prod_name
        items.append(PurchaseHistoryItem(
            id=str(p.id),
            purchase_date=p.purchase_date.isoformat() if p.purchase_date else "",
            product_name=display_name,
            product_article=p.product_article or prod_article,
            quantity=p.quantity or 1,
            price=(p.price or 0) / 100.0,
            total_amount=(p.total_amount or 0) / 100.0,
            category=derive_purchase_category(display_name, p.category or prod_category),
            brand=derive_purchase_brand(display_name, p.brand or prod_brand, prod_category or p.category),
            document_id_1c=p.document_id_1c,
            store_id_1c=p.store_id_1c,
            store_name=store_name,
            is_refund=is_refund
        ))

    return PurchaseHistoryResponse(
        items=items,
        total_count=total_count,
        total_amount=total_sum / 100.0
    )


@router.get("/{user_id}/stylist-dialogs", response_model=StylistDialogsResponse)
async def get_customer_stylist_dialogs(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """История диалогов покупателя со стилистом."""
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат user_id")

    stmt = select(User).where(User.id == uid, User.is_customer == True)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Покупатель не найден")

    conversations = (
        await db.execute(
            select(LiveStylistConversation)
            .where(LiveStylistConversation.customer_user_id == uid)
            .order_by(desc(LiveStylistConversation.last_message_at), desc(LiveStylistConversation.created_at))
        )
    ).scalars().all()
    if not conversations:
        return StylistDialogsResponse(items=[], total=0)

    conversation_ids = [item.id for item in conversations]
    message_rows = (
        await db.execute(
            select(StylistChatMessage)
            .where(StylistChatMessage.conversation_id.in_(conversation_ids))
            .order_by(StylistChatMessage.created_at.asc(), StylistChatMessage.id.asc())
        )
    ).scalars().all()

    messages_by_conversation: Dict[UUID, List[StylistChatMessage]] = {}
    sender_ids = set()
    assigned_ids = set()
    for row in message_rows:
        if row.conversation_id:
            messages_by_conversation.setdefault(row.conversation_id, []).append(row)
        if row.sender_user_id:
            sender_ids.add(row.sender_user_id)
    for conversation in conversations:
        if conversation.assigned_stylist_user_id:
            assigned_ids.add(conversation.assigned_stylist_user_id)

    users_map: Dict[UUID, User] = {}
    all_user_ids = list(sender_ids.union(assigned_ids))
    if all_user_ids:
        users = (await db.execute(select(User).where(User.id.in_(all_user_ids)))).scalars().all()
        users_map = {item.id: item for item in users}

    items: List[StylistDialogItem] = []
    for conversation in conversations:
        dialog_messages = messages_by_conversation.get(conversation.id, [])
        assigned_user = users_map.get(conversation.assigned_stylist_user_id) if conversation.assigned_stylist_user_id else None
        items.append(
            StylistDialogItem(
                id=str(conversation.id),
                topic=_stylist_dialog_topic(conversation, dialog_messages),
                source=conversation.source,
                scenario=conversation.scenario,
                status=conversation.status,
                status_label=_live_stylist_status_label(conversation.status),
                assigned_stylist_name=getattr(assigned_user, "full_name", None) or getattr(assigned_user, "email", None),
                created_at=conversation.created_at.isoformat() if conversation.created_at else None,
                last_message_at=conversation.last_message_at.isoformat() if conversation.last_message_at else None,
                messages=[
                    StylistDialogMessageItem(
                        id=str(message.id),
                        role=message.role,
                        sender_name=(
                            getattr(users_map.get(message.sender_user_id), "full_name", None)
                            or getattr(users_map.get(message.sender_user_id), "email", None)
                            or ("Покупатель" if message.role == "user" else "Стилист")
                        ),
                        text=message.text,
                        attachments=message.attachments or [],
                        created_at=message.created_at.isoformat() if message.created_at else None,
                    )
                    for message in dialog_messages
                ],
            )
        )

    return StylistDialogsResponse(items=items, total=len(items))


class UpdateCustomerRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None


@router.put("/{user_id}")
async def update_customer(
    user_id: str,
    request: UpdateCustomerRequest,
    db: AsyncSession = Depends(get_db)
):
    """Обновление данных покупателя"""
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат user_id")
    
    stmt = select(User).where(User.id == uid)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Покупатель не найден")
    
    if request.full_name is not None:
        user.full_name = request.full_name
        # Автоматически определяем пол, только если пол НЕ указан явно в запросе
        if request.gender is None and not user.gender:
            from app.agents.communication_agent import CommunicationAgent
            agent = CommunicationAgent(db)
            determined_gender = agent.determine_gender(request.full_name)
            if determined_gender:
                user.gender = determined_gender
                logger.info(f"Автоматически определен пол для {user_id}: {determined_gender}")
    
    if request.email is not None:
        user.email = request.email
    
    # Позволяем вручную установить пол (если указан явно, перезаписываем автоматическое определение)
    gender_updated = False
    if request.gender is not None:
        old_gender = getattr(user, 'gender', None)
        # Обрабатываем пустую строку как None
        if request.gender == "":
            new_gender_value = None
            logger.info(f"Пол сброшен для {user_id} (было: {old_gender})")
        elif request.gender in ["male", "female"]:
            new_gender_value = request.gender
            logger.info(f"Пол вручную установлен для {user_id}: {request.gender} (было: {old_gender})")
        else:
            raise HTTPException(status_code=400, detail="Неверное значение пола. Допустимые значения: 'male', 'female', null")
        
        # Используем прямое SQL-обновление для надежности (даже если поле не видно в модели)
        try:
            # Пробуем через ORM, если поле видно в модели
            if hasattr(User, 'gender'):
                user.gender = new_gender_value
                logger.info(f"Пол обновлен через ORM для {user_id}: {new_gender_value}")
            else:
                # Если поле не видно в модели, используем прямое SQL-обновление через text()
                sql_update = text("UPDATE users SET gender = :gender_value WHERE id = :user_id")
                await db.execute(sql_update, {"gender_value": new_gender_value, "user_id": str(uid)})
                gender_updated = True
                logger.info(f"Пол обновлен через SQL UPDATE для {user_id}: {new_gender_value}")
        except Exception as e:
            logger.warning(f"Ошибка при обновлении через ORM, используем SQL: {e}")
            # Fallback: прямое SQL-обновление через text()
            sql_update = text("UPDATE users SET gender = :gender_value WHERE id = :user_id")
            await db.execute(sql_update, {"gender_value": new_gender_value, "user_id": str(uid)})
            gender_updated = True
            logger.info(f"Пол обновлен через SQL (fallback) для {user_id}: {new_gender_value}")
    
    try:
        await db.commit()
        # Перезагружаем user из базы для получения актуальных данных
        if not gender_updated:
            await db.refresh(user)
        
        # Получаем gender через прямой SQL запрос для надежности
        saved_gender = None
        try:
            gender_query = text("SELECT gender FROM users WHERE id = :user_id")
            gender_result = await db.execute(gender_query, {"user_id": str(uid)})
            gender_row = gender_result.first()
            if gender_row:
                saved_gender = gender_row[0]
            logger.info(f"✅ Gender для {user_id} из БД (SQL): {saved_gender}")
        except Exception as e:
            logger.warning(f"Ошибка при получении gender через SQL: {e}, используем getattr")
            saved_gender = getattr(user, 'gender', None)
        
        logger.info(f"✅ Данные сохранены для {user_id}, пол в БД: {saved_gender}")
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении данных для {user_id}: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Ошибка при сохранении данных")
    
    return {"success": True, "message": "Данные покупателя обновлены", "gender": saved_gender}


@router.post("/{user_id}/loyalty/adjust")
async def adjust_loyalty_points(
    user_id: str,
    request: LoyaltyAdjustRequest,
    db: AsyncSession = Depends(get_db)
):
    """Ручная корректировка баллов"""
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат user_id")
    
    loyalty_service = LoyaltyService(db)
    
    if request.points > 0:
        await loyalty_service.earn_points(
            user_id=uid,
            points=request.points,
            reason=request.reason,
            metadata={"description": request.description},
            source="manual",
            source_id="system"
        )
    else:
        await loyalty_service.spend_points(
            user_id=uid,
            points=abs(request.points),
            reason=request.reason,
            description=request.description
        )
    
    return {"success": True, "message": "Баллы скорректированы"}


@router.get("/segments/list")
async def get_segments(
    db: AsyncSession = Depends(get_db)
):
    stmt = select(CustomerSegment).where(CustomerSegment.is_active == True)
    result = await db.execute(stmt)
    segments = result.scalars().all()
    items = []
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import cast, Integer
    for s in segments:
        count = int(s.customer_count or 0)
        normalized_dict = s.rules or {}
        # Единый способ расчёта через customer_segmentation
        try:
            rules = getattr(s, "rules", None) or {}
            is_auto = getattr(s, "is_auto_generated", False)
            
            from app.api.customer_segmentation import _normalize_to_segment_rules, _build_select_for_rules
            
            normalized_model = _normalize_to_segment_rules(rules, is_auto)
            normalized_dict = normalized_model.dict()
            
            # Если есть фильтры, считаем в реальном времени
            if normalized_dict.get("filters"):
                base, _ = _build_select_for_rules(normalized_dict)
                subq = base.subquery()
                total_result = await db.execute(select(func.count()).select_from(subq))
                count = int(total_result.scalar() or 0)
            else:
                # Если фильтров нет (или не смогли нормализовать), берем сохраненное значение
                # Для пустых ручных сегментов это может быть неточно, но безопасно
                count = int(s.customer_count or 0)
        except Exception:
            count = int(s.customer_count or 0)
        items.append({
            "id": str(s.id),
            "name": s.name,
            "description": s.description,
            "rules": normalized_dict,
            "customer_count": count,
            "color": s.color,
            "is_auto_generated": s.is_auto_generated
        })
    return items


@router.get("/segments/{segment_id}/users")
async def get_segment_users_admin(
    segment_id: str,
    limit: int = 200,
    db: AsyncSession = Depends(get_db)
):
    try:
        seg_uuid = UUID(segment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid segment ID format")

    res = await db.execute(select(CustomerSegment).where(CustomerSegment.id == seg_uuid))
    seg = res.scalar_one_or_none()
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found")

    lim = max(1, min(int(limit or 200), 1000))

    users_stmt = (
        select(User)
        .join(UserSegment, UserSegment.user_id == User.id, isouter=True)
        .where(UserSegment.segment_id == seg_uuid, User.is_customer == True)
        .order_by(User.last_purchase_date.desc().nullslast(), User.total_purchases.desc(), User.total_spent.desc())
        .limit(lim)
    )
    users = (await db.execute(users_stmt)).scalars().all()

    if not users:
        try:
            from app.api.customer_segmentation import _normalize_to_segment_rules, _build_select_for_rules
            
            rules = seg.rules if isinstance(seg.rules, dict) else {}
            is_auto = getattr(seg, "is_auto_generated", False)
            
            normalized_model = _normalize_to_segment_rules(rules, is_auto)
            normalized_dict = normalized_model.dict()
            
            # Only apply if filters exist, otherwise we might get all users which is risky for fallback
            if normalized_dict.get("filters"):
                base_stmt, _ = _build_select_for_rules(normalized_dict)
                subq = base_stmt.subquery()
                users_stmt = (
                    select(User)
                    .where(User.id.in_(select(subq.c.id)), User.is_customer == True)
                    .order_by(User.last_purchase_date.desc().nullslast(), User.total_purchases.desc(), User.total_spent.desc())
                    .limit(lim)
                )
                users = (await db.execute(users_stmt)).scalars().all()
        except Exception:
            users = []

    preferred_store_by_user: dict = {}
    if users:
        uids = [u.id for u in users]
        counts_stmt = (
            select(PurchaseHistory.user_id, PurchaseHistory.store_id_1c, func.count().label("cnt"))
            .where(PurchaseHistory.user_id.in_(uids))
            .group_by(PurchaseHistory.user_id, PurchaseHistory.store_id_1c)
        )
        rows = (await db.execute(counts_stmt)).all()
        for uid, store_id_1c, cnt in rows:
            if not store_id_1c:
                continue
            prev = preferred_store_by_user.get(uid)
            if not prev or cnt > prev[1]:
                preferred_store_by_user[uid] = (store_id_1c, cnt)
        store_ids = {sid for (sid, _cnt) in preferred_store_by_user.values()}
        name_by_ext = {}
        if store_ids:
            store_rows = await db.execute(select(Store.external_id, Store.name).where(Store.external_id.in_(store_ids)))
            name_by_ext = {row[0]: row[1] for row in store_rows.all()}
        for uid, (sid, _cnt) in list(preferred_store_by_user.items()):
            preferred_store_by_user[uid] = name_by_ext.get(sid) or sid or None

    payload = [
        {
            "id": str(u.id),
            "full_name": u.full_name,
            "phone": u.phone,
            "city": u.city,
            "preferred_store": u.preferred_store_name or preferred_store_by_user.get(u.id),
            "gender": u.gender,
            "total_purchases": u.total_purchases,
            "total_spent": u.total_spent,
            "last_purchase_date": u.last_purchase_date.isoformat() if u.last_purchase_date else None,
        }
        for u in users
    ]
    return {"users": payload, "count": len(payload)}

@router.get("/analytics/overview")
async def get_customers_analytics(
    db: AsyncSession = Depends(get_db)
):
    """Общая аналитика по покупателям"""
    try:
        analytics_service = CustomerAnalyticsService(db)
        
        # Статистика - используем безопасный доступ к колонкам
        total_customers = 0
        total_revenue = 0.0
        
        try:
            is_customer_col = User.__table__.columns.get("is_customer")
            if is_customer_col is None:
                is_customer_col = literal_column("is_customer")
            
            total_spent_col = User.__table__.columns.get("total_spent")
            if total_spent_col is None:
                total_spent_col = literal_column("total_spent")
            
            stmt = select(
                func.count(User.id).label("total_customers"),
                func.coalesce(func.sum(total_spent_col), 0).label("total_revenue")
            ).where(is_customer_col == True)
            result = await db.execute(stmt)
            row = result.first()
            
            if row:
                total_customers = row.total_customers or 0
                total_revenue = (row.total_revenue or 0) / 100  # Конвертируем из копеек в рубли
        except Exception as stats_error:
            logger.error(f"Ошибка получения базовой статистики: {stats_error}", exc_info=True)
            # Используем значения по умолчанию
            total_customers = 0
            total_revenue = 0.0
        
        # RFM анализ (с обработкой ошибок)
        rfm_analysis = {}
        try:
            rfm_analysis = await analytics_service.get_rfm_analysis()
        except Exception as e:
            logger.error(f"Ошибка RFM анализа: {e}", exc_info=True)
            rfm_analysis = {}
        
        # LTV (с обработкой ошибок)
        ltv_metrics = {}
        try:
            ltv_metrics = await analytics_service.get_ltv_metrics()
        except Exception as e:
            logger.error(f"Ошибка LTV метрик: {e}", exc_info=True)
            ltv_metrics = {}
        
        # Сегменты (с обработкой ошибок)
        segments_stats = {}
        try:
            segments_stats = await analytics_service.get_customer_segments_stats()
        except Exception as e:
            logger.error(f"Ошибка статистики сегментов: {e}", exc_info=True)
            segments_stats = {}
        
        return {
            "total_customers": total_customers,
            "total_revenue": total_revenue,
            "rfm_analysis": rfm_analysis or {},
            "ltv_metrics": ltv_metrics or {},
            "segments_stats": segments_stats or {}
        }
    except HTTPException:
        # Пробрасываем HTTP исключения (например, от require_admin)
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Ошибка при получении аналитики покупателей: {e}\n{error_trace}")
        # Возвращаем базовую статистику даже при ошибке
        return {
            "total_customers": 0,
            "total_revenue": 0,
            "rfm_analysis": {},
            "ltv_metrics": {},
            "segments_stats": {}
        }


@router.get("/export")
async def export_customers_xlsx(
    segment: Optional[str] = Query(None, description="Фильтр по сегменту (имя)"),
    segment_id: Optional[str] = Query(None, description="Фильтр по сегменту (ID)"),
    search: Optional[str] = Query(None, description="Поиск по имени/телефону/email/городу"),
    db: AsyncSession = Depends(get_db)
):
    try:
        try:
            stmt = select(User).where(User.is_customer == True)
        except Exception:
            is_customer_col = User.__table__.columns.get("is_customer") or literal_column("is_customer")
            stmt = select(User).where(is_customer_col == True)

        target_segment_obj = None
        if segment_id:
            try:
                sid = UUID(segment_id)
                res = await db.execute(select(CustomerSegment).where(CustomerSegment.id == sid))
                target_segment_obj = res.scalar_one_or_none()
            except Exception:
                pass
        
        if not target_segment_obj and segment:
            try:
                res = await db.execute(
                    select(CustomerSegment).where(CustomerSegment.name == segment, CustomerSegment.is_active == True)
                )
                target_segment_obj = res.scalar_one_or_none()
            except Exception:
                pass

        if target_segment_obj:
            rules = getattr(target_segment_obj, "rules", None) or {}
            is_auto = getattr(target_segment_obj, "is_auto_generated", False)
            try:
                def _seg_build_where_clause(rules_dict):
                    # Local helper only for fallback - DEPRECATED
                    # Prefer using app.api.customer_segmentation
                    pass

                from app.api.customer_segmentation import _normalize_to_segment_rules, _build_select_for_rules
                normalized_rules_model = _normalize_to_segment_rules(rules, is_auto)
                normalized_rules_dict = normalized_rules_model.dict()
                stmt_rules, _ = _build_select_for_rules(normalized_rules_dict)
                
                subq = stmt_rules.subquery()
                stmt = stmt.where(User.id.in_(select(subq.c.id)))
            except Exception:
                stmt = stmt.join(UserSegment, User.id == UserSegment.user_id).where(UserSegment.segment_id == target_segment_obj.id)
        elif segment:
            try:
                customer_segment_col = User.__table__.columns.get("customer_segment") or literal_column("customer_segment")
                stmt = stmt.where(customer_segment_col == segment)
            except Exception:
                customer_segment_col = User.__table__.columns.get("customer_segment") or literal_column("customer_segment")
                stmt = stmt.where(customer_segment_col == segment)

        if search and search.strip():
            term = f"%{search.strip()}%"
            conditions = []
            for col_name in ["phone", "email", "full_name", "city"]:
                col = User.__table__.columns.get(col_name)
                if col is not None:
                    conditions.append(col.ilike(term))
            if conditions:
                stmt = stmt.where(or_(*conditions))

        users = (await db.execute(stmt.order_by(desc(User.created_at)))).scalars().all()

        if not users:
            df_empty = pd.DataFrame(columns=[
                "id","phone","email","full_name","city","birth_date","gender","discount_card_number","customer_id_1c",
                "loyalty_points","total_purchases","total_spent_rub","average_check_rub","last_purchase_date",
                "customer_segment","rfm_r","rfm_f","rfm_m","rfm_score_sum","purchase_preferences","persona",
                "created_at","updated_at","synced_at","segments"
            ])
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df_empty.to_excel(writer, index=False, sheet_name="Покупатели")
            buf.seek(0)
            filename = f"customers_{datetime.now(timezone.utc).date().isoformat()}.xlsx"
            return StreamingResponse(
                buf,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )

        user_ids = [u.id for u in users]
        seg_rows = await db.execute(
            select(UserSegment.user_id, CustomerSegment.name)
            .join(CustomerSegment, UserSegment.segment_id == CustomerSegment.id)
            .where(UserSegment.user_id.in_(user_ids))
        )
        seg_map: dict = {}
        for uid, seg_name in seg_rows.all():
            seg_map.setdefault(uid, []).append(seg_name)

        rows = []
        for u in users:
            rfm = getattr(u, "rfm_score", None) or {}
            purchase_prefs = getattr(u, "purchase_preferences", None)
            rows.append({
                "id": str(u.id),
                "phone": getattr(u, "phone", None),
                "email": getattr(u, "email", None),
                "full_name": getattr(u, "full_name", None),
                "city": getattr(u, "city", None),
                "birth_date": getattr(u, "birth_date", None).isoformat() if getattr(u, "birth_date", None) else None,
                "gender": getattr(u, "gender", None),
                "discount_card_number": getattr(u, "discount_card_number", None),
                "customer_id_1c": getattr(u, "customer_id_1c", None),
                "loyalty_points": getattr(u, "loyalty_points", 0) or 0,
                "total_purchases": getattr(u, "total_purchases", 0) or 0,
                "total_spent_rub": (getattr(u, "total_spent", 0) or 0) / 100.0,
                "average_check_rub": (getattr(u, "average_check", None) or 0) / 100.0 if getattr(u, "average_check", None) else None,
                "last_purchase_date": getattr(u, "last_purchase_date", None).isoformat() if getattr(u, "last_purchase_date", None) else None,
                "customer_segment": getattr(u, "customer_segment", None),
                "rfm_r": rfm.get("r_score"),
                "rfm_f": rfm.get("f_score"),
                "rfm_m": rfm.get("m_score"),
                "rfm_score_sum": sum(v for v in [rfm.get("r_score"), rfm.get("f_score"), rfm.get("m_score")] if isinstance(v, (int, float))) if isinstance(rfm, dict) else None,
                "purchase_preferences": pd.NA if purchase_prefs is None else str(purchase_prefs),
                "persona": getattr(u, "persona", None),
                "created_at": getattr(u, "created_at", None).isoformat() if getattr(u, "created_at", None) else None,
                "updated_at": getattr(u, "updated_at", None).isoformat() if getattr(u, "updated_at", None) else None,
                "synced_at": getattr(u, "synced_at", None).isoformat() if getattr(u, "synced_at", None) else None,
                "segments": ", ".join(seg_map.get(u.id, []))
            })

        df = pd.DataFrame(rows)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Покупатели")
        buf.seek(0)
        filename = f"customers_{datetime.now(timezone.utc).date().isoformat()}.xlsx"
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        logger.error(f"Ошибка выгрузки покупателей в XLSX: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Не удалось сформировать выгрузку")
