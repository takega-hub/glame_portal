from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Optional
from uuid import UUID
import logging
import json

from app.models.look import Look
from app.models.user import User
from app.models.session import Session as DBSession
from app.models.product import Product
from app.services.fashion_trends_service import fashion_trends_service
from app.services.vector_service import vector_service
from app.services.llm_service import llm_service
from app.services.recommendation_service import RecommendationService
from app.services.image_generation_service import image_generation_service

logger = logging.getLogger(__name__)


class LookGenerationService:
    """Сервис для автоматической генерации образов на основе правил клиента и трендов"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.recommendation_service = RecommendationService(db)

    @staticmethod
    def _extract_product_combination(product: Product) -> Optional[str]:
        """
        Извлекает значение параметра "Сочетание" из specifications товара.
        """
        specs = product.specifications if isinstance(product.specifications, dict) else {}
        for key in ("Сочетание", "сочетание", "combination", "Combination"):
            value = specs.get(key)
            if value is None:
                continue
            if isinstance(value, list):
                value = value[0] if value else None
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    def _get_dominant_combination(self, products: List[Product]) -> Optional[str]:
        counts: Dict[str, int] = {}
        for product in products:
            combo = self._extract_product_combination(product)
            if not combo:
                continue
            counts[combo] = counts.get(combo, 0) + 1
        if not counts:
            return None
        combo, count = max(counts.items(), key=lambda item: item[1])
        return combo if count >= 2 else None
    
    async def generate_look(
        self,
        user_id: Optional[UUID] = None,
        session_id: Optional[UUID] = None,
        style: Optional[str] = None,
        mood: Optional[str] = None,
        persona: Optional[str] = None,
        user_request: Optional[str] = None,
        generate_image: bool = True,
        use_default_model: bool = False,
        digital_model: Optional[str] = None,
    ) -> Look:
        """
        Генерация образа на основе правил клиента и трендов
        
        Args:
            user_id: ID пользователя
            session_id: ID сессии
            style: Стиль образа
            mood: Настроение образа
            persona: Персона пользователя
            user_request: Текстовый запрос пользователя
        
        Returns:
            Look: Сгенерированный образ со статусом auto_generated
        """
        # 1. Сбор требований клиента
        client_requirements = await self.get_client_requirements(
            user_id=user_id,
            session_id=session_id,
            user_request=user_request
        )
        
        # 2. Получение актуальных трендов
        if style:
            trends = await fashion_trends_service.get_trends_for_style(style)
        else:
            trends = await fashion_trends_service.get_current_trends()
        
        # 3. Получение контекста бренда
        brand_context_query = user_request or f"{style or ''} {mood or ''}".strip()
        brand_context = vector_service.get_brand_context(
            brand_context_query or "украшения",
            limit=3
        )
        
        # 4. Получение требований из векторной БД
        requirements_context = []
        if user_request:
            requirements_context = vector_service.get_context(
                "client_requirements",
                user_request,
                limit=3
            )
        
        # 5. Генерация промпта для LLM
        prompt = self._build_generation_prompt(
            client_requirements=client_requirements,
            trends=trends,
            brand_context=brand_context,
            requirements_context=requirements_context,
            style=style,
            mood=mood,
            persona=persona,
            user_request=user_request
        )
        
        # 6. Генерация описания образа через LLM
        look_description = await self._generate_look_description(prompt)
        
        # 7. Подбор товаров для образа
        selected_products = await self.select_products_for_look(
            look_description=look_description,
            client_requirements=client_requirements,
            style=style,
            mood=mood,
            persona=persona,
            require_images=True,
        )
        
        # 8. Валидация образа
        validated_products = await self.validate_look(selected_products)
        
        if not validated_products:
            raise ValueError("Не удалось подобрать совместимые товары для образа")
        
        # 9. Создание объекта Look
        look = Look(
            name=look_description.get("name", "Автоматически сгенерированный образ"),
            product_ids=[str(p.id) for p in validated_products],
            style=style or look_description.get("style"),
            mood=mood or look_description.get("mood"),
            description=look_description.get("description"),
            status="auto_generated",
            approval_status="pending",
            user_id=user_id,
            generation_metadata={
                "persona": persona,
                "client_requirements": client_requirements,
                "generation_method": "ai_agent",
                "digital_model": digital_model,
                "combination": self._get_dominant_combination(validated_products),
            },
            fashion_trends=trends[:5],  # Сохраняем первые 5 трендов
            client_requirements=client_requirements
        )
        
        self.db.add(look)
        await self.db.flush()
        
        # 10. Генерация изображения образа (если требуется)
        if generate_image:
            try:
                logger.info(f"Начало генерации изображения для образа {look.id}")
                products_data = [
                    {
                        "name": p.name,
                        "description": p.description,
                        "category": p.category,
                        "images": p.images or []
                    }
                    for p in validated_products
                ]
                safe_model = image_generation_service._sanitize_profile_name(digital_model)
                
                # Генерируем изображение и ждем завершения
                image_url = await image_generation_service.generate_look_image(
                    look_description=look_description,
                    products=products_data,
                    use_default_model=use_default_model,
                    model_profile=safe_model,
                    asset_group=f"look_images/models/{safe_model}" if safe_model else "look_images",
                    filename_prefix=f"look_{safe_model}" if safe_model else "look",
                )
                
                if image_url:
                    look.image_url = image_url
                    await self.db.flush()
                    logger.info(f"Генерация изображения для образа {look.id} завершена успешно: {image_url}")
                else:
                    logger.warning(f"Генерация изображения для образа {look.id} не вернула URL (возможно, использована типовая модель или произошла ошибка)")
            except Exception as e:
                logger.warning(f"Не удалось сгенерировать изображение для образа {look.id}: {e}")
                # Не прерываем процесс, образ создается без изображения
        
        await self.db.commit()
        await self.db.refresh(look)
        
        logger.info(f"Генерация образа {look.id} для пользователя {user_id} полностью завершена")
        
        return look
    
    async def get_client_requirements(
        self,
        user_id: Optional[UUID] = None,
        session_id: Optional[UUID] = None,
        user_request: Optional[str] = None
    ) -> Dict:
        """
        Сбор требований клиента из всех источников
        
        Args:
            user_id: ID пользователя
            session_id: ID сессии
            user_request: Текстовый запрос пользователя
        
        Returns:
            Dict: Объединенные требования клиента
        """
        requirements = {}
        
        # 1. Из профиля пользователя
        if user_id:
            result = await self.db.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
            if user and user.preferences:
                requirements["user_preferences"] = user.preferences
                requirements["persona"] = user.persona
        
        # 2. Из истории сессии
        if session_id:
            result = await self.db.execute(
                select(DBSession).where(DBSession.id == session_id)
            )
            session = result.scalar_one_or_none()
            if session:
                if session.persona_detected:
                    requirements["detected_persona"] = session.persona_detected
                if session.interactions:
                    # Извлекаем ключевые слова из последних взаимодействий
                    recent_interactions = session.interactions[-5:]  # Последние 5
                    interaction_texts = [
                        i.get("message", "") for i in recent_interactions
                        if isinstance(i, dict)
                    ]
                    requirements["recent_interactions"] = " ".join(interaction_texts)
        
        # 3. Из векторной БД (если есть запрос)
        if user_request:
            vector_requirements = vector_service.get_context(
                "client_requirements",
                user_request,
                limit=3
            )
            if vector_requirements:
                requirements["vector_requirements"] = [
                    item.get("payload", {}).get("text", "")
                    for item in vector_requirements
                ]
        
        return requirements
    
    async def select_products_for_look(
        self,
        look_description: Dict,
        client_requirements: Dict,
        style: Optional[str] = None,
        mood: Optional[str] = None,
        persona: Optional[str] = None,
        limit: int = 5,
        require_images: bool = False,
    ) -> List[Product]:
        """
        Подбор товаров для образа с учетом разнообразия и исключения уже использованных
        
        Args:
            look_description: Описание образа от LLM
            client_requirements: Требования клиента
            style: Стиль
            mood: Настроение
            persona: Персона
            limit: Максимальное количество товаров
        
        Returns:
            List[Product]: Список подобранных товаров
        """
        # Получаем список уже использованных товаров в других образах
        # Это поможет избежать повторения одних и тех же товаров
        used_product_ids = await self._get_recently_used_product_ids(limit=50)
        
        # Извлекаем категории и теги из описания
        categories = look_description.get("categories", [])
        tags = look_description.get("tags", [])
        
        # Если категории не указаны, пробуем извлечь из описания или использовать общие
        if not categories:
            # Пробуем найти категории в описании образа
            description_text = (look_description.get("description", "") + " " + 
                             look_description.get("name", "")).lower()
            # Базовые категории для украшений
            possible_categories = ["кулон", "кольцо", "серьги", "браслет", "колье", "подвеска"]
            for cat in possible_categories:
                if cat in description_text:
                    categories.append(cat)
        
        # Учитываем предпочтения пользователя
        user_prefs = client_requirements.get("user_preferences", {})
        favorite_brands = user_prefs.get("favorite_brands", [])
        budget_range = user_prefs.get("budget_range", {})
        forbidden_elements = user_prefs.get("forbidden_elements", [])
        
        # Подбираем товары с рандомизацией и исключением уже использованных
        products = []
        exclude_ids = set(used_product_ids)
        
        # Сначала пробуем по категориям из описания (с рандомизацией)
        for category in categories[:3]:  # Берем первые 3 категории для разнообразия
            if len(products) >= limit * 2:  # Собираем больше для лучшего выбора
                break
            category_products = await self.recommendation_service.recommend_products(
                persona=persona,
                category=category,
                tags=None,  # Сначала без тегов для более широкого выбора
                limit=limit * 2,
                exclude_ids=list(exclude_ids),
                randomize=True,  # Включаем рандомизацию
                require_images=require_images,
            )
            products.extend(category_products)
            # Добавляем найденные товары в исключения для следующей итерации
            exclude_ids.update(p.id for p in category_products)
        
        # Если недостаточно, добавляем по тегам (материал, цвет, стиль)
        if len(products) < limit * 2 and tags:
            tag_products = await self.recommendation_service.recommend_products(
                persona=persona,
                tags=tags,
                category=None,
                limit=limit * 2,
                exclude_ids=list(exclude_ids),
                randomize=True,
                require_images=require_images,
            )
            products.extend(tag_products)
            exclude_ids.update(p.id for p in tag_products)
        
        # Если все еще недостаточно, добавляем товары по стилю и персоне
        if len(products) < limit * 2:
            # Ищем товары, которые подходят по стилю (в названии или описании)
            style_keywords = []
            if style:
                style_keywords.append(style.lower())
            if mood:
                style_keywords.append(mood.lower())
            
            if style_keywords:
                # Используем текстовый поиск для поиска товаров по стилю
                search_query = " ".join(style_keywords)
                style_products = await self.recommendation_service.search_products(
                    query_text=search_query,
                    limit=limit * 2,
                    only_active=True,
                    require_images=require_images,
                )
                # Фильтруем уже добавленные
                style_products = [p for p in style_products if p.id not in exclude_ids]
                products.extend(style_products)
                exclude_ids.update(p.id for p in style_products)
        
        # Если все еще недостаточно, добавляем случайные товары (но не те, что уже использовались)
        if len(products) < limit:
            random_products = await self.recommendation_service.recommend_products(
                persona=persona,
                tags=None,
                category=None,
                limit=limit * 3,
                exclude_ids=list(used_product_ids),  # Исключаем только недавно использованные
                randomize=True,
                require_images=require_images,
            )
            products.extend(random_products)
        
        # Фильтруем по бюджету, брендам и другим критериям
        filtered_products = []
        for product in products:
            # Проверка бюджета
            if budget_range:
                min_price = budget_range.get("min", 0)
                max_price = budget_range.get("max", float('inf'))
                if not (min_price <= product.price <= max_price):
                    continue
            
            # Проверка запрещенных элементов
            if forbidden_elements and product.description:
                product_text = (product.description + " " + product.name).lower()
                if any(forbidden.lower() in product_text for forbidden in forbidden_elements):
                    continue
            
            # Приоритет любимым брендам
            if favorite_brands and product.brand:
                if product.brand in favorite_brands:
                    filtered_products.insert(0, product)
                    continue
            
            filtered_products.append(product)
        
        # Убираем дубликаты и обеспечиваем разнообразие категорий
        # Дополнительно повышаем шанс красивого образа:
        # товары с одинаковым значением параметра "Сочетание" приоритизируются.
        combination_counts: Dict[str, int] = {}
        for product in filtered_products:
            combo = self._extract_product_combination(product)
            if combo:
                combination_counts[combo] = combination_counts.get(combo, 0) + 1
        preferred_combination: Optional[str] = None
        if combination_counts:
            candidate_combo, candidate_count = max(combination_counts.items(), key=lambda item: item[1])
            if candidate_count >= 2:
                preferred_combination = candidate_combo
                filtered_products = sorted(
                    filtered_products,
                    key=lambda p: 0 if self._extract_product_combination(p) == preferred_combination else 1,
                )

        seen_ids = set()
        unique_products = []
        category_counts = {}  # Отслеживаем количество товаров по категориям
        
        for product in filtered_products:
            if product.id in seen_ids:
                continue
            
            # Ограничиваем количество товаров одной категории (максимум 2)
            category = product.category or "other"
            if category_counts.get(category, 0) >= 2 and len(unique_products) >= 3:
                continue
            
            seen_ids.add(product.id)
            unique_products.append(product)
            category_counts[category] = category_counts.get(category, 0) + 1
            
            if len(unique_products) >= limit:
                break
        
        return unique_products[:limit]
    
    async def _get_recently_used_product_ids(self, limit: int = 50) -> List[UUID]:
        """
        Получает список ID товаров, которые недавно использовались в образах
        Это помогает избежать повторения одних и тех же товаров
        """
        try:
            # Получаем последние N образов
            result = await self.db.execute(
                select(Look)
                .order_by(Look.created_at.desc())
                .limit(limit)
            )
            recent_looks = result.scalars().all()
            
            # Собираем все product_ids из этих образов
            used_ids = set()
            for look in recent_looks:
                if look.product_ids:
                    for pid in look.product_ids:
                        try:
                            used_ids.add(UUID(pid))
                        except (ValueError, TypeError):
                            continue
            
            return list(used_ids)
        except Exception as e:
            logger.warning(f"Ошибка при получении списка использованных товаров: {e}")
            return []
    
    async def validate_look(self, products: List[Product]) -> List[Product]:
        """
        Валидация образа - проверка совместимости товаров
        
        Args:
            products: Список товаров для проверки
        
        Returns:
            List[Product]: Валидированный список товаров
        """
        if not products:
            return []
        
        # Базовая валидация:
        # 1. Проверяем, что товары активны
        active_products = [p for p in products if p.is_active]
        
        # 2. Проверяем разнообразие категорий (не все товары одной категории)
        categories = [p.category for p in active_products if p.category]
        if len(set(categories)) < 2 and len(active_products) > 2:
            # Если все товары одной категории и их больше 2, оставляем только 2
            category_counts = {}
            for p in active_products:
                cat = p.category or "other"
                category_counts[cat] = category_counts.get(cat, []) + [p]
            
            validated = []
            for cat, prods in category_counts.items():
                validated.extend(prods[:2])  # Максимум 2 товара одной категории
            return validated[:5]  # Максимум 5 товаров в образе
        
        return active_products[:5]  # Максимум 5 товаров в образе
    
    def _build_generation_prompt(
        self,
        client_requirements: Dict,
        trends: List[Dict],
        brand_context: List[Dict],
        requirements_context: List[Dict],
        style: Optional[str],
        mood: Optional[str],
        persona: Optional[str],
        user_request: Optional[str]
    ) -> str:
        """Построение промпта для генерации образа"""
        
        # Форматируем тренды
        trends_text = "\n".join([
            f"- {t.get('name', 'Тренд')}: {t.get('description', '')}"
            for t in trends[:5]
        ]) if trends else "Актуальные модные тренды не найдены"
        
        # Форматируем контекст бренда
        brand_text = "\n".join([
            item.get("payload", {}).get("text", "")
            for item in brand_context
        ]) if brand_context else "Философия GLAME: стиль как отражение характера"
        
        # Форматируем требования клиента
        reqs_text = ""
        if client_requirements.get("user_preferences"):
            prefs = client_requirements["user_preferences"]
            reqs_text += f"Предпочтения пользователя: {json.dumps(prefs, ensure_ascii=False)}\n"
        if client_requirements.get("detected_persona"):
            reqs_text += f"Определенная персона: {client_requirements['detected_persona']}\n"
        if client_requirements.get("recent_interactions"):
            reqs_text += f"Последние запросы: {client_requirements['recent_interactions'][:200]}\n"
        
        if requirements_context:
            reqs_text += "\nДополнительные требования из базы знаний:\n"
            reqs_text += "\n".join([
                item.get("payload", {}).get("text", "")
                for item in requirements_context
            ])
        
        prompt = f"""Ты персональный стилист бренда GLAME. Создай образ на основе следующих данных:

Контекст бренда GLAME:
{brand_text}

Актуальные модные тренды:
{trends_text}

Требования и предпочтения клиента:
{reqs_text or "Не указаны"}

Параметры образа:
- Стиль: {style or "не указан"}
- Настроение: {mood or "не указано"}
- Персона: {persona or "не определена"}
- Запрос пользователя: {user_request or "не указан"}

ВАЖНО для разнообразия образов:
1. Используй РАЗНЫЕ категории товаров в каждом образе. Доступные категории: кулон, кольцо, серьги, браслет, колье, подвеска, цепочка, брошь, заколка, ободок
2. В тегах указывай конкретные характеристики: материал (золото, серебро, сталь, акрилл, кожа), цвет (золотой, серебряный, черный, белый, винный, розовый), стиль (минимализм, классика, модерн, винтаж), форма (геометрия, круг, овал, квадрат)
3. Создавай УНИКАЛЬНЫЙ образ, отличающийся от предыдущих. Избегай повторения одних и тех же комбинаций категорий и тегов.
4. В образе должно быть 3-5 товаров из РАЗНЫХ категорий для создания гармоничного комплекта.

Создай описание образа в формате JSON:
{{
  "name": "Название образа (2-4 слова, уникальное)",
  "description": "Подробное описание образа (3-5 предложений)",
  "style": "Стиль образа",
  "mood": "Настроение образа",
  "categories": ["категория1", "категория2", "категория3"],
  "tags": ["материал", "цвет", "стиль", "форма", "дополнительная_характеристика"],
  "reasoning": "Почему этот образ подходит (2-3 предложения)"
}}

Примеры хороших комбинаций категорий:
- ["кулон", "кольцо", "серьги"] - классический комплект
- ["браслет", "колье", "подвеска"] - акцент на шею и запястье
- ["кольцо", "серьги", "заколка"] - элегантный дневной образ

Ответь ТОЛЬКО валидным JSON без дополнительного текста."""
        
        return prompt
    
    async def _generate_look_description(self, prompt: str) -> Dict:
        """Генерация описания образа через LLM"""
        try:
            response = await llm_service.generate(
                prompt=prompt,
                system_prompt="Ты эксперт-стилист. Отвечай только валидным JSON.",
                temperature=0.8,
                max_tokens=2000
            )
            
            # Парсим JSON из ответа
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = response
            
            description = json.loads(json_str)
            return description
        except Exception as e:
            logger.error(f"Ошибка при генерации описания образа: {e}")
            # Возвращаем базовое описание
            return {
                "name": "Стильный образ от GLAME",
                "description": "Элегантный образ, подобранный специально для вас",
                "style": "универсальный",
                "mood": "вдохновляющий",
                "categories": ["кольца", "серьги"],
                "tags": ["элегантность", "стиль"],
                "reasoning": "Образ создан на основе ваших предпочтений"
            }
