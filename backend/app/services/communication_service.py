"""
Сервис для работы с данными клиентов для генерации сообщений
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, distinct, or_, case, text, literal_column
from datetime import datetime, timedelta, timezone
from uuid import UUID
import logging

from app.models.user import User
from app.models.purchase_history import PurchaseHistory

logger = logging.getLogger(__name__)


class CommunicationService:
    """Сервис для получения данных клиентов и расчета метрик"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_client_data(self, client_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Получение полных данных клиента для генерации сообщения
        
        Args:
            client_id: ID клиента
        
        Returns:
            Словарь с данными клиента или None если не найден
        """
        try:
            # Получаем пользователя
            result = await self.db.execute(
                select(User).where(User.id == client_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                return None
            
            # Рассчитываем метрики за 365 дней
            metrics = await self.calculate_client_metrics(client_id)
            
            # Получаем историю покупок за 365 дней
            purchase_history = await self.get_purchase_history_365(client_id)
            
            # Определяем дни с последней покупки
            days_since_last = None
            if user.last_purchase_date:
                now = datetime.now(user.last_purchase_date.tzinfo) if user.last_purchase_date.tzinfo else datetime.now()
                days_since_last = (now - user.last_purchase_date).days
            
            # Определяем пол: сначала из БД, если нет - по имени
            gender = getattr(user, 'gender', None)
            if not gender and user.full_name:
                # Если пол не указан в БД, определяем по имени
                gender = self._determine_gender_from_name(user.full_name)
            
            # Формируем данные клиента
            client_data = {
                "id": str(user.id),
                "name": user.full_name or "Клиент",
                "phone": user.phone,
                "city": getattr(user, 'city', None),
                "gender": gender,  # Пол из БД или определенный по имени
                "loyalty_points": user.loyalty_points or 0,
                "bonus_balance": user.loyalty_points or 0,  # Бонусы = баллы лояльности
                "total_spend_365": metrics.get("total_spend_365", 0),
                "purchases_365": metrics.get("purchases_365", 0),
                "days_since_last": days_since_last,
                "last_purchase_date": user.last_purchase_date.isoformat() if user.last_purchase_date else None,
                "purchase_history": purchase_history
            }
            
            return client_data
        
        except Exception as e:
            logger.exception(f"Error getting client data for {client_id}: {e}")
            return None
    
    async def calculate_client_metrics(self, client_id: UUID) -> Dict[str, Any]:
        """
        Расчет метрик клиента за последние 365 дней
        
        Args:
            client_id: ID клиента
        
        Returns:
            Словарь с метриками
        """
        try:
            # Дата 365 дней назад
            date_365_days_ago = datetime.now() - timedelta(days=365)
            
            # Получаем покупки за 365 дней
            result = await self.db.execute(
                select(
                    func.sum(PurchaseHistory.total_amount).label("total_spend"),
                    func.count(PurchaseHistory.id).label("purchases_count")
                )
                .where(
                    and_(
                        PurchaseHistory.user_id == client_id,
                        PurchaseHistory.purchase_date >= date_365_days_ago
                    )
                )
            )
            
            row = result.first()
            
            total_spend_365 = int(row.total_spend or 0)  # В копейках
            purchases_365 = int(row.purchases_count or 0)
            
            return {
                "total_spend_365": total_spend_365,
                "purchases_365": purchases_365
            }
        
        except Exception as e:
            logger.exception(f"Error calculating metrics for client {client_id}: {e}")
            return {
                "total_spend_365": 0,
                "purchases_365": 0
            }
    
    async def get_purchase_history_365(self, client_id: UUID) -> List[Dict[str, Any]]:
        """
        Получение истории покупок за последние 365 дней
        
        Args:
            client_id: ID клиента
        
        Returns:
            Список покупок с брендами и датами
        """
        try:
            date_365_days_ago = datetime.now() - timedelta(days=365)
            
            result = await self.db.execute(
                select(PurchaseHistory)
                .where(
                    and_(
                        PurchaseHistory.user_id == client_id,
                        PurchaseHistory.purchase_date >= date_365_days_ago
                    )
                )
                .order_by(PurchaseHistory.purchase_date.desc())
            )
            
            purchases = result.scalars().all()
            
            # Формируем список уникальных покупок по брендам и датам
            purchase_history = []
            seen_brands = set()
            
            for purchase in purchases:
                brand = purchase.brand
                if brand and brand not in seen_brands:
                    seen_brands.add(brand)
                    purchase_history.append({
                        "brand": brand,
                        "date": purchase.purchase_date.isoformat() if purchase.purchase_date else None,
                        "store": purchase.store_id_1c  # Можно будет заменить на название
                    })
            
            return purchase_history
        
        except Exception as e:
            logger.exception(f"Error getting purchase history for client {client_id}: {e}")
            return []
    
    async def find_clients_by_brand(
        self,
        brand: str,
        limit: int = 1000,
        search_criteria: Optional[Dict[str, Any]] = None
    ) -> List[UUID]:
        """
        Поиск клиентов, у которых в истории покупок есть указанный бренд
        
        Args:
            brand: Название бренда
            limit: Максимальное количество клиентов
        
        Returns:
            Список ID клиентов
        """
        try:
            # Поиск нечувствителен к регистру и пробелам
            from sqlalchemy import func
            brand_normalized = brand.strip()
            
            # Сначала пробуем точное совпадение (нормализованное)
            result = await self.db.execute(
                select(distinct(PurchaseHistory.user_id))
                .where(
                    func.lower(func.trim(PurchaseHistory.brand)) == func.lower(brand_normalized)
                )
                .limit(limit)
            )
            
            client_ids = [row[0] for row in result.all()]
            
            # Если не нашли, пробуем поиск по частичному совпадению
            if not client_ids:
                result = await self.db.execute(
                    select(distinct(PurchaseHistory.user_id))
                    .where(
                        func.lower(func.trim(PurchaseHistory.brand)).contains(func.lower(brand_normalized))
                    )
                    .limit(limit)
                )
                client_ids = [row[0] for row in result.all()]
                logger.info(f"Found {len(client_ids)} clients with brand containing '{brand}' (partial match)")
            else:
                logger.info(f"Found {len(client_ids)} clients with brand '{brand}' (exact match)")
            
            # Применяем дополнительные критерии поиска, если они указаны
            if search_criteria and client_ids:
                # Фильтруем найденных клиентов по дополнительным критериям
                filtered_ids = []
                for client_id in client_ids:
                    client_data = await self.get_client_data(client_id)
                    if not client_data:
                        continue
                    
                    # Проверяем критерии
                    if search_criteria.get("min_total_spend_365") is not None:
                        if client_data.get("total_spend_365", 0) < search_criteria["min_total_spend_365"]:
                            continue
                    
                    if search_criteria.get("max_total_spend_365") is not None:
                        if client_data.get("total_spend_365", 0) > search_criteria["max_total_spend_365"]:
                            continue
                    
                    if search_criteria.get("min_purchases_365") is not None:
                        if client_data.get("purchases_365", 0) < search_criteria["min_purchases_365"]:
                            continue
                    
                    if search_criteria.get("max_purchases_365") is not None:
                        if client_data.get("purchases_365", 0) > search_criteria["max_purchases_365"]:
                            continue
                    
                    if search_criteria.get("min_bonus_balance") is not None:
                        if client_data.get("bonus_balance", 0) < search_criteria["min_bonus_balance"]:
                            continue
                    
                    if search_criteria.get("max_bonus_balance") is not None:
                        if client_data.get("bonus_balance", 0) > search_criteria["max_bonus_balance"]:
                            continue
                    
                    if search_criteria.get("cities"):
                        client_city = client_data.get("city", "")
                        if not client_city or client_city not in search_criteria["cities"]:
                            continue
                    
                    filtered_ids.append(client_id)
                
                client_ids = filtered_ids[:limit]
                logger.info(f"After applying search criteria: {len(client_ids)} clients")
            
            return client_ids
        
        except Exception as e:
            logger.exception(f"Error finding clients by brand {brand}: {e}")
            return []
    
    def apply_search_criteria(
        self,
        base_query,
        criteria: Optional[Dict[str, Any]] = None
    ):
        """
        Применение критериев поиска к базовому запросу
        
        Args:
            base_query: Базовый SQLAlchemy запрос
            criteria: Словарь с критериями поиска
        
        Returns:
            Модифицированный запрос
        """
        if not criteria:
            return base_query
        
        conditions = []
        
        # Фильтр по сегментам (A, B, C, D, E)
        if criteria.get("segments"):
            segments = criteria["segments"]
            # Сегменты определяются динамически, нужно вычислять их
            # Для упрощения используем поле customer_segment если оно есть
            if hasattr(User, 'customer_segment'):
                segment_conditions = []
                for segment in segments:
                    # Маппинг наших сегментов на сегменты в БД
                    segment_mapping = {
                        "A": ["VIP", "A"],
                        "B": ["Active", "B"],
                        "C": ["Regular", "C"],
                        "D": ["Sleeping", "D"],
                        "E": ["New", "E"]
                    }
                    db_segments = segment_mapping.get(segment, [segment])
                    segment_conditions.append(User.customer_segment.in_(db_segments))
                
                if segment_conditions:
                    conditions.append(or_(*segment_conditions))
        
        # Фильтр по полу
        if criteria.get("gender"):
            gender = criteria["gender"]
            # Используем literal_column, так как поле gender может быть не видно в ORM модели
            conditions.append(literal_column("gender") == gender)
        
        # Фильтр по минимальной сумме покупок за 365 дней
        if criteria.get("min_total_spend_365") is not None:
            conditions.append(User.total_spent >= criteria["min_total_spend_365"])
        
        # Фильтр по максимальной сумме покупок за 365 дней
        if criteria.get("max_total_spend_365") is not None:
            conditions.append(User.total_spent <= criteria["max_total_spend_365"])
        
        # Фильтр по минимальному количеству покупок
        if criteria.get("min_purchases_365") is not None:
            conditions.append(User.total_purchases >= criteria["min_purchases_365"])
        
        # Фильтр по максимальному количеству покупок
        if criteria.get("max_purchases_365") is not None:
            conditions.append(User.total_purchases <= criteria["max_purchases_365"])
        
        # Фильтр по минимальному балансу бонусов
        if criteria.get("min_bonus_balance") is not None:
            conditions.append(User.loyalty_points >= criteria["min_bonus_balance"])
        
        # Фильтр по максимальному балансу бонусов
        if criteria.get("max_bonus_balance") is not None:
            conditions.append(User.loyalty_points <= criteria["max_bonus_balance"])
        
        # Фильтр по городам
        if criteria.get("cities"):
            cities = [city.strip() for city in criteria["cities"] if city.strip()]
            if cities and hasattr(User, 'city'):
                conditions.append(User.city.in_(cities))
        
        # Фильтр по местным клиентам (крымские города)
        if criteria.get("is_local_only") is True:
            crimean_cities = [
                "Симферополь", "Ялта", "Севастополь", "Керчь", "Феодосия",
                "Евпатория", "Алушта", "Бахчисарай", "Судак", "Алупка"
            ]
            if hasattr(User, 'city'):
                conditions.append(User.city.in_(crimean_cities))
        
        # Фильтр по датам (дни с последней покупки)
        if criteria.get("min_days_since_last") is not None or criteria.get("max_days_since_last") is not None:
            if hasattr(User, 'last_purchase_date'):
                min_days = criteria.get("min_days_since_last")
                max_days = criteria.get("max_days_since_last")
                
                date_conditions = []
                
                if min_days is not None:
                    min_date = datetime.now() - timedelta(days=min_days)
                    date_conditions.append(
                        or_(
                            User.last_purchase_date <= min_date,
                            User.last_purchase_date.is_(None)
                        )
                    )
                
                if max_days is not None:
                    max_date = datetime.now() - timedelta(days=max_days)
                    date_conditions.append(
                        User.last_purchase_date >= max_date
                    )
                
                if date_conditions:
                    conditions.append(and_(*date_conditions))
        
        # Применяем условия к запросу
        if conditions:
            # Если в запросе уже есть where, объединяем условия
            if hasattr(base_query, 'whereclause') and base_query.whereclause is not None:
                base_query = base_query.where(and_(base_query.whereclause, *conditions))
            else:
                base_query = base_query.where(and_(*conditions))
        
        return base_query
    
    async def find_clients_for_event(
        self,
        event_type: str,
        event_data: Optional[Dict[str, Any]] = None,
        limit: int = 1000,
        search_criteria: Optional[Dict[str, Any]] = None
    ) -> List[UUID]:
        """
        Поиск клиентов для конкретного события
        
        Args:
            event_type: Тип события (brand_arrival, no_purchase_180, etc.)
            event_data: Дополнительные данные события
            limit: Максимальное количество клиентов
        
        Returns:
            Список ID клиентов
        """
        if event_type == "brand_arrival":
            brand = event_data.get("brand") if event_data else None
            if brand:
                return await self.find_clients_by_brand(brand, limit)
            else:
                logger.warning("brand_arrival event without brand specified")
                return []
        
        elif event_type == "no_purchase_180":
            # Клиенты без покупок более 180 дней
            date_180_days_ago = datetime.now() - timedelta(days=180)
            
            # Находим клиентов с последней покупкой > 180 дней назад или без покупок
            query = select(User.id).where(
                and_(
                    User.is_customer == True,
                    or_(
                        User.last_purchase_date < date_180_days_ago,
                        User.last_purchase_date.is_(None)
                    )
                )
            )
            
            # Применяем дополнительные критерии поиска
            if search_criteria:
                query = self.apply_search_criteria(query, search_criteria)
            
            query = query.limit(limit)
            result = await self.db.execute(query)
            
            client_ids = [row[0] for row in result.all()]
            logger.info(f"Found {len(client_ids)} clients with no purchase > 180 days")
            return client_ids
        
        elif event_type == "bonus_balance":
            # Клиенты с балансом бонусов > 0
            query = select(User.id).where(
                and_(
                    User.is_customer == True,
                    User.loyalty_points > 0
                )
            )
            
            # Применяем дополнительные критерии поиска
            if search_criteria:
                query = self.apply_search_criteria(query, search_criteria)
            
            query = query.limit(limit)
            result = await self.db.execute(query)
            
            client_ids = [row[0] for row in result.all()]
            logger.info(f"Found {len(client_ids)} clients with bonus balance > 0")
            return client_ids
        
        elif event_type == "loyalty_level_up":
            # Для нового уровня лояльности - все активные клиенты
            query = select(User.id).where(
                and_(
                    User.is_customer == True,
                    User.last_purchase_date.isnot(None)
                )
            )
            
            # Применяем дополнительные критерии поиска
            if search_criteria:
                query = self.apply_search_criteria(query, search_criteria)
            
            query = query.order_by(User.last_purchase_date.desc()).limit(limit)
            result = await self.db.execute(query)
            
            client_ids = [row[0] for row in result.all()]
            logger.info(f"Found {len(client_ids)} clients for loyalty_level_up")
            return client_ids
        
        elif event_type == "holiday_male":
            # Для праздничных сообщений мужчинам - фильтруем по полу
            # Определяем целевой пол: сначала из search_criteria (приоритет), потом "male" по умолчанию
            target_gender = "male"  # По умолчанию для holiday_male
            if search_criteria and search_criteria.get("gender"):
                # Критерий gender из search_criteria имеет приоритет
                target_gender = search_criteria["gender"]
                logger.info(f"Using gender from search_criteria for holiday_male: {target_gender}")
            
            # Проверяем, есть ли поле gender в модели
            has_gender_field = hasattr(User, 'gender')
            logger.info(f"User model has gender field: {has_gender_field}")
            
            if has_gender_field:
                # Используем поле gender из БД для прямой фильтрации в SQL
                # Сначала берем всех клиентов с нужным полом из БД
                # Используем literal_column, так как поле gender может быть не видно в ORM модели
                query = select(User.id).where(
                    and_(
                        User.is_customer == True,
                        literal_column("gender") == target_gender  # Прямая фильтрация по БД
                    )
                )
                
                # Применяем дополнительные критерии поиска (но исключаем gender, так как уже применили выше)
                if search_criteria:
                    criteria_without_gender = {k: v for k, v in search_criteria.items() if k != "gender"}
                    if criteria_without_gender:
                        query = self.apply_search_criteria(query, criteria_without_gender)
                
                query = query.limit(limit)
                result = await self.db.execute(query)
                
                client_ids = [row[0] for row in result.all()]
                logger.info(f"Found {len(client_ids)} {target_gender} clients from DB (gender field) for holiday_male")
                
                # Если нашли достаточно клиентов, возвращаем их
                if len(client_ids) >= limit:
                    return client_ids[:limit]
                
                # Если не хватает, добавляем клиентов с gender = NULL и определяем пол по имени
                if len(client_ids) < limit:
                    remaining_needed = limit - len(client_ids)
                    logger.info(f"Need {remaining_needed} more clients, checking clients with gender=NULL")
                    
                    # Берем клиентов с gender = NULL
                    query_null = select(User.id, User.full_name).where(
                        and_(
                            User.is_customer == True,
                            literal_column("gender").is_(None)
                        )
                    )
                    
                    # Применяем дополнительные критерии поиска
                    if search_criteria:
                        criteria_without_gender = {k: v for k, v in search_criteria.items() if k != "gender"}
                        if criteria_without_gender:
                            query_null = self.apply_search_criteria(query_null, criteria_without_gender)
                    
                    query_null = query_null.limit(remaining_needed * 3)  # Берем больше для фильтрации по имени
                    result_null = await self.db.execute(query_null)
                    null_gender_clients = result_null.all()
                    
                    # Определяем пол по имени для клиентов с gender = NULL
                    for row in null_gender_clients:
                        if len(client_ids) >= limit:
                            break
                        client_id = row[0]
                        full_name = row[1] if len(row) > 1 else None
                        
                        if full_name:
                            determined_gender = self._determine_gender_from_name(full_name)
                            if determined_gender == target_gender:
                                client_ids.append(client_id)
                    
                    logger.info(f"Added {len(client_ids) - (limit - remaining_needed)} clients from name-based filtering")
                
                return client_ids[:limit]
            else:
                # Если поле gender отсутствует в модели, используем старую логику (определение по имени)
                logger.warning("User.gender field not found in model, using name-based filtering only")
                query = select(User.id, User.full_name).where(User.is_customer == True)
                
                # Применяем дополнительные критерии поиска
                if search_criteria:
                    criteria_without_gender = {k: v for k, v in search_criteria.items() if k != "gender"}
                    if criteria_without_gender:
                        query = self.apply_search_criteria(query, criteria_without_gender)
                
                query = query.limit(limit * 3)  # Берем больше для фильтрации по имени
                result = await self.db.execute(query)
                
                all_clients = result.all()
                logger.info(f"Found {len(all_clients)} total clients before gender filtering for holiday_male")
                
                # Фильтруем по целевому полу (определяем по имени)
                filtered_clients = []
                for row in all_clients:
                    client_id = row[0]
                    full_name = row[1] if len(row) > 1 else None
                    
                    if full_name:
                        client_gender = self._determine_gender_from_name(full_name)
                        if client_gender == target_gender:
                            filtered_clients.append(client_id)
                
                client_ids = filtered_clients[:limit]
                logger.info(f"Found {len(client_ids)} {target_gender} clients for holiday_male (name-based)")
                return client_ids
        
        # Для других типов событий (включая кастомные) - все клиенты
        logger.info(f"Event type '{event_type}', analyzing for gender filter")
        
        # Определяем целевой пол: сначала из search_criteria (приоритет), потом из названия события
        target_gender = None
        if search_criteria and search_criteria.get("gender"):
            # Критерий gender из search_criteria имеет приоритет
            target_gender = search_criteria["gender"]
            logger.info(f"Using gender from search_criteria: {target_gender}")
        else:
            # Если не указан в search_criteria, определяем из названия события
            target_gender = self._extract_gender_from_event_name(event_type)
            logger.info(f"Event '{event_type}' - extracted target gender: {target_gender}")
        
        # Если нужно фильтровать по полу, используем поле gender из БД
        if target_gender:
            # Проверяем, есть ли поле gender в модели
            has_gender_field = hasattr(User, 'gender')
            
            # ВАЖНО: Даже если поле не видно в модели, оно может быть в БД
            # Используем прямое SQL-обращение к БД для максимальной надежности
            
            # Инициализируем client_ids
            client_ids = []
            
            # Сначала пытаемся использовать поле gender из БД через SQLAlchemy (если видно в модели)
            if has_gender_field:
                # Сначала берем всех клиентов с нужным полом из БД (прямая SQL-фильтрация)
                # Используем literal_column, так как поле gender может быть не видно в ORM модели
                query = select(User.id).where(
                    and_(
                        User.is_customer == True,
                        literal_column("gender") == target_gender  # Прямая фильтрация по БД
                    )
                )
                
                # Применяем дополнительные критерии поиска
                if search_criteria:
                    criteria_without_gender = {k: v for k, v in search_criteria.items() if k != "gender"}
                    if criteria_without_gender:
                        query = self.apply_search_criteria(query, criteria_without_gender)
                
                query = query.limit(limit)
                result = await self.db.execute(query)
                
                client_ids = [row[0] for row in result.all()]
                logger.info(f"Found {len(client_ids)} {target_gender} clients from DB (gender field) for event '{event_type}'")
            else:
                # Поле не видно в модели, но может быть в БД - используем прямой SQL
                logger.info(f"Gender field not visible in model, using direct SQL query to DB")
                
                # Формируем базовый SQL-запрос
                sql_query = f"""
                    SELECT id 
                    FROM users 
                    WHERE is_customer = TRUE AND gender = :target_gender
                """
                
                # Применяем дополнительные критерии через WHERE условия
                # (упрощенная версия для SQL, основные критерии)
                params = {"target_gender": target_gender}
                
                # Добавляем условия из search_criteria (упрощенно)
                if search_criteria:
                    if search_criteria.get("min_total_spend_365") is not None:
                        sql_query += " AND total_spent >= :min_spend"
                        params["min_spend"] = search_criteria["min_total_spend_365"]
                    if search_criteria.get("max_total_spend_365") is not None:
                        sql_query += " AND total_spent <= :max_spend"
                        params["max_spend"] = search_criteria["max_total_spend_365"]
                    if search_criteria.get("min_purchases_365") is not None:
                        sql_query += " AND total_purchases >= :min_purchases"
                        params["min_purchases"] = search_criteria["min_purchases_365"]
                    if search_criteria.get("max_purchases_365") is not None:
                        sql_query += " AND total_purchases <= :max_purchases"
                        params["max_purchases"] = search_criteria["max_purchases_365"]
                    if search_criteria.get("cities"):
                        cities = [c.strip() for c in search_criteria["cities"] if c.strip()]
                        if cities:
                            sql_query += " AND city = ANY(:cities)"
                            params["cities"] = cities
                
                sql_query += f" LIMIT {limit}"
                
                try:
                    result = await self.db.execute(text(sql_query), params)
                    client_ids = [row[0] for row in result.all()]
                    logger.info(f"Found {len(client_ids)} {target_gender} clients from DB (direct SQL) for event '{event_type}'")
                except Exception as e:
                    logger.error(f"Error executing SQL query for gender filter: {e}", exc_info=True)
                    # Fallback: используем определение по имени для всех клиентов
                    client_ids = []
                    logger.warning(f"Falling back to name-based filtering due to SQL error")
            
            # Если нашли достаточно клиентов, возвращаем их
            if len(client_ids) >= limit:
                return client_ids[:limit]
            
            # Если не хватает, добавляем клиентов с gender = NULL и определяем пол по имени
            if len(client_ids) < limit:
                remaining_needed = limit - len(client_ids)
                logger.info(f"Need {remaining_needed} more clients, checking clients with gender=NULL")
                
                # Берем клиентов с gender = NULL
                null_gender_clients = []
                try:
                    if has_gender_field:
                        query_null = select(User.id, User.full_name).where(
                            and_(
                                User.is_customer == True,
                                literal_column("gender").is_(None)
                            )
                        )
                        
                        # Применяем дополнительные критерии поиска
                        if search_criteria:
                            criteria_without_gender = {k: v for k, v in search_criteria.items() if k != "gender"}
                            if criteria_without_gender:
                                query_null = self.apply_search_criteria(query_null, criteria_without_gender)
                        
                        query_null = query_null.limit(remaining_needed * 3)
                        result_null = await self.db.execute(query_null)
                        null_gender_clients = result_null.all()
                    else:
                        # Используем прямой SQL для клиентов с gender = NULL
                        sql_query_null = """
                            SELECT id, full_name 
                            FROM users 
                            WHERE is_customer = TRUE AND gender IS NULL
                        """
                        params_null = {}
                        
                        # Добавляем условия из search_criteria
                        if search_criteria:
                            criteria_without_gender = {k: v for k, v in search_criteria.items() if k != "gender"}
                            if criteria_without_gender.get("min_total_spend_365") is not None:
                                sql_query_null += " AND total_spent >= :min_spend"
                                params_null["min_spend"] = criteria_without_gender["min_total_spend_365"]
                            if criteria_without_gender.get("max_total_spend_365") is not None:
                                sql_query_null += " AND total_spent <= :max_spend"
                                params_null["max_spend"] = criteria_without_gender["max_total_spend_365"]
                            if criteria_without_gender.get("min_purchases_365") is not None:
                                sql_query_null += " AND total_purchases >= :min_purchases"
                                params_null["min_purchases"] = criteria_without_gender["min_purchases_365"]
                            if criteria_without_gender.get("max_purchases_365") is not None:
                                sql_query_null += " AND total_purchases <= :max_purchases"
                                params_null["max_purchases"] = criteria_without_gender["max_purchases_365"]
                            if criteria_without_gender.get("cities"):
                                cities = [c.strip() for c in criteria_without_gender["cities"] if c.strip()]
                                if cities:
                                    sql_query_null += " AND city = ANY(:cities)"
                                    params_null["cities"] = cities
                        
                        sql_query_null += f" LIMIT {remaining_needed * 3}"
                        result_null = await self.db.execute(text(sql_query_null), params_null)
                        null_gender_clients = result_null.all()
                except Exception as e:
                    logger.error(f"Error getting NULL gender clients: {e}", exc_info=True)
                    null_gender_clients = []
                
                # Определяем пол по имени для клиентов с gender = NULL
                for row in null_gender_clients:
                    if len(client_ids) >= limit:
                        break
                    client_id = row[0]
                    full_name = row[1] if len(row) > 1 else None
                    
                    if full_name:
                        determined_gender = self._determine_gender_from_name(full_name)
                        if determined_gender == target_gender:
                            client_ids.append(client_id)
                
                logger.info(f"Added {len(client_ids) - (limit - remaining_needed)} clients from name-based filtering")
            
            return client_ids[:limit]
        else:
            # Не фильтруем по полу - берем всех клиентов
            query = select(User.id).where(User.is_customer == True)
            
            # Применяем дополнительные критерии поиска
            if search_criteria:
                query = self.apply_search_criteria(query, search_criteria)
            
            query = query.limit(limit)
            result = await self.db.execute(query)
            
            client_ids = [row[0] for row in result.all()]
            logger.info(f"Found {len(client_ids)} clients for event '{event_type}' (no gender filter)")
            return client_ids
    
    def _determine_gender_from_name(self, name: Optional[str]) -> Optional[str]:
        """
        Определение пола клиента по имени
        
        Проверяет оба слова (первое и второе), так как нет четкого правила,
        что идет первым - имя или фамилия.
        
        ВАЖНО: Если в имени только одно слово (только фамилия), не определяем пол
        по окончанию, так как это может быть неточно.
        
        Args:
            name: Полное имя клиента (может быть "Фамилия Имя" или "Имя Фамилия")
        
        Returns:
            "male", "female" или None если не удалось определить
        """
        if not name:
            return None
        
        name_parts = name.strip().split()
        if not name_parts:
            return None
        
        # Фильтруем части имени: убираем телефонные номера (только цифры)
        # Например: "Амедова 79788396090" -> ["Амедова"]
        filtered_parts = []
        for part in name_parts:
            # Если часть состоит только из цифр (телефон), пропускаем
            if part.isdigit():
                continue
            filtered_parts.append(part)
        
        # Если после фильтрации не осталось частей или осталась только одна - это фамилия
        if len(filtered_parts) == 0:
            return None
        
        # Если только одно слово (после фильтрации телефонов) - это скорее всего только фамилия
        # Не определяем пол по окончанию фамилии, так как это неточно
        if len(filtered_parts) == 1:
            # Проверяем только по списку имен (если это имя, а не фамилия)
            word = filtered_parts[0].lower()
            
            # Популярные женские имена
            female_names = {
                'анна', 'мария', 'елена', 'наталья', 'ольга', 'татьяна', 'ирина', 'екатерина',
                'светлана', 'юлия', 'анастасия', 'дарья', 'марина', 'людмила', 'валентина',
                'галина', 'надежда', 'виктория', 'любовь', 'валерия', 'алина',
                'кристина', 'полина', 'вероника', 'диана', 'майя', 'софия',
                'александра', 'василиса', 'милана', 'милена', 'алиса', 'эмилия', 'эмили',
                'виолетта', 'маргарита', 'елизавета', 'ксения', 'мирослава',
                'злата', 'ярослава', 'арина', 'карина', 'ангелина', 'нисо', 'урие', 'лидия'
            }
            
            # Популярные мужские имена
            male_names = {
                'александр', 'дмитрий', 'максим', 'сергей', 'андрей', 'алексей', 'артем',
                'илья', 'кирилл', 'михаил', 'николай', 'матвей', 'роман', 'павел', 'владимир',
                'денис', 'тимофей', 'иван', 'евгений', 'даниил', 'данил', 'данила', 'арсений',
                'леонид', 'степан', 'владислав', 'игорь', 'семен', 'антон',
                'василий', 'виктор', 'юрий', 'олег', 'валерий'
            }
            
            if word in female_names:
                return "female"
            if word in male_names:
                return "male"
            
            # Если не в списке имен, не определяем по окончанию (это может быть фамилия)
            return None
        
        # Проверяем оба слова (первое и второе), если их больше одного (после фильтрации телефонов)
        words_to_check = []
        if len(filtered_parts) >= 1:
            words_to_check.append(filtered_parts[0].lower())
        if len(filtered_parts) >= 2:
            words_to_check.append(filtered_parts[1].lower())
        
        if not words_to_check:
            return None
        
        # Популярные женские имена
        female_names = {
            'анна', 'мария', 'елена', 'наталья', 'ольга', 'татьяна', 'ирина', 'екатерина',
            'светлана', 'юлия', 'анастасия', 'дарья', 'марина', 'людмила', 'валентина',
            'галина', 'надежда', 'виктория', 'любовь', 'валерия', 'алина',
            'кристина', 'полина', 'вероника', 'диана', 'майя', 'софия',
            'александра', 'василиса', 'милана', 'милена', 'алиса', 'эмилия', 'эмили',
            'виолетта', 'маргарита', 'елизавета', 'ксения', 'мирослава',
            'злата', 'ярослава', 'арина', 'карина', 'ангелина'
        }
        
        # Популярные мужские имена
        male_names = {
            'александр', 'дмитрий', 'максим', 'сергей', 'андрей', 'алексей', 'артем',
            'илья', 'кирилл', 'михаил', 'николай', 'матвей', 'роман', 'павел', 'владимир',
            'денис', 'тимофей', 'иван', 'евгений', 'даниил', 'данил', 'данила', 'арсений',
            'леонид', 'степан', 'владислав', 'игорь', 'семен', 'антон',
            'василий', 'виктор', 'юрий', 'олег', 'валерий'
        }
        
        # Определение по окончанию
        female_endings = ['а', 'я', 'ия', 'ья', 'ея', 'уя', 'ая', 'яя']
        male_endings = ['й', 'ь', 'н', 'р', 'л', 'с', 'т', 'в', 'м', 'к', 'г', 'д', 'б', 'п', 'з', 'ж', 'ш', 'ч', 'ц', 'ф', 'х']
        
        # Собираем результаты для каждого слова
        results_by_list = []  # Результаты по списку имен (надежнее)
        results_by_ending = []  # Результаты по окончанию
        
        for word in words_to_check:
            # Проверка по списку имен (приоритет 1)
            if word in female_names:
                results_by_list.append("female")
            elif word in male_names:
                results_by_list.append("male")
            
            # Проверка по окончанию (приоритет 2)
            if len(word) > 1:
                last_char = word[-1]
                if last_char in female_endings:
                    results_by_ending.append("female")
                elif last_char in male_endings and last_char not in ['а', 'я']:
                    results_by_ending.append("male")
        
        # Приоритет: список имен > окончания
        # Если есть результаты по списку имен, используем их
        if results_by_list:
            # Если все результаты по списку одинаковые - возвращаем их
            if all(r == results_by_list[0] for r in results_by_list):
                result = results_by_list[0]
                logger.debug(f"Gender determined by name list for '{name}': {result} (words: {words_to_check})")
                return result
            # Если разные - выбираем первое (более надежное)
            result = results_by_list[0]
            logger.debug(f"Gender determined by name list (conflicting) for '{name}': {result} (words: {words_to_check}, all: {results_by_list})")
            return result
        
        # Если нет результатов по списку, используем окончания
        if results_by_ending:
            # Если все результаты по окончанию одинаковые - возвращаем их
            if all(r == results_by_ending[0] for r in results_by_ending):
                result = results_by_ending[0]
                logger.debug(f"Gender determined by ending for '{name}': {result} (words: {words_to_check})")
                return result
            # Если разные - выбираем первое
            result = results_by_ending[0]
            logger.debug(f"Gender determined by ending (conflicting) for '{name}': {result} (words: {words_to_check}, all: {results_by_ending})")
            return result
        
        logger.debug(f"Could not determine gender for '{name}' (words: {words_to_check})")
        return None
    
    def _extract_gender_from_event_name(self, event_name: str) -> Optional[str]:
        """
        Определение пола получателя сообщения из названия события
        
        ЛОГИКА:
        1. В скобках указывается, кому адресовано сообщение (получатели)
           Пример: "Праздничное сообщение (мужчинам)" → получатели: мужчины
        2. "от мужчин" / "от женщин" означает отправителя подарка, получатель - противоположный пол
           Пример: "Подарок на 14 февраля от мужчин" → получатели: женщины (получат подарок от мужчин)
        3. "для мужчин" / "для женщин" означает получателей сообщения
           Пример: "Подарок для мужчин" → получатели: мужчины
        
        Args:
            event_name: Название события
        
        Returns:
            "male", "female" или None если пол не указан
        """
        if not event_name:
            return None
        
        event_lower = event_name.lower()
        
        # 1. Сначала проверяем содержимое скобок (если есть)
        # Формат: "Название (мужчинам)" или "Название (женщинам)"
        # В скобках всегда указывается получатель сообщения
        import re
        bracket_match = re.search(r'\(([^)]+)\)', event_lower)
        if bracket_match:
            bracket_content = bracket_match.group(1).strip()
            # Ключевые слова для мужского пола в скобках
            if any(kw in bracket_content for kw in ['мужчин', 'мужчинам', 'мужской', 'мужчине']):
                logger.info(f"Found male gender in brackets for event '{event_name}'")
                return "male"
            # Ключевые слова для женского пола в скобках
            if any(kw in bracket_content for kw in ['женщин', 'женщинам', 'женский', 'женщине', 'девушк', 'девушкам']):
                logger.info(f"Found female gender in brackets for event '{event_name}'")
                return "female"
        
        # 2. Проверяем "от мужчин" / "от женщин" - это отправитель подарка, получатель - противоположный пол
        if 'от мужчин' in event_lower:
            logger.info(f"Found 'от мужчин' in event '{event_name}' - recipients are female")
            return "female"  # Подарок от мужчин → получатели женщины
        if 'от женщин' in event_lower:
            logger.info(f"Found 'от женщин' in event '{event_name}' - recipients are male")
            return "male"  # Подарок от женщин → получатели мужчины
        
        # 3. Проверяем "для мужчин" / "для женщин" - это получатели сообщения
        if 'для мужчин' in event_lower:
            logger.info(f"Found 'для мужчин' in event '{event_name}' - recipients are male")
            return "male"
        if 'для женщин' in event_lower or 'для девушек' in event_lower:
            logger.info(f"Found 'для женщин' in event '{event_name}' - recipients are female")
            return "female"
        
        # 4. Если не найдено в скобках и специальных конструкциях, ищем по всему тексту
        # Ключевые слова для мужского пола
        male_keywords = ['мужчин', 'мужчинам', 'мужской', 'мужчине']
        # Ключевые слова для женского пола
        female_keywords = ['женщин', 'женщинам', 'женский', 'женщине', 'девушк', 'девушкам']
        
        # Проверяем наличие ключевых слов (но не "от мужчин", так как это уже обработано)
        for keyword in male_keywords:
            if keyword in event_lower and 'от ' + keyword not in event_lower:
                logger.info(f"Found male keyword '{keyword}' in event '{event_name}'")
                return "male"
        
        for keyword in female_keywords:
            if keyword in event_lower and 'от ' + keyword not in event_lower:
                logger.info(f"Found female keyword '{keyword}' in event '{event_name}'")
                return "female"
        
        return None
    
    async def generate_batch_messages(
        self,
        client_ids: List[UUID],
        event: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Генерация сообщений для списка клиентов
        
        Args:
            client_ids: Список ID клиентов
            event: Событие для генерации
        
        Returns:
            Список сгенерированных сообщений
        """
        from app.agents.communication_agent import CommunicationAgent
        
        agent = CommunicationAgent(self.db)
        messages = []
        
        for client_id in client_ids:
            try:
                # Получаем данные клиента
                client_data = await self.get_client_data(client_id)
                
                if not client_data:
                    continue
                
                # Генерируем сообщение
                message = await agent.generate_message(
                    client_id=client_id,
                    event=event,
                    client_data=client_data
                )
                
                messages.append(message)
            
            except Exception as e:
                logger.warning(f"Failed to generate message for client {client_id}: {e}")
                continue
        
        return messages
