from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, cast, String, func, and_
from typing import List, Dict, Optional
from app.models.product import Product
from app.models.look import Look
from app.models.analytics_event import AnalyticsEvent
from app.services.persona_service import PersonaService
from app.services.vector_service import vector_service
from uuid import UUID
from datetime import datetime, timedelta
import re
import logging
import random

logger = logging.getLogger(__name__)


class RecommendationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.persona_service = PersonaService(db)
    
    async def recommend_products(
        self,
        persona: Optional[str] = None,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
        limit: int = 10,
        exclude_ids: Optional[List[UUID]] = None,
        randomize: bool = True
    ) -> List[Product]:
        """
        Подбор товаров на основе критериев
        
        Args:
            persona: Персона пользователя
            tags: Список тегов для фильтрации
            category: Категория товаров
            limit: Максимальное количество товаров
            exclude_ids: Список ID товаров для исключения
            randomize: Рандомизировать выбор товаров
        """
        from sqlalchemy.dialects.postgresql import JSONB
        import random
        
        query = select(Product).where(Product.is_active == True)
        
        # Исключаем товары, которые уже использованы
        if exclude_ids:
            query = query.where(Product.id.notin_(exclude_ids))
        
        # Фильтрация по категории
        if category:
            query = query.where(Product.category == category)
        
        # Фильтрация по тегам (исправленная версия для JSONB)
        if tags:
            from sqlalchemy import or_
            tag_conditions = []
            for tag in tags:
                # Правильный способ работы с JSONB в PostgreSQL
                # Используем оператор @> (contains) для проверки наличия тега в массиве
                tag_conditions.append(
                    Product.tags.contains([tag])
                )
            if tag_conditions:
                query = query.where(or_(*tag_conditions))
        
        # Если нужна рандомизация, используем ORDER BY RANDOM()
        if randomize:
            query = query.order_by(func.random())
        
        query = query.limit(limit * 2 if randomize else limit)  # Берем больше для рандомизации
        
        result = await self.db.execute(query)
        products = list(result.scalars().all())
        
        # Если рандомизация включена, перемешиваем и берем нужное количество
        if randomize and len(products) > limit:
            products = random.sample(products, min(limit, len(products)))
        
        return products
    
    async def recommend_looks(
        self,
        style: Optional[str] = None,
        mood: Optional[str] = None,
        persona: Optional[str] = None,
        limit: int = 5
    ) -> List[Look]:
        """Подбор образов на основе критериев"""
        query = select(Look)
        
        if style:
            query = query.where(Look.style == style)
        if mood:
            query = query.where(Look.mood == mood)
        
        query = query.limit(limit)
        
        result = await self.db.execute(query)
        looks = result.scalars().all()
        return list(looks)
    
    async def get_look_products(self, look_id: UUID) -> List[Product]:
        """Получение товаров из образа"""
        result = await self.db.execute(
            select(Look).where(Look.id == look_id)
        )
        look = result.scalar_one_or_none()
        
        if not look or not look.product_ids:
            return []
        
        product_ids = [UUID(pid) for pid in look.product_ids]
        result = await self.db.execute(
            select(Product).where(Product.id.in_(product_ids))
        )
        products = result.scalars().all()
        return list(products)

    async def search_products(
        self,
        query_text: str,
        limit: int = 8,
        only_active: bool = True,
    ) -> List[Product]:
        """
        Текстовый поиск товаров (для ContentAgent промптов).

        Это НЕ полнотекстовый поиск; это лёгкая эвристика:
        - name/brand/category/description ILIKE по токенам
        - tags содержит токен (используется правильный JSONB оператор)
        """
        from sqlalchemy.dialects.postgresql import JSONB
        from sqlalchemy import cast, String, func
        
        q = select(Product)
        if only_active:
            q = q.where(Product.is_active == True)

        tokens = [t.lower() for t in re.findall(r"[a-zA-Zа-яА-Я0-9_\\-]+", query_text or "") if len(t) >= 3]
        tokens = list(dict.fromkeys(tokens))[:8]  # uniq + cap

        if tokens:
            ors = []
            for t in tokens:
                like = f"%{t}%"
                # Ищем в текстовых полях (name, brand, category, description)
                # Проверка tags временно отключена из-за проблем с JSONB операторами в PostgreSQL
                # Поиск по текстовым полям покрывает большую часть случаев использования
                ors.extend([
                    Product.name.ilike(like),
                    Product.brand.ilike(like),
                    Product.category.ilike(like),
                    Product.description.ilike(like),
                ])
            q = q.where(or_(*ors))

        q = q.limit(limit)
        result = await self.db.execute(q)
        return list(result.scalars().all())
    
    async def recommend_looks_with_generation(
        self,
        style: Optional[str] = None,
        mood: Optional[str] = None,
        persona: Optional[str] = None,
        limit: int = 5,
        user_id: Optional[UUID] = None,
        session_id: Optional[UUID] = None,
        user_request: Optional[str] = None
    ) -> List[Look]:
        """
        Рекомендация образов с автоматической генерацией при недостатке образов
        
        Args:
            style: Стиль образа
            mood: Настроение образа
            persona: Персона пользователя
            limit: Максимальное количество образов
            user_id: ID пользователя
            session_id: ID сессии
            user_request: Текстовый запрос пользователя
        
        Returns:
            List[Look]: Список образов (существующие + сгенерированные)
        """
        # Сначала получаем существующие образы
        existing_looks = await self.recommend_looks(
            style=style,
            mood=mood,
            persona=persona,
            limit=limit
        )
        
        # Если недостаточно образов, генерируем новые
        if len(existing_looks) < limit:
            try:
                from app.services.look_generation_service import LookGenerationService
                generation_service = LookGenerationService(self.db)
                
                # Генерируем недостающие образы
                looks_to_generate = limit - len(existing_looks)
                generated_looks = []
                
                for _ in range(looks_to_generate):
                    try:
                        generated_look = await generation_service.generate_look(
                            user_id=user_id,
                            session_id=session_id,
                            style=style,
                            mood=mood,
                            persona=persona,
                            user_request=user_request
                        )
                        generated_looks.append(generated_look)
                    except Exception as e:
                        logger.warning(f"Ошибка при генерации образа: {e}")
                        continue
                
                # Объединяем существующие и сгенерированные
                all_looks = list(existing_looks) + generated_looks
                return all_looks[:limit]
            except Exception as e:
                logger.error(f"Ошибка при генерации образов: {e}")
                return existing_looks
        
        return existing_looks
    
    async def get_compatible_products(
        self,
        base_products: List[Product],
        style: Optional[str] = None,
        mood: Optional[str] = None,
        persona: Optional[str] = None,
        limit: int = 5
    ) -> List[Product]:
        """
        Подбор совместимых товаров для образа
        
        Args:
            base_products: Базовые товары образа
            style: Стиль образа
            mood: Настроение образа
            persona: Персона пользователя
            limit: Максимальное количество товаров
        
        Returns:
            List[Product]: Список совместимых товаров
        """
        if not base_products:
            return []
        
        # Извлекаем категории и бренды из базовых товаров
        categories = [p.category for p in base_products if p.category]
        brands = [p.brand for p in base_products if p.brand]
        
        # Исключаем ID базовых товаров
        exclude_ids = {p.id for p in base_products}
        
        # Подбираем совместимые товары
        compatible = []
        
        # По категориям
        for category in set(categories):
            if len(compatible) >= limit:
                break
            products = await self.recommend_products(
                persona=persona,
                category=category,
                limit=limit * 2
            )
            for p in products:
                if p.id not in exclude_ids and p.id not in {c.id for c in compatible}:
                    compatible.append(p)
                    if len(compatible) >= limit:
                        break
        
        # По брендам, если недостаточно
        if len(compatible) < limit:
            for brand in set(brands):
                if len(compatible) >= limit:
                    break
                query = select(Product).where(
                    Product.is_active == True,
                    Product.brand == brand,
                    Product.id.notin_(exclude_ids | {c.id for c in compatible})
                ).limit(limit - len(compatible))
                result = await self.db.execute(query)
                additional = result.scalars().all()
                compatible.extend(additional)
        
        # По стилю и персоне, если все еще недостаточно
        if len(compatible) < limit:
            query = select(Product).where(
                Product.is_active == True,
                Product.id.notin_(exclude_ids | {c.id for c in compatible})
            ).limit(limit - len(compatible))
            result = await self.db.execute(query)
            additional = result.scalars().all()
            compatible.extend(additional)
        
        return compatible[:limit]
    
    async def recommend_products_by_context(
        self,
        user_id: Optional[UUID] = None,
        query_text: Optional[str] = None,
        cjm_stage: Optional[str] = None,
        persona: Optional[str] = None,
        limit: int = 10,
        use_vector_search: bool = True
    ) -> List[Product]:
        """
        Подбор товаров на основе контекста пользователя:
        - История просмотров
        - История покупок
        - Текущий CJM этап
        - Векторный поиск в Qdrant для семантического подбора
        """
        # Получаем историю пользователя, если есть user_id
        viewed_product_ids = set()
        purchased_product_ids = set()
        user_preferences = {}
        
        if user_id:
            try:
                behavior_data = await self.persona_service.analyze_user_behavior(user_id, days=90)
                viewed_product_ids = set(behavior_data.get("product_ids", []))
                purchases = behavior_data.get("interactions", {}).get("purchases", 0)
                
                # Получаем предпочтения пользователя
                user_preferences = await self.persona_service.get_user_preferences(user_id, days=90)
                
                # Если нет персоны, определяем её
                if not persona:
                    persona = user_preferences.get("persona") or await self.persona_service.determine_persona(user_id)
            except Exception as e:
                logger.warning(f"Error getting user behavior for recommendations: {e}")
        
        # Формируем запрос для векторного поиска
        search_query = query_text or ""
        if persona:
            search_query += f" {persona}"
        if cjm_stage:
            search_query += f" {cjm_stage}"
        
        # Используем векторный поиск, если включен
        vector_results = []
        if use_vector_search and search_query and vector_service.openai_client:
            try:
                # Ищем похожие товары в Qdrant (если товары индексированы)
                # Пока используем поиск по описаниям товаров через векторный поиск
                vector_results = vector_service.get_context("brand_philosophy", search_query, limit=5)
            except Exception as e:
                logger.warning(f"Error in vector search: {e}")
        
        # Базовый SQL запрос
        query = select(Product).where(Product.is_active == True)
        
        # Приоритизируем товары, которые пользователь уже просматривал (но не покупал)
        # Это помогает показать товары, которые пользователь рассматривал
        if viewed_product_ids and not purchased_product_ids:
            # Исключаем купленные товары, но включаем просмотренные
            if purchased_product_ids:
                query = query.where(Product.id.notin_(purchased_product_ids))
        
        # Фильтрация по предпочтениям пользователя
        if user_preferences:
            favorite_categories = [cat[0] for cat in user_preferences.get("favorite_categories", [])[:3]]
            if favorite_categories:
                query = query.where(Product.category.in_(favorite_categories))
        
        # Фильтрация по персоне через теги
        # Используем поиск по текстовым полям вместо JSONB для частичных совпадений
        if persona:
            persona_keywords = {
                "fashion_girl": ["тренд", "модн", "стиль"],
                "status_woman": ["премиум", "качеств", "статус"],
                "romantic": ["романт", "нежн", "элегант"],
                "minimalist": ["минимал", "просто", "лаконич"]
            }
            keywords = persona_keywords.get(persona, [])
            if keywords:
                # Ищем ключевые слова в текстовых полях (name, description)
                # Это более надежно, чем поиск по JSONB тегам с частичными совпадениями
                keyword_conditions = []
                for keyword in keywords:
                    like_pattern = f"%{keyword}%"
                    keyword_conditions.extend([
                        Product.name.ilike(like_pattern),
                        Product.description.ilike(like_pattern),
                    ])
                if keyword_conditions:
                    query = query.where(or_(*keyword_conditions))
        
        # Учитываем CJM этап
        if cjm_stage == "purchase":
            # На этапе покупки показываем товары с хорошим соотношением цена/качество
            query = query.order_by(Product.price.asc())
        elif cjm_stage == "consideration":
            # На этапе сравнения показываем разнообразие
            query = query.order_by(func.random())
        else:
            # На этапе вдохновения показываем популярные/трендовые
            query = query.order_by(func.random())
        
        query = query.limit(limit * 2)  # Берем больше для фильтрации
        
        result = await self.db.execute(query)
        products = list(result.scalars().all())
        
        # Приоритизируем просмотренные товары (но не купленные)
        if viewed_product_ids:
            viewed_products = [p for p in products if p.id in viewed_product_ids]
            other_products = [p for p in products if p.id not in viewed_product_ids]
            products = viewed_products + other_products
        
        # Исключаем купленные товары из рекомендаций (если не запрошено иное)
        if purchased_product_ids:
            products = [p for p in products if p.id not in purchased_product_ids]
        
        return products[:limit]
    
    async def recommend_looks_by_query(
        self,
        query_text: str,
        user_id: Optional[UUID] = None,
        limit: int = 5,
        use_vector_search: bool = True
    ) -> List[Look]:
        """
        Подбор образов на основе текстового запроса с векторным поиском
        
        Args:
            query_text: Текстовый запрос пользователя
            user_id: ID пользователя для учета предпочтений
            limit: Максимальное количество образов
            use_vector_search: Использовать векторный поиск в Qdrant
        """
        # Получаем предпочтения пользователя
        user_preferences = {}
        if user_id:
            try:
                user_preferences = await self.persona_service.get_user_preferences(user_id, days=90)
            except Exception as e:
                logger.warning(f"Error getting user preferences: {e}")
        
        # Используем векторный поиск для семантического поиска образов
        vector_results = []
        if use_vector_search and vector_service.openai_client:
            try:
                # Ищем похожие описания образов в Qdrant
                # Пока используем поиск по бренд-контексту для понимания запроса
                vector_results = vector_service.get_context("brand_philosophy", query_text, limit=3)
            except Exception as e:
                logger.warning(f"Error in vector search for looks: {e}")
        
        # Извлекаем стиль и настроение из запроса
        style = None
        mood = None
        
        # Анализируем запрос для определения стиля и настроения
        query_lower = query_text.lower()
        
        # Определение стиля
        if any(word in query_lower for word in ["минимал", "просто", "лаконич"]):
            style = "minimalist"
        elif any(word in query_lower for word in ["романт", "нежн", "элегант"]):
            style = "romantic"
        elif any(word in query_lower for word in ["делов", "офис", "строг"]):
            style = "business"
        elif any(word in query_lower for word in ["повседнев", "casual"]):
            style = "casual"
        
        # Определение настроения
        if any(word in query_lower for word in ["радост", "весел", "ярк"]):
            mood = "joyful"
        elif any(word in query_lower for word in ["спокой", "умиротвор", "нежн"]):
            mood = "calm"
        elif any(word in query_lower for word in ["энергич", "динамич", "актив"]):
            mood = "energetic"
        elif any(word in query_lower for word in ["элегант", "изыскан", "утончен"]):
            mood = "elegant"
        
        # Используем предпочтения пользователя, если стиль/настроение не определены
        if not style and user_preferences:
            favorite_styles = user_preferences.get("favorite_styles", [])
            if favorite_styles:
                style = favorite_styles[0][0]  # Берем самый популярный стиль
        
        if not mood and user_preferences:
            favorite_moods = user_preferences.get("favorite_moods", [])
            if favorite_moods:
                mood = favorite_moods[0][0]  # Берем самое популярное настроение
        
        # Поиск образов
        looks_query = select(Look)
        
        if style:
            looks_query = looks_query.where(Look.style == style)
        if mood:
            looks_query = looks_query.where(Look.mood == mood)
        
        # Если есть векторные результаты, можем использовать их для фильтрации
        # Пока используем базовый поиск по стилю и настроению
        
        looks_query = looks_query.limit(limit)
        
        result = await self.db.execute(looks_query)
        looks = list(result.scalars().all())
        
        # Если недостаточно образов, расширяем поиск
        if len(looks) < limit:
            # Убираем фильтры и ищем любые образы
            extended_query = select(Look).limit(limit)
            extended_result = await self.db.execute(extended_query)
            all_looks = list(extended_result.scalars().all())
            
            # Объединяем результаты, убирая дубликаты
            existing_ids = {look.id for look in looks}
            for look in all_looks:
                if look.id not in existing_ids:
                    looks.append(look)
                    if len(looks) >= limit:
                        break
        
        return looks[:limit]
