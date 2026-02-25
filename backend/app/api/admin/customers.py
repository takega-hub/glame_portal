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
from app.models.loyalty_transaction import LoyaltyTransaction
from app.models.saved_look import SavedLook
from app.models.customer_segment import CustomerSegment
from app.models.user_segment import UserSegment
from app.models.store import Store
from app.api.dependencies import require_admin
from app.services.loyalty_service import LoyaltyService
from app.services.customer_analytics_service import CustomerAnalyticsService
from app.services.customer_sync_service import CustomerSyncService

router = APIRouter()


class CustomerListItem(BaseModel):
    id: str
    phone: Optional[str]
    email: Optional[str]
    full_name: Optional[str]
    city: Optional[str]
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

    class Config:
        from_attributes = True


class LoyaltyAdjustRequest(BaseModel):
    points: int
    reason: str
    description: Optional[str] = None


@router.get("", response_model=CustomersListResponse)
async def get_customers(
    segment: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort: Optional[str] = Query("total_spent"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db)
):
    """Список всех покупателей"""
    try:
        logger.info(f"Получение списка покупателей: segment={segment}, search={search}, sort={sort}, limit={limit}, offset={offset}")
        
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
        
        # Фильтр по сегменту
        # Сначала пробуем найти сегмент в CustomerSegment (для AI-сегментации)
        # Если не найден - фильтруем по полю customer_segment (для простой сегментации)
        if segment:
            try:
                # Ищем сегмент в CustomerSegment по названию
                segment_stmt = select(CustomerSegment).where(CustomerSegment.name == segment, CustomerSegment.is_active == True)
                segment_result = await db.execute(segment_stmt)
                found_segment = segment_result.scalar_one_or_none()
                
                if found_segment:
                    # Если сегмент найден в CustomerSegment - фильтруем через UserSegment
                    # Используем left join, чтобы не исключать пользователей без записей в UserSegment
                    logger.info(f"Найден сегмент в CustomerSegment: {segment}, фильтруем через UserSegment")
                    stmt = stmt.join(UserSegment, User.id == UserSegment.user_id, isouter=False).where(UserSegment.segment_id == found_segment.id)
                else:
                    # Если не найден - фильтруем по полю customer_segment (обратная совместимость)
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
            except Exception as e:
                logger.error(f"Ошибка при фильтрации по сегменту '{segment}': {e}")
                # Fallback на прямое сравнение с customer_segment
                try:
                    customer_segment_col = User.__table__.columns.get("customer_segment")
                    if customer_segment_col is not None:
                        stmt = stmt.where(customer_segment_col == segment)
                    else:
                        return []
                except Exception as fallback_error:
                    logger.error(f"Ошибка при fallback фильтрации: {fallback_error}")
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
            # Применяем те же условия, что и в основном запросе
            # Базовое условие is_customer
            try:
                count_stmt = count_stmt.where(User.is_customer == True)
            except:
                is_customer_col = User.__table__.columns.get("is_customer")
                if is_customer_col:
                    count_stmt = count_stmt.where(is_customer_col == True)
            
            # Фильтр по сегменту (если был применен join, используем его)
            if segment:
                try:
                    segment_stmt = select(CustomerSegment).where(CustomerSegment.name == segment, CustomerSegment.is_active == True)
                    segment_result = await db.execute(segment_stmt)
                    found_segment = segment_result.scalar_one_or_none()
                    if found_segment:
                        count_stmt = count_stmt.join(UserSegment, User.id == UserSegment.user_id, isouter=False).where(UserSegment.segment_id == found_segment.id)
                    else:
                        customer_segment_col = User.__table__.columns.get("customer_segment")
                        if customer_segment_col:
                            count_stmt = count_stmt.where(customer_segment_col == segment)
                except Exception:
                    pass
            
            # Поиск
            if search and search.strip():
                search_term = f"%{search.strip()}%"
                search_conditions = []
                for col_name in ['phone', 'email', 'full_name', 'city']:
                    col = User.__table__.columns.get(col_name)
                    if col:
                        search_conditions.append(col.ilike(search_term))
                if search_conditions:
                    count_stmt = count_stmt.where(or_(*search_conditions))
            
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


@router.get("/{user_id}", response_model=CustomerDetailResponse)
async def get_customer_detail(
    user_id: str,
    sync: bool = Query(True, description="Синхронизировать данные из 1С при загрузке страницы"),
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db)
):
    """Детали покупателя. При загрузке страницы автоматически синхронизирует данные из 1С."""
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
    
    # Синхронизация данных из 1С при загрузке страницы
    if sync:
        try:
            logger.info(f"Синхронизация покупателя {uid} из 1С при загрузке страницы")
            sync_service = CustomerSyncService(db)
            
            # Синхронизируем начальный ввод (миграция)
            await sync_service.sync_initial_balances(user_id=uid)
            
            # Синхронизируем историю покупок за последние 2 года
            await sync_service.sync_purchase_history(user_id=uid, days=730)
            
            # Синхронизируем бонусные баллы
            await sync_service.sync_loyalty_points(user_id=uid)
            
            # Пересчитываем метрики
            await sync_service.calculate_customer_metrics(uid)
            
            # Обновляем сегмент
            await sync_service.update_customer_segment(uid)
            
            # Коммитим изменения
            await db.commit()
            
            logger.info(f"Синхронизация покупателя {uid} завершена")
        except Exception as e:
            logger.error(f"Ошибка синхронизации покупателя {uid}: {e}", exc_info=True)
            # Не прерываем запрос, просто логируем ошибку
            await db.rollback()
    
    # ВАЖНО: Перезагружаем user из базы после синхронизации (или rollback)
    # чтобы получить актуальные данные, включая gender
    stmt = select(User).where(User.id == uid)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Покупатель не найден")
    
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
        created_at=getattr(user, "created_at", None).isoformat() if getattr(user, "created_at", None) else None
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

    class Config:
        from_attributes = True


class PurchaseHistoryResponse(BaseModel):
    items: List[PurchaseHistoryItem]
    total_count: int
    total_amount: float  # общая сумма в рублях


@router.get("/{user_id}/purchases", response_model=PurchaseHistoryResponse)
async def get_customer_purchases(
    user_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    exclude_packaging: bool = Query(True, description="Исключить упаковку (товары дешевле 5₽)"),
    current_user: User = Depends(require_admin()),
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
    PACKAGING_THRESHOLD = 500
    
    # Базовое условие фильтрации
    base_filter = PurchaseHistory.user_id == uid
    if exclude_packaging:
        # Исключаем товары дешевле 5 рублей (упаковка)
        base_filter = and_(base_filter, PurchaseHistory.total_amount >= PACKAGING_THRESHOLD)
    
    # Получаем общее количество и сумму (с учётом фильтра)
    count_stmt = select(func.count(PurchaseHistory.id), func.sum(PurchaseHistory.total_amount)).where(base_filter)
    count_result = await db.execute(count_stmt)
    total_count, total_sum = count_result.one()
    total_count = total_count or 0
    total_sum = total_sum or 0
    
    # Получаем историю покупок с сортировкой по дате
    # Делаем LEFT JOIN с Store для получения названия магазина
    stmt = (
        select(
            PurchaseHistory,
            Store.name.label('store_name')
        )
        .outerjoin(
            Store,
            PurchaseHistory.store_id_1c == Store.external_id
        )
        .where(base_filter)
        .order_by(desc(PurchaseHistory.purchase_date))
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    rows = result.all()
    
    items = []
    for p, store_name in rows:
        items.append(PurchaseHistoryItem(
            id=str(p.id),
            purchase_date=p.purchase_date.isoformat() if p.purchase_date else "",
            product_name=p.product_name,
            product_article=p.product_article,
            quantity=p.quantity or 1,
            price=(p.price or 0) / 100.0,
            total_amount=(p.total_amount or 0) / 100.0,
            category=p.category,
            brand=p.brand,
            document_id_1c=p.document_id_1c,
            store_id_1c=p.store_id_1c,
            store_name=store_name
        ))
    
    return PurchaseHistoryResponse(
        items=items,
        total_count=total_count,
        total_amount=total_sum / 100.0  # конвертируем в рубли
    )


class UpdateCustomerRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None


@router.put("/{user_id}")
async def update_customer(
    user_id: str,
    request: UpdateCustomerRequest,
    current_user: User = Depends(require_admin()),
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
    current_user: User = Depends(require_admin()),
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
            source_id=str(current_user.id)
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
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db)
):
    """Список сегментов"""
    stmt = select(CustomerSegment).where(CustomerSegment.is_active == True)
    result = await db.execute(stmt)
    segments = result.scalars().all()
    
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "description": s.description,
            "customer_count": s.customer_count,
            "color": s.color,
            "is_auto_generated": s.is_auto_generated
        }
        for s in segments
    ]


@router.get("/analytics/overview")
async def get_customers_analytics(
    current_user: User = Depends(require_admin()),
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
