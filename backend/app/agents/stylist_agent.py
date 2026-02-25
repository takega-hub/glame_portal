from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.agents.base_agent import BaseAgent
from app.services.recommendation_service import RecommendationService
from app.services.persona_service import PersonaService
from app.models.session import Session as DBSession
from app.models.look import Look
from uuid import UUID, uuid4


class StylistAgent(BaseAgent):
    """AI Stylist Agent - основной агент для подбора образов"""
    
    BRAND_SYSTEM_PROMPT = """Ты - персональный стилист бренда GLAME, пространства авторских украшений и аксессуаров.

GLAME - это место, где стиль становится отражением характера. Мы предлагаем уникальные украшения от известных брендов: Antura, Uno de 50, и других.

Твоя задача:
- Помочь клиенту найти идеальный образ для его ситуации
- Подобрать украшения, которые отражают его личность
- Предложить как онлайн покупку, так и визит в офлайн пространство GLAME
- Быть дружелюбным, профессиональным и вдохновляющим

Всегда предлагай конкретные образы с товарами из каталога GLAME."""
    
    PERSONAS = {
        "fashion_girl": "Молодая активная девушка, следит за трендами, любит экспериментировать",
        "status_woman": "Успешная женщина, ценит качество и статусные вещи",
        "romantic": "Романтичная натура, предпочитает нежные и элегантные образы",
        "minimalist": "Минималист, ценит простоту и лаконичность"
    }
    
    CJM_STAGES = {
        "inspiration": "Поиск вдохновения, изучение вариантов",
        "consideration": "Сравнение вариантов, выбор",
        "purchase": "Готовность к покупке"
    }
    
    def __init__(self, db: AsyncSession):
        super().__init__()
        self.db = db
        self.recommendation_service = RecommendationService(db)
        self.persona_service = PersonaService(db)
    
    async def detect_persona(
        self,
        message: str,
        user_history: List[Dict] = None,
        user_id: Optional[UUID] = None
    ) -> str:
        """Определение персоны пользователя с учетом истории покупок и просмотров"""
        # Если есть user_id, используем PersonaService для анализа поведения
        if user_id:
            try:
                behavior_data = await self.persona_service.analyze_user_behavior(user_id)
                persona_from_behavior = await self.persona_service.determine_persona(user_id, behavior_data)
                
                # Если есть сохраненная персона в профиле пользователя, используем её
                from app.models.user import User
                result = await self.db.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.scalar_one_or_none()
                if user and user.persona:
                    # Используем сохраненную персону, но можем скорректировать на основе поведения
                    return user.persona
                
                # Если нет сохраненной персоны, используем определенную по поведению
                if persona_from_behavior:
                    # Сохраняем персону в профиле пользователя
                    await self.persona_service.update_user_persona(user_id, persona_from_behavior)
                    return persona_from_behavior
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Error analyzing user behavior for persona detection: {e}")
        
        # Fallback: определяем персону по сообщению через LLM
        try:
            prompt = f"""Проанализируй сообщение пользователя и определи его персону.

Сообщение: {message}

Доступные персоны:
- fashion_girl: Молодая активная девушка, следит за трендами
- status_woman: Успешная женщина, ценит качество
- romantic: Романтичная натура, предпочитает нежные образы
- minimalist: Минималист, ценит простоту

Ответь ТОЛЬКО одним словом: fashion_girl, status_woman, romantic или minimalist."""
            
            response = await self.generate_response(
                prompt=prompt,
                system_prompt="Ты анализируешь персону пользователя. Отвечай только одним словом.",
                temperature=0.3
            )
            
            persona = response.strip().lower()
            detected_persona = persona if persona in self.PERSONAS else "fashion_girl"
            
            # Сохраняем персону, если есть user_id
            if user_id:
                try:
                    await self.persona_service.update_user_persona(user_id, detected_persona)
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Error saving persona to user profile: {e}")
            
            return detected_persona
        except (ValueError, Exception) as e:
            # Fallback: определяем персону по ключевым словам, если LLM недоступен
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"LLM недоступен для detect_persona, используем fallback: {e}")
            message_lower = message.lower()
            if any(word in message_lower for word in ["романт", "свидан", "любов", "нежн"]):
                return "romantic"
            elif any(word in message_lower for word in ["делов", "офис", "работа", "строг"]):
                return "status_woman"
            elif any(word in message_lower for word in ["минимал", "просто", "лаконич"]):
                return "minimalist"
            else:
                return "fashion_girl"
    
    async def detect_cjm_stage(self, message: str, user_history: List[Dict] = None) -> str:
        """Определение этапа Customer Journey Map"""
        try:
            prompt = f"""Определи этап Customer Journey Map пользователя.

Сообщение: {message}

Этапы:
- inspiration: Ищет вдохновение, изучает варианты
- consideration: Сравнивает варианты, выбирает
- purchase: Готов купить

Ответь ТОЛЬКО одним словом: inspiration, consideration или purchase."""
            
            response = await self.generate_response(
                prompt=prompt,
                system_prompt="Ты определяешь этап CJM. Отвечай только одним словом.",
                temperature=0.3
            )
            
            stage = response.strip().lower()
            return stage if stage in self.CJM_STAGES else "inspiration"
        except (ValueError, Exception) as e:
            # Fallback: определяем этап по ключевым словам, если LLM недоступен
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"LLM недоступен для detect_cjm_stage, используем fallback: {e}")
            message_lower = message.lower()
            if any(word in message_lower for word in ["купить", "заказ", "оформить", "приобрести"]):
                return "purchase"
            elif any(word in message_lower for word in ["сравнить", "выбрать", "какой лучше"]):
                return "consideration"
            else:
                return "inspiration"
    
    async def process(
        self,
        user_id: Optional[UUID],
        message: str,
        city: Optional[str] = None,
        session_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Основная логика обработки запроса"""
        
        # Загружаем данные пользователя для персонализации
        user_context = ""
        if user_id:
            from app.models.user import User
            from app.models.purchase_history import PurchaseHistory
            
            result = await self.db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            
            if user and user.is_customer:
                # Загружаем историю покупок
                result = await self.db.execute(
                    select(PurchaseHistory)
                    .where(PurchaseHistory.user_id == user_id)
                    .order_by(PurchaseHistory.purchase_date.desc())
                    .limit(10)
                )
                purchases = result.scalars().all()
                
                # Формируем контекст для персонализации
                if user.purchase_preferences:
                    favorite_categories = user.purchase_preferences.get("favorite_categories", [])
                    favorite_brands = user.purchase_preferences.get("favorite_brands", [])
                    
                    user_context = f"""
История покупок покупателя:
- Любимые категории: {', '.join(favorite_categories) if favorite_categories else 'не определены'}
- Любимые бренды: {', '.join(favorite_brands) if favorite_brands else 'не определены'}
- Средний чек: {user.average_check / 100 if user.average_check else 0} руб
- Всего покупок: {user.total_purchases}
- Последняя покупка: {user.last_purchase_date.strftime('%d.%m.%Y') if user.last_purchase_date else 'нет данных'}

Учитывай предпочтения покупателя при рекомендациях. Рекомендуй товары в диапазоне среднего чека ±30%.
"""
        
        # Получаем или создаем сессию
        if session_id:
            result = await self.db.execute(
                select(DBSession).filter(DBSession.id == session_id)
            )
            session = result.scalar_one_or_none()
            if not session:
                session = DBSession(
                    id=uuid4(),
                    user_id=user_id,
                    city=city,
                    interactions=[]
                )
                self.db.add(session)
        else:
            session = DBSession(
                id=uuid4(),
                user_id=user_id,
                city=city,
                interactions=[]
            )
            self.db.add(session)
        
        # Определяем персону и CJM этап
        persona = await self.detect_persona(
            message,
            session.interactions if session.interactions else [],
            user_id=user_id
        )
        cjm_stage = await self.detect_cjm_stage(message, session.interactions if session.interactions else [])
        
        # Обновляем сессию
        session.persona_detected = persona
        session.cjm_stage = cjm_stage
        if not session.interactions:
            session.interactions = []
        session.interactions.append({
            "message": message,
            "persona": persona,
            "cjm_stage": cjm_stage
        })
        
        # Получаем контекст бренда из базы знаний
        import logging
        logger = logging.getLogger(__name__)
        
        # Извлекаем название коллекции из сообщения для более точного поиска
        collection_name = self._extract_collection_name(message)
        
        # Ищем в нескольких коллекциях: brand_philosophy и collections_info
        brand_context = await self.get_brand_context(message, limit=3)
        
        # Для поиска коллекций используем более специфичный запрос
        collections_query = collection_name if collection_name else message
        collections_context = await self.get_collections_context(collections_query, limit=5)
        
        # Объединяем контексты (убираем дубликаты по ID)
        seen_ids = set()
        all_context = []
        for ctx in brand_context + collections_context:
            ctx_id = ctx.get("id")
            if ctx_id and ctx_id not in seen_ids:
                seen_ids.add(ctx_id)
                all_context.append(ctx)
        
        logger.info(
            f"StylistAgent: получено {len(brand_context)} фрагментов из brand_philosophy, "
            f"{len(collections_context)} из collections_info (запрос: '{collections_query[:50]}...'), "
            f"всего {len(all_context)} уникальных для запроса: '{message[:50]}...'"
        )
        
        # Используем объединенный контекст
        brand_context = all_context
        
        # Подбираем товары и образы с учетом контекста
        tags = self._extract_tags_from_message(message)
        
        # Используем улучшенный метод с учетом истории пользователя
        products = await self.recommendation_service.recommend_products_by_context(
            user_id=user_id,
            query_text=message,
            cjm_stage=cjm_stage,
            persona=persona,
            limit=10,
            use_vector_search=True
        )
        
        # Если новый метод не вернул достаточно товаров, используем старый
        if len(products) < 5:
            products_fallback = await self.recommendation_service.recommend_products(
                persona=persona,
            tags=tags,
            limit=12  # Увеличиваем лимит, чтобы было больше товаров для карточек
        )
        
        # Подбираем образы с учетом запроса пользователя
        looks = await self.recommendation_service.recommend_looks_by_query(
            query_text=message,
            user_id=user_id,
            limit=5,
            use_vector_search=True
        )
        
        # Если новый метод не вернул достаточно образов, используем старый
        if len(looks) < 3:
            looks_fallback = await self.recommendation_service.recommend_looks(
                style=self._extract_style_from_message(message),
                mood=self._extract_mood_from_message(message),
                persona=persona,
                limit=5 - len(looks)
            )
            # Объединяем, убирая дубликаты
            existing_look_ids = {look.id for look in looks}
            for look in looks_fallback:
                if look.id not in existing_look_ids:
                    looks.append(look)
        
        # Формируем промпт для LLM
        products_info = "\n".join([
            f"- {p.name} ({p.brand or 'GLAME'}) - {p.price/100:.0f} руб. Теги: {', '.join(p.tags) if p.tags else 'нет тегов'}"
            for p in products[:5]
        ]) if products else "Пока нет доступных товаров"
        
        looks_info = "\n".join([
            f"- {l.name}: {l.description or l.mood or l.style}. Товары: {', '.join([str(pid) for pid in l.product_ids[:3]])}"
            for l in looks
        ]) if looks else "Пока нет доступных образов"
        
        # Форматируем контекст бренда для промпта с использованием улучшенного метода
        brand_context_text = self.format_brand_context_for_prompt(brand_context) if brand_context else "Философия GLAME: стиль как отражение характера. Мы предлагаем уникальные украшения от известных брендов."
        
        prompt = f"""Пользователь написал: "{message}"

Персона: {persona} ({self.PERSONAS.get(persona, '')})
Этап CJM: {cjm_stage} ({self.CJM_STAGES.get(cjm_stage, '')})
Город: {city or 'не указан'}
{user_context if user_context else ''}

ВАЖНО: Используй следующий контекст бренда GLAME для формирования ответа:
{brand_context_text}

Доступные товары:
{products_info}

Доступные образы:
{looks_info}

Сформируй ответ стилиста:
1. Дружелюбно поприветствуй и покажи понимание запроса
2. Предложи 1-2 конкретных образа с товарами
3. Объясни, почему эти образы подходят, ОБЯЗАТЕЛЬНО используя информацию из контекста бренда выше
4. Предложи действие: купить онлайн или записаться в пространство GLAME{' в ' + city if city else ''}

КРИТИЧЕСКИ ВАЖНО:
- Используй конкретные факты и формулировки из контекста бренда GLAME
- Отражай философию и ценности бренда в своем ответе
- Будь вдохновляющим и профессиональным
- Используй конкретные названия товаров
- Опирайся на контекст бренда при объяснении, почему образы подходят"""
        
        # Генерируем ответ
        try:
            reply = await self.generate_response(
                prompt=prompt,
                system_prompt=self.BRAND_SYSTEM_PROMPT,
                temperature=0.8,
                max_tokens=3000  # Увеличиваем лимит токенов для более полных ответов
            )
        except (ValueError, Exception) as e:
            # Fallback ответ если LLM недоступен (например, нет OPENROUTER_API_KEY)
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"LLM недоступен для генерации ответа, используем fallback: {e}")
            
            # Простой ответ на основе доступных данных
            if looks and products:
                look_names = ", ".join([l.name for l in looks[:2]])
                product_count = len(products[:5])
                reply = f"""Привет! Я вижу твой запрос: "{message[:50]}...". 

Для тебя я подобрала {len(looks)} образа: {look_names}. В них входят {product_count} стильных украшения от GLAME, которые идеально подойдут для твоей ситуации.

Хочешь посмотреть детали образов или записаться в наше пространство GLAME для примерки?"""
            elif products:
                product_names = ", ".join([p.name for p in products[:3]])
                reply = f"""Привет! Я вижу твой запрос: "{message[:50]}...". 

Для тебя я подобрала несколько украшений: {product_names}. Это стильные изделия от GLAME, которые идеально подойдут для твоей ситуации.

Хочешь посмотреть детали товаров или записаться в наше пространство GLAME для примерки?"""
            else:
                reply = f"""Привет! Я вижу твой запрос: "{message[:50]}...". 

Я помогу тебе подобрать идеальный образ! GLAME - это пространство авторских украшений и аксессуаров, где стиль становится отражением характера.

Хочешь записаться в наше пространство GLAME для консультации и примерки?"""
        
        # Формируем структурированный ответ
        selected_looks = []
        all_products_in_looks = set()  # Для отслеживания товаров, уже включенных в образы
        
        for look in looks[:2]:
            look_products = await self.recommendation_service.get_look_products(look.id)
            product_list = [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "brand": p.brand,
                    "price": p.price,
                    "images": p.images if p.images is not None else [],
                    "category": p.category,
                    "tags": p.tags if p.tags is not None else [],
                    "external_code": p.external_code
                }
                for p in look_products
            ]
            selected_looks.append({
                "id": str(look.id),
                "name": look.name,
                "products": product_list,
                "mood": look.mood,
                "style": look.style
            })
            # Добавляем ID товаров из образа в множество
            all_products_in_looks.update(str(p.id) for p in look_products)
        
        # Формируем отдельный список всех рекомендованных товаров для карточек
        # Включаем товары из образов + дополнительные товары, если их меньше 6
        recommended_products = []
        
        # Сначала добавляем товары из образов
        for look in selected_looks:
            for product in look["products"]:
                if product["id"] not in [p["id"] for p in recommended_products]:
                    recommended_products.append(product)
        
        # Добавляем дополнительные товары из общего списка, если их меньше 6
        if len(recommended_products) < 6 and products:
            for p in products:
                if str(p.id) not in all_products_in_looks and len(recommended_products) < 6:
                    recommended_products.append({
                        "id": str(p.id),
                        "name": p.name,
                        "brand": p.brand,
                        "price": p.price,
                        "images": p.images if p.images is not None else [],
                        "category": p.category,
                        "tags": p.tags if p.tags is not None else [],
                        "external_code": p.external_code
                    })
        
        # Сохраняем сессию
        await self.db.commit()
        
        # Формируем CTA
        cta = f"Записаться в пространство GLAME{' в ' + city if city else ''}" if city else "Записаться в пространство GLAME"
        
        return {
            "persona": persona,
            "cjm_stage": cjm_stage,
            "reply": reply,
            "looks": selected_looks,
            "products": recommended_products,  # Отдельный список товаров для карточек
            "cta": cta,
            "session_id": str(session.id)
        }
    
    def _extract_tags_from_message(self, message: str) -> List[str]:
        """Извлечение тегов из сообщения (упрощенная версия)"""
        message_lower = message.lower()
        tags = []
        
        tag_keywords = {
            "романтичный": ["романт", "свидан", "любов"],
            "вечерний": ["вечер", "ужин", "торжеств"],
            "деловой": ["делов", "офис", "работа"],
            "повседневный": ["повседнев", "каждый день", "обычн"]
        }
        
        for tag, keywords in tag_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                tags.append(tag)
        
        return tags
    
    def _extract_collection_name(self, message: str) -> Optional[str]:
        """Извлечение названия коллекции из сообщения"""
        import re
        message_lower = message.lower()
        
        # Известные коллекции GLAME
        known_collections = [
            "crystal", "momenti", "geometry", "wine dream", 
            "winedream", "disco", "shine", "сияние", "кристалл"
        ]
        
        # Ищем упоминания коллекций
        for collection in known_collections:
            if collection.lower() in message_lower:
                # Возвращаем оригинальное название с заглавной буквы
                return collection.title()
        
        # Пытаемся извлечь название после слов "коллекция", "collection"
        patterns = [
            r"коллекци[ия]\s+([а-яёa-z]+)",
            r"collection\s+([a-z]+)",
            r"о\s+коллекци[ия]\s+([а-яёa-z]+)",
            r"расскажи\s+о\s+([а-яёa-z]+)",
            r"что\s+такое\s+([а-яёa-z]+)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message_lower, re.IGNORECASE)
            if match:
                potential_name = match.group(1).strip()
                if len(potential_name) > 2:  # Минимальная длина названия
                    return potential_name.title()
        
        return None
    
    def _extract_style_from_message(self, message: str) -> Optional[str]:
        """Извлечение стиля из сообщения"""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ["романт", "нежн", "элегант"]):
            return "романтичный"
        elif any(word in message_lower for word in ["делов", "строг", "классич"]):
            return "деловой"
        elif any(word in message_lower for word in ["повседнев", "casual"]):
            return "повседневный"
        
        return None
    
    def _extract_mood_from_message(self, message: str) -> Optional[str]:
        """Извлечение настроения из сообщения"""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ["свидан", "романт"]):
            return "романтичный вечер"
        elif any(word in message_lower for word in ["работа", "офис"]):
            return "уверенный день"
        elif any(word in message_lower for word in ["праздник", "торжеств"]):
            return "праздничный"
        
        return None
    
    def _format_brand_context(self, context: list) -> str:
        """Форматирование контекста бренда из базы знаний"""
        if not context:
            return "Философия GLAME: стиль как отражение характера. Мы предлагаем уникальные украшения от известных брендов."
        
        formatted = "\n".join([
            f"- {item.get('payload', {}).get('text', '')}"
            for item in context
            if item.get('payload', {}).get('text')
        ])
        
        return formatted if formatted else "Философия GLAME: стиль как отражение характера."
    
    async def generate_look_for_user(
        self,
        user_id: Optional[UUID],
        session_id: Optional[UUID],
        style: Optional[str] = None,
        mood: Optional[str] = None,
        persona: Optional[str] = None,
        user_request: Optional[str] = None,
        generate_image: bool = True,
        use_default_model: bool = False
    ) -> Dict[str, Any]:
        """
        Генерация образа для пользователя
        
        Args:
            user_id: ID пользователя
            session_id: ID сессии
            style: Стиль образа
            mood: Настроение образа
            persona: Персона пользователя
            user_request: Текстовый запрос пользователя
        
        Returns:
            Dict: Сгенерированный образ с метаданными
        """
        from app.services.look_generation_service import LookGenerationService
        
        generation_service = LookGenerationService(self.db)
        
        # Если персона не указана, определяем её
        if not persona and session_id:
            result = await self.db.execute(
                select(DBSession).where(DBSession.id == session_id)
            )
            session = result.scalar_one_or_none()
            if session:
                persona = session.persona_detected
        
        # Генерируем образ
        look = await generation_service.generate_look(
            user_id=user_id,
            session_id=session_id,
            style=style,
            mood=mood,
            persona=persona,
            user_request=user_request,
            generate_image=generate_image,
            use_default_model=use_default_model
        )
        
        await self.db.commit()
        
        # Получаем товары образа
        products = await self.recommendation_service.get_look_products(look.id)
        
        return {
            "id": str(look.id),
            "name": look.name,
            "description": look.description,
            "style": look.style,
            "mood": look.mood,
            "status": look.status,
            "approval_status": look.approval_status,
            "products": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "brand": p.brand,
                    "price": p.price,
                    "images": p.images if p.images is not None else [],
                    "category": p.category,
                    "tags": p.tags if p.tags is not None else []
                }
                for p in products
            ],
            "generation_metadata": look.generation_metadata,
            "fashion_trends": look.fashion_trends
        }
    
    async def try_on_look(
        self,
        look_id: UUID,
        user_photo_data: bytes,
        user_id: Optional[UUID] = None,
        filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Примерка образа на фото пользователя
        
        Args:
            look_id: ID образа
            user_photo_data: Байты фото пользователя
            user_id: ID пользователя
            filename: Имя файла фото
        
        Returns:
            Dict: Результат примерки с URL изображения
        """
        from app.services.look_tryon_service import look_tryon_service
        
        # Получаем образ
        result = await self.db.execute(
            select(Look).where(Look.id == look_id)
        )
        look = result.scalar_one_or_none()
        
        if not look:
            raise ValueError(f"Образ {look_id} не найден")
        
        # Получаем товары образа
        products = await self.recommendation_service.get_look_products(look.id)
        
        if not products:
            raise ValueError("В образе нет товаров для примерки")
        
        # Анализируем фото пользователя
        photo_analysis = await look_tryon_service.analyze_photo(
            photo_data=user_photo_data,
            filename=filename
        )
        
        # Сохраняем фото пользователя
        if user_id:
            user_photo_url = await look_tryon_service.save_user_photo(
                photo_data=user_photo_data,
                user_id=user_id,
                filename=filename
            )
        else:
            # Временное сохранение, если нет user_id
            import tempfile
            import uuid as uuid_lib
            temp_filename = f"temp_{uuid_lib.uuid4()}.jpg"
            user_photo_url = await look_tryon_service.save_user_photo(
                photo_data=user_photo_data,
                user_id=uuid_lib.uuid4(),  # Временный ID
                filename=temp_filename
            )
        
        # Получаем изображения товаров
        product_images = []
        for product in products:
            if product.images:
                product_images.extend(product.images[:1])  # Берем первое изображение каждого товара
        
        # Генерируем изображение с примеркой
        try_on_image_url = await look_tryon_service.generate_tryon_image(
            user_photo_url=user_photo_url,
            product_images=product_images,
            look_id=look_id
        )
        
        # Обновляем образ с URL примерки
        look.try_on_image_url = try_on_image_url
        await self.db.commit()
        
        return {
            "look_id": str(look.id),
            "try_on_image_url": try_on_image_url,
            "user_photo_url": user_photo_url,
            "photo_analysis": photo_analysis,
            "products_count": len(products)
        }
    
    async def approve_look(
        self,
        look_id: UUID,
        user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Одобрение сгенерированного образа
        
        Args:
            look_id: ID образа
            user_id: ID пользователя, который одобряет
        
        Returns:
            Dict: Обновленный образ
        """
        result = await self.db.execute(
            select(Look).where(Look.id == look_id)
        )
        look = result.scalar_one_or_none()
        
        if not look:
            raise ValueError(f"Образ {look_id} не найден")
        
        # Обновляем статус
        look.approval_status = "approved"
        if look.status == "auto_generated":
            look.status = "approved"
        
        await self.db.commit()
        await self.db.refresh(look)
        
        # Получаем товары образа
        products = await self.recommendation_service.get_look_products(look.id)
        
        return {
            "id": str(look.id),
            "name": look.name,
            "status": look.status,
            "approval_status": look.approval_status,
            "products": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "brand": p.brand,
                    "price": p.price
                }
                for p in products
            ]
        }