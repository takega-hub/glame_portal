from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.base_agent import BaseAgent
from app.services.recommendation_service import RecommendationService
from app.models.product import Product


class ContentAgent(BaseAgent):
    """AI Content Agent - генерация контента для бренда"""
    
    BRAND_SYSTEM_PROMPT = """Ты - контент-менеджер бренда GLAME, пространства авторских украшений и аксессуаров.

GLAME - это место, где стиль становится отражением характера. Мы предлагаем уникальные украшения от известных брендов: Antura, Uno de 50, и других.

Твоя задача - создавать вдохновляющий контент, который:
- Отражает философию бренда
- Обращается к целевой аудитории
- Мотивирует к действию
- Соответствует этапу Customer Journey Map

Будь креативным, но профессиональным."""
    
    def __init__(self, db: AsyncSession):
        super().__init__()
        self.db = db
        self.recommendation_service = RecommendationService(db)

    def _format_products_for_prompt(self, products: List[Product]) -> str:
        if not products:
            return "Нет подходящих товаров в каталоге (или каталог пуст)."

        lines = []
        for p in products[:8]:
            price_rub = f"{(p.price or 0)/100:.0f} ₽" if p.price is not None else "—"
            tags = ", ".join(p.tags) if isinstance(p.tags, list) and p.tags else "—"
            lines.append(
                f"- {p.name} ({p.brand or 'GLAME'}), {price_rub}. Категория: {p.category or '—'}. Теги: {tags}."
            )
        return "\n".join(lines)
    
    async def process(
        self,
        persona: Optional[str] = None,
        cjm_stage: Optional[str] = None,
        channel: str = "website_main",
        goal: Optional[str] = None
    ) -> Dict[str, Any]:
        """Генерация контента"""
        
        # Получаем контекст бренда из базы знаний
        import logging
        logger = logging.getLogger(__name__)
        query_text = f"{persona or ''} {cjm_stage or ''} {goal or ''}"
        brand_context = await self.get_brand_context(query_text, limit=3)
        logger.info(f"ContentAgent.process: получено {len(brand_context)} фрагментов из базы знаний для query: '{query_text[:50]}...'")

        # Подбираем товары из каталога (Postgres), чтобы контент был привязан к реальным позициям
        products = await self.recommendation_service.search_products(query_text=query_text, limit=6, only_active=True)
        logger.info(f"ContentAgent.process: найдено {len(products)} товаров в каталоге для query: '{query_text[:50]}...'")
        
        # Формируем промпт
        prompt = f"""Создай контент для бренда GLAME.

Персона: {persona or 'не указана'}
Этап CJM: {cjm_stage or 'не указан'}
Канал: {channel}
Цель: {goal or 'вдохновить и мотивировать'}

Контекст бренда:
{self._format_brand_context(brand_context)}

Товары из каталога GLAME (используй реальные названия, не выдумывай позиции/цены):
{self._format_products_for_prompt(products)}

Создай контент, который:
1. Соответствует персоне и этапу CJM
2. Подходит для канала {channel}
3. Достигает цели: {goal or 'вдохновить'}
4. Отражает философию GLAME"""
        
        # Генерируем контент
        content = await self.generate_response(
            prompt=prompt,
            system_prompt=self.BRAND_SYSTEM_PROMPT,
            temperature=0.8
        )
        
        return {
            "content": content,
            "persona": persona,
            "cjm_stage": cjm_stage
        }

    async def generate_calendar_plan(
        self,
        start_date: str,
        end_date: str,
        timezone: str,
        channels: List[str],
        frequency_rules: Optional[Dict[str, Any]] = None,
        persona: Optional[str] = None,
        goal: Optional[str] = None,
        campaign_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Генерация структурированного календарного контент-плана (JSON).

        Даты передаются строками ISO (например, 2026-02-01 или 2026-02-01T00:00:00+03:00),
        чтобы не ломать парсинг на клиенте.
        """
        # Получаем контекст бренда из базы знаний
        import logging
        logger = logging.getLogger(__name__)
        query_text = f"{persona or ''} {goal or ''} {campaign_context or ''}"
        brand_context = await self.get_brand_context(query_text, limit=5)
        logger.info(f"ContentAgent.generate_calendar_plan: получено {len(brand_context)} фрагментов из базы знаний для query: '{query_text[:50]}...'")

        # Товары из каталога — чтобы план включал реальные product-mentions
        products = await self.recommendation_service.search_products(query_text=query_text, limit=8, only_active=True)
        logger.info(f"ContentAgent.generate_calendar_plan: найдено {len(products)} товаров в каталоге для query: '{query_text[:50]}...'")

        response_format = {
            "plan": {
                "title": "План контента GLAME на период",
                "timezone": timezone,
                "start_date": start_date,
                "end_date": end_date,
                "channels": channels,
                "notes": "Короткие правила и допущения"
            },
            "items": [
                {
                    "scheduled_at": "2026-02-03T12:00:00+03:00",
                    "channel": "instagram",
                    "content_type": "post",
                    "topic": "Тема поста",
                    "hook": "Хук/первое предложение",
                    "cta": "Призыв к действию",
                    "persona": persona or "не указана",
                    "cjm_stage": "awareness",
                    "goal": goal or "вдохновить",
                    "spec": {
                        "tone": "теплый, премиальный, вдохновляющий",
                        "length": "коротко/средне/длинно",
                        "assets_needed": ["фото продукта", "видео примерка"],
                        "hashtags": ["#glame", "#украшения"],
                        "media_task": {
                            "type": "photo",
                            "goal": "Поддержать публикацию визуалом под тему слота",
                            "style": "премиальная editorial fashion-фотография, дерзкие ракурсы, выразительные позы, без текста на изображении",
                            "assets_needed": ["студийное фото украшения", "чистый фон"],
                            "model_profile": "default",
                            "status": "ready_for_generation"
                        }
                    }
                }
            ]
        }

        prompt = f"""Составь календарный контент-план для бренда GLAME.

Период: {start_date} → {end_date}
Timezone: {timezone}
Каналы: {", ".join(channels)}
Персона: {persona or "не указана"}
Цель: {goal or "не указана"}
Контекст/кампания: {campaign_context or "не указано"}
Правила частоты (если есть): {frequency_rules or {}}

Контекст бренда:
{self._format_brand_context(brand_context)}

Товары из каталога GLAME (используй эти названия в слотах периодически; не выдумывай новые позиции):
{self._format_products_for_prompt(products)}

Требования:
- Верни ТОЛЬКО валидный JSON (без текста).
- В items добавь равномерное распределение по периодам и каналам.
- Учитывай разнообразие: product spotlight, storytelling, UGC, education, promo, engagement.
- scheduled_at должен быть ISO datetime со смещением (например, +03:00).
- Для каждого item добавь в spec.media_task структурированное задание на фото (type=photo, goal, style, assets_needed, model_profile, status).
"""

        structured = await self.llm.generate_structured(
            prompt=prompt,
            response_format=response_format,
            system_prompt=self.BRAND_SYSTEM_PROMPT,
            temperature=0.4,
            max_tokens=4000,
        )
        return structured

    async def generate_item_content(
        self,
        channel: str,
        content_type: str,
        topic: Optional[str] = None,
        hook: Optional[str] = None,
        cta: Optional[str] = None,
        persona: Optional[str] = None,
        cjm_stage: Optional[str] = None,
        goal: Optional[str] = None,
        spec: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Генерация контента под конкретный слот календаря."""
        # Получаем контекст бренда из базы знаний
        import logging
        logger = logging.getLogger(__name__)
        query_text = f"{persona or ''} {cjm_stage or ''} {goal or ''} {topic or ''}"
        brand_context = await self.get_brand_context(query_text, limit=5)
        logger.info(f"ContentAgent.generate_item_content: получено {len(brand_context)} фрагментов из базы знаний для query: '{query_text[:50]}...'")

        products = await self.recommendation_service.search_products(query_text=query_text, limit=6, only_active=True)
        logger.info(f"ContentAgent.generate_item_content: найдено {len(products)} товаров в каталоге для query: '{query_text[:50]}...'")

        response_format = {
            "title": "Заголовок/тема (если уместно)",
            "text": "Основной текст",
            "variants": ["Альтернатива 1", "Альтернатива 2"],
            "hashtags": ["#glame"],
            "cta": cta or "Перейти на сайт / написать в директ / записаться",
        }

        # Извлекаем feedback пользователя из spec, если есть
        user_feedback = None
        spec_dict = spec or {}
        if isinstance(spec_dict, dict):
            user_feedback = spec_dict.get("user_feedback")
            if user_feedback:
                logger.info(f"ContentAgent.generate_item_content: получен feedback пользователя: {user_feedback[:100]}...")

        prompt = f"""Создай контент для бренда GLAME под конкретный слот.

Канал: {channel}
Формат: {content_type}
Тема: {topic or "не указана"}
Хук: {hook or "не указан"}
CTA: {cta or "не указан"}
Персона: {persona or "не указана"}
Этап CJM: {cjm_stage or "не указан"}
Цель: {goal or "вдохновить и мотивировать"}
Тех. требования/spec: {spec or {}}
{f'Пожелания пользователя для переделки: {user_feedback}' if user_feedback else ''}

Контекст бренда:
{self._format_brand_context(brand_context)}

Товары из каталога GLAME (если уместно — упомяни 1-2 конкретные позиции):
{self._format_products_for_prompt(products)}

Требования:
- Верни ТОЛЬКО валидный JSON (без текста).
- Подстрой стиль под канал и формат.
- Не выдумывай факты про скидки/наличие/цены, если их нет в вводных.
{f'- Учти пожелания пользователя: {user_feedback}' if user_feedback else ''}
"""

        return await self.llm.generate_structured(
            prompt=prompt,
            response_format=response_format,
            system_prompt=self.BRAND_SYSTEM_PROMPT,
            temperature=0.6,
            max_tokens=2500,
        )
    
    async def generate_product_description(
        self,
        product: Product,
        rewrite_existing: bool = False,
        seo_keywords: Optional[List[str]] = None,
        target_length: Optional[str] = "medium",  # short, medium, long
    ) -> Dict[str, Any]:
        """
        Генерация SEO-оптимизированного описания товара.
        
        Описание должно быть:
        - SEO-оптимизированным (ключевые слова, структура)
        - AI-оптимизированным (для поисковых систем с AI)
        - Читаемым для человека (естественный язык)
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Получаем контекст бренда
        query_text = f"{product.name} {product.brand or ''} {product.category or ''} {' '.join(product.tags or [])}"
        brand_context = await self.get_brand_context(query_text, limit=5)
        logger.info(f"ContentAgent.generate_product_description: получено {len(brand_context)} фрагментов из базы знаний для товара: {product.name}")
        
        # Формируем информацию о товаре
        price_rub = f"{(product.price or 0)/100:.0f} ₽" if product.price is not None else "—"
        tags_str = ", ".join(product.tags) if isinstance(product.tags, list) and product.tags else "—"
        category_str = product.category or "украшения"
        brand_str = product.brand or "GLAME"
        
        # SEO-ключевые слова (если не указаны, генерируем на основе товара)
        if not seo_keywords:
            seo_keywords = [
                product.name.lower(),
                brand_str.lower(),
                category_str.lower(),
            ]
            if product.tags:
                seo_keywords.extend([tag.lower() for tag in product.tags[:3]])
        
        # Определяем длину описания
        length_guidance = {
            "short": "150-200 символов (краткое описание для карточки)",
            "medium": "300-500 символов (стандартное описание)",
            "long": "600-1000 символов (подробное описание с деталями)",
        }
        target_length_text = length_guidance.get(target_length, length_guidance["medium"])
        
        prompt = f"""Создай SEO-оптимизированное описание товара для бренда GLAME.

Товар:
- Название: {product.name}
- Бренд: {brand_str}
- Категория: {category_str}
- Цена: {price_rub}
- Теги: {tags_str}
- Текущее описание: {product.description or 'отсутствует'}

SEO-ключевые слова для включения: {', '.join(seo_keywords[:5])}

Контекст бренда GLAME:
{self._format_brand_context(brand_context)}

Требования к описанию:
1. SEO-оптимизация:
   - Естественное включение ключевых слов (не переспам)
   - Структурированный текст (абзацы, списки при необходимости)
   - Уникальность (не копируй существующее описание)
   - Мета-информация: упоминание бренда, категории, стиля

2. AI-оптимизация:
   - Понятная структура для AI-поисковых систем
   - Семантически связанные термины
   - Контекст использования и преимущества

3. Читаемость для человека:
   - Естественный, вдохновляющий язык
   - Эмоциональная связь с покупателем
   - Конкретные детали и преимущества
   - Призыв к действию (неявный)

4. Длина: {target_length_text}

5. Стиль: премиальный, вдохновляющий, но не пафосный

{"ВАЖНО: Перепиши существующее описание, улучшив его с учетом SEO и читаемости." if rewrite_existing and product.description else "Создай новое описание с нуля."}

Верни ТОЛЬКО текст описания, без дополнительных комментариев."""

        description = await self.generate_response(
            prompt=prompt,
            system_prompt=self.BRAND_SYSTEM_PROMPT + "\n\nТы - SEO-копирайтер, специализирующийся на премиальных украшениях. Создавай описания, которые одновременно привлекают поисковые системы и вдохновляют покупателей.",
            temperature=0.7,
            max_tokens=1500 if target_length == "long" else 800,
        )
        
        # Очистка описания от возможных артефактов LLM
        description = description.strip()
        # Убираем кавычки, если LLM обернул в них
        if description.startswith('"') and description.endswith('"'):
            description = description[1:-1]
        if description.startswith("'") and description.endswith("'"):
            description = description[1:-1]
        
        return {
            "description": description,
            "length": len(description),
            "seo_keywords_used": seo_keywords[:5],
            "rewritten": rewrite_existing and product.description is not None,
        }
    
    def _format_brand_context(self, context: list) -> str:
        """Форматирование контекста бренда (использует улучшенный метод из BaseAgent)"""
        return self.format_brand_context_for_prompt(context) if context else "Философия GLAME: стиль как отражение характера."
