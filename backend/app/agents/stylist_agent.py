from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from app.agents.base_agent import BaseAgent
from app.services.recommendation_service import RecommendationService
from app.services.persona_service import PersonaService
from app.models.session import Session as DBSession
from app.models.look import Look
from app.models.saved_look import SavedLook
from app.models.product import Product
from app.models.catalog_section import CatalogSection
from app.models.product_catalog_section import ProductCatalogSection
from app.models.product_stock import ProductStock
from app.models.store import Store
from app.models.app_store import AppStore
from app.models.app_lookbook import AppLookbook
from app.models.app_news import AppNews
from app.models.app_promotion import AppPromotion
from app.models.knowledge_document import KnowledgeDocument
from uuid import UUID, uuid4
import re


@dataclass
class CustomerStyleDNA:
    occasion: Optional[str] = None
    style: Optional[str] = None
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    materials: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    brands: List[str] = field(default_factory=list)
    dislikes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "occasion": self.occasion,
            "style": self.style,
            "budget_min": self.budget_min,
            "budget_max": self.budget_max,
            "materials": self.materials,
            "categories": self.categories,
            "brands": self.brands,
            "dislikes": self.dislikes,
        }


@dataclass
class SalesDecision:
    stage: str
    next_action: str
    cta_type: str
    should_show_products: bool
    should_show_looks: bool
    objection: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "next_action": self.next_action,
            "cta_type": self.cta_type,
            "should_show_products": self.should_show_products,
            "should_show_looks": self.should_show_looks,
            "objection": self.objection,
        }


class StylistAgent(BaseAgent):
    """AI Stylist Agent - основной агент для подбора образов"""

    AGENT_TYPE = "stylist-agent"
    PROMPT_AGENT_TYPE = "stylist"
    
    BRAND_SYSTEM_PROMPT = """Ты - персональный стилист бренда GLAME, пространства авторских украшений и аксессуаров.

GLAME - это место, где стиль становится отражением характера. Мы предлагаем уникальные украшения от известных брендов: Antura, Uno de 50, и других.

Твоя задача:
- Помочь клиенту найти идеальный образ для его ситуации
- Подобрать украшения, которые отражают его личность
- Предложить как онлайн покупку, так и визит в офлайн пространство GLAME
- Быть дружелюбным, профессиональным и вдохновляющим
- Говорить по-человечески, без шаблонных фраз и заученных продажных формул
- Запоминать важные детали о человеке и опираться на них в следующих сообщениях

Не предлагай товары и не веди к покупке, если пользователь сейчас задает справочный или уточняющий вопрос."""
    
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

    async def _find_nomenclature_products(self, message: str, limit: int = 6) -> List[Product]:
        """
        Поиск товаров по номенклатуре/артикулу/коду/названию.
        Используется для ответов про конкретные позиции в чате.
        """
        text = (message or "").strip()
        if not text:
            return []

        tokens = list({t for t in re.findall(r"[a-zA-Zа-яА-Я0-9_\-]{3,}", text)})[:10]
        if not tokens:
            return []

        exact_clauses = []
        ilike_clauses = []
        for token in tokens:
            exact_clauses.extend(
                [
                    Product.article == token,
                    Product.external_code == token,
                    Product.external_id == token,
                ]
            )
            like = f"%{token}%"
            ilike_clauses.extend(
                [
                    Product.name.ilike(like),
                    Product.article.ilike(like),
                    Product.external_code.ilike(like),
                ]
            )

        query = (
            select(Product)
            .where(
                Product.is_active == True,
                or_(*(exact_clauses + ilike_clauses)),
            )
            .limit(limit * 2)
        )
        result = await self.db.execute(query)
        rows = list(result.scalars().all())
        if not rows:
            return []

        # Приоритизируем точные совпадения по артикулу/коду
        normalized = {t.lower() for t in tokens}

        def _score(product: Product) -> tuple[int, int]:
            article = str(product.article or "").lower()
            ext_code = str(product.external_code or "").lower()
            ext_id = str(product.external_id or "").lower()
            exact = int(any(x in normalized for x in [article, ext_code, ext_id] if x))
            has_images = int(isinstance(product.images, list) and len(product.images) > 0)
            return (exact, has_images)

        rows.sort(key=_score, reverse=True)
        return rows[:limit]

    async def _build_stores_context(self, city: Optional[str], limit: int = 10) -> str:
        # Источник магазинов для клиентского приложения: контент app_stores (админка приложения)
        stores_query = select(AppStore).where(AppStore.is_active == True)
        if city and city.strip():
            city_q = city.strip()
            stores_query = stores_query.where(AppStore.city.ilike(f"%{city_q}%"))
        stores_result = await self.db.execute(
            stores_query.order_by(AppStore.sort_order.asc(), AppStore.city.asc(), AppStore.title.asc()).limit(limit)
        )
        stores = list(stores_result.scalars().all())

        if not stores:
            return "Нет данных по активным магазинам в выбранном городе."

        lines = []
        for store in stores:
            address = store.address or "адрес уточняется"
            city_name = store.city or "город не указан"
            phone = f", тел: {store.phone}" if store.phone else ""
            hours = f", часы: {store.working_hours}" if store.working_hours else ""
            lines.append(f"- {store.title} ({city_name}): {address}{phone}{hours}")
        return "\n".join(lines)

    async def _get_stores_payload(self, city: Optional[str], limit: int = 6) -> List[Dict[str, Any]]:
        stores_query = select(AppStore).where(AppStore.is_active == True)
        if city and city.strip():
            city_q = city.strip()
            stores_query = stores_query.where(AppStore.city.ilike(f"%{city_q}%"))
        stores_result = await self.db.execute(
            stores_query.order_by(AppStore.sort_order.asc(), AppStore.city.asc(), AppStore.title.asc()).limit(limit)
        )
        stores = list(stores_result.scalars().all())
        payload: List[Dict[str, Any]] = []
        for store in stores:
            payload.append(
                {
                    "id": str(store.id),
                    "city": store.city,
                    "title": store.title,
                    "address": store.address,
                    "working_hours": store.working_hours,
                    "phone": store.phone,
                    "latitude": float(store.latitude) if store.latitude is not None else None,
                    "longitude": float(store.longitude) if store.longitude is not None else None,
                }
            )
        return payload

    @staticmethod
    def _detect_store_city_from_message(message: str) -> Optional[str]:
        text = (message or "").lower()
        if "ялт" in text:
            return "Ялта"
        if "симферопол" in text:
            return "Симферополь"
        return None

    @staticmethod
    def _is_broad_store_request(message: str) -> bool:
        text = (message or "").lower()
        return any(
            k in text
            for k in [
                "где у вас магаз",
                "где магаз",
                "какие магаз",
                "в каких город",
                "адреса магаз",
                "покажи магаз",
            ]
        )

    @staticmethod
    def _is_store_intent(message: str) -> bool:
        text = (message or "").lower()
        return any(
            k in text
            for k in [
                "магазин",
                "адрес",
                "как добраться",
                "как найти",
                "на карте",
                "в ялте",
                "в симферополе",
                "где вы находитесь",
                "в каких городах",
            ]
        )

    async def _build_store_stock_context(self, products: List[Product], city: Optional[str]) -> str:
        if not products:
            return "Нет товаров для проверки остатков по магазинам."

        product_ids = [p.id for p in products if p and p.id]
        if not product_ids:
            return "Нет товаров для проверки остатков по магазинам."

        query = (
            select(
                ProductStock.product_id,
                ProductStock.store_id,
                func.sum(ProductStock.available_quantity).label("available_qty"),
                Store.name,
                Store.city,
                Store.address,
            )
            .outerjoin(Store, Store.external_id == ProductStock.store_id)
            .where(ProductStock.product_id.in_(product_ids))
            .group_by(
                ProductStock.product_id,
                ProductStock.store_id,
                Store.name,
                Store.city,
                Store.address,
            )
            .order_by(func.sum(ProductStock.available_quantity).desc())
        )
        if city:
            query = query.where(or_(Store.city.ilike(city), Store.city.is_(None)))

        rows = (await self.db.execute(query)).all()
        if not rows:
            return "Нет данных об остатках по выбранным товарам."

        product_map = {p.id: p for p in products}
        grouped: Dict[UUID, List[Any]] = {}
        for row in rows:
            pid = row.product_id
            grouped.setdefault(pid, []).append(row)

        lines = []
        for pid, stock_rows in grouped.items():
            product = product_map.get(pid)
            if not product:
                continue
            lines.append(f"- {product.name} (арт: {product.article or '—'}, код: {product.external_code or '—'}):")
            for item in stock_rows[:3]:
                store_label = item.name or f"Склад {item.store_id}"
                city_label = item.city or "город не указан"
                addr = f", {item.address}" if item.address else ""
                qty = float(item.available_qty or 0)
                lines.append(f"  {store_label} ({city_label}{addr}) — доступно {qty:.0f}")

        return "\n".join(lines) if lines else "Нет данных об остатках по выбранным товарам."

    @staticmethod
    def _base_article(article: Optional[str]) -> str:
        raw = str(article or "").strip()
        if not raw:
            return ""
        for sep in ("-", "_", " "):
            if sep in raw:
                head = raw.split(sep, 1)[0].strip()
                if head:
                    return head
        return raw

    async def _get_total_stock(self, product_id: UUID) -> float:
        result = await self.db.execute(
            select(func.sum(ProductStock.available_quantity)).where(ProductStock.product_id == product_id)
        )
        return float(result.scalar_one_or_none() or 0)

    def _resolve_look_image_url(self, look: Look) -> Optional[str]:
        image_url = look.image_url
        if isinstance(look.image_urls, list) and look.image_urls:
            idx = look.current_image_index if isinstance(look.current_image_index, int) else 0
            idx = max(0, min(idx, len(look.image_urls) - 1))
            selected = look.image_urls[idx]
            if isinstance(selected, dict):
                image_url = selected.get("url") or image_url
            elif isinstance(selected, str) and selected.strip():
                image_url = selected
        return image_url

    async def _resolve_product_for_display(self, product: Product) -> Product:
        """
        Возвращает лучший вариант товара для отображения в чате:
        с валидной ценой, фото и предпочтительно в наличии.
        """
        stock = await self._get_total_stock(product.id)
        has_image = isinstance(product.images, list) and len(product.images) > 0
        has_price = int(product.price or 0) > 0
        if has_price and has_image and stock > 0:
            return product

        parent_external_id = None
        if isinstance(product.specifications, dict):
            parent_external_id = (
                product.specifications.get("parent_external_id")
                or product.specifications.get("Parent_Key")
                or product.specifications.get("parent_key")
            )
        if not parent_external_id and isinstance(product.sync_metadata, dict):
            parent_external_id = product.sync_metadata.get("parent_external_id")
        if parent_external_id == "00000000-0000-0000-0000-000000000000":
            parent_external_id = None

        article_base = self._base_article(product.article)
        clauses = []
        if parent_external_id:
            clauses.append(Product.external_id == parent_external_id)
            clauses.append(Product.specifications["parent_external_id"].as_string() == str(parent_external_id))
        if article_base:
            clauses.extend(
                [
                    Product.article == article_base,
                    Product.article.ilike(f"{article_base}-%"),
                    Product.article.ilike(f"{article_base}_%"),
                    Product.article.ilike(f"{article_base} %"),
                ]
            )
        if not clauses:
            return product

        result = await self.db.execute(
            select(Product)
            .where(Product.is_active == True, or_(*clauses))
            .limit(30)
        )
        candidates = list(result.scalars().all())
        if not candidates:
            return product

        scored = []
        for candidate in candidates:
            c_stock = await self._get_total_stock(candidate.id)
            c_has_image = int(isinstance(candidate.images, list) and len(candidate.images) > 0)
            c_has_price = int(int(candidate.price or 0) > 0)
            scored.append((c_has_price, int(c_stock > 0), c_has_image, c_stock, int(candidate.price or 0), candidate))
        scored.sort(key=lambda x: (x[0], x[1], x[2], x[3], x[4]), reverse=True)
        return scored[0][5] if scored else product

    async def _to_product_payload(self, product: Product) -> Dict[str, Any]:
        display_product = await self._resolve_product_for_display(product)
        display_stock = await self._get_total_stock(display_product.id)
        return {
            "id": str(display_product.id),
            "name": display_product.name,
            "brand": display_product.brand,
            "price": display_product.price,
            "images": display_product.images if display_product.images is not None else [],
            "category": display_product.category,
            "tags": display_product.tags if display_product.tags is not None else [],
            "stock": display_stock,
            "in_stock": display_stock > 0,
            "article": display_product.article,
            "external_code": display_product.external_code,
            "external_id": display_product.external_id,
        }

    @staticmethod
    def _payload_has_images(payload: Dict[str, Any]) -> bool:
        images = payload.get("images")
        return isinstance(images, list) and len(images) > 0

    @staticmethod
    def _tokenize_name(value: str) -> List[str]:
        raw = re.findall(r"[a-zA-Zа-яА-Я0-9]{2,}", (value or "").lower())
        stop = {
            "кольцо", "серьги", "браслет", "колье", "каффа", "кафф",
            "с", "и", "на", "для", "из", "в", "по",
        }
        return [t for t in raw if t not in stop]

    def _is_payload_mentioned_in_reply(self, reply: str, payload: Dict[str, Any]) -> bool:
        text = (reply or "").lower()
        if not text:
            return False
        name = str(payload.get("name") or "").strip().lower()
        if not name:
            return False
        if name in text:
            return True
        # Мягкий матч: 2+ значимых токена названия есть в тексте ответа.
        name_tokens = self._tokenize_name(name)
        if not name_tokens:
            return False
        hit = sum(1 for t in name_tokens if t in text)
        return hit >= min(2, len(name_tokens))

    async def _find_products_from_reply(self, reply: str, limit: int = 6) -> List[Product]:
        """
        Если LLM упомянула конкретные товары в тексте ответа, пытаемся
        сматчить их с каталогом, чтобы отдать карточки в payload.
        """
        text = (reply or "").strip()
        if not text:
            return []

        # 1) Приоритет: markdown-выделение названий **...**
        names: List[str] = []
        for m in re.findall(r"\*\*([^*\n]{3,120})\*\*", text):
            candidate = re.sub(r"\s*\([^)]*\)\s*$", "", m).strip(" .,:;–-")
            if len(candidate) >= 3:
                names.append(candidate)

        # 2) Fallback: строки перечисления "1. Название ..."
        if not names:
            for m in re.findall(r"(?:^|\n)\s*\d+[.)]\s*([^\n]{3,120})", text):
                candidate = re.split(r"\s+[—-]\s+", m, maxsplit=1)[0].strip(" .,:;–-")
                candidate = re.sub(r"\s*\([^)]*\)\s*$", "", candidate).strip()
                if len(candidate) >= 3:
                    names.append(candidate)

        seen_names = set()
        unique_names = []
        for name in names:
            key = name.lower()
            if key in seen_names:
                continue
            seen_names.add(key)
            unique_names.append(name)
        if not unique_names:
            return []

        found: List[Product] = []
        found_ids = set()
        for name in unique_names[:limit]:
            stmt = (
                select(Product)
                .where(Product.is_active == True, Product.name.ilike(f"%{name}%"))
                .limit(10)
            )
            rows = list((await self.db.execute(stmt)).scalars().all())
            if not rows:
                continue
            scored = []
            normalized = name.lower()
            for p in rows:
                score_exact = int(str(p.name or "").lower() == normalized)
                score_contains = int(normalized in str(p.name or "").lower())
                score_img = int(isinstance(p.images, list) and len(p.images) > 0)
                score_price = int(int(p.price or 0) > 0)
                stock = await self._get_total_stock(p.id)
                score_stock = int(stock > 0)
                scored.append((score_exact, score_contains, score_img, score_price, score_stock, p))
            scored.sort(key=lambda x: (x[0], x[1], x[2], x[3], x[4]), reverse=True)
            best = scored[0][5]
            if best.id not in found_ids:
                found_ids.add(best.id)
                found.append(best)
            if len(found) >= limit:
                break
        return found

    @staticmethod
    def _build_short_history_context(
        conversation_history: Optional[List[Dict[str, Any]]],
        limit: int = 12,
    ) -> str:
        if not conversation_history:
            return "История диалога пуста."
        items = conversation_history[-limit:]
        lines: List[str] = []
        for item in items:
            role = str(item.get("role") or "").lower()
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            prefix = "Покупатель" if role == "user" else "Стилист"
            lines.append(f"- {prefix}: {text[:220]}")
        return "\n".join(lines) if lines else "История диалога пуста."

    @staticmethod
    def _build_long_memory_from_session(session: DBSession) -> str:
        interactions = session.interactions if isinstance(session.interactions, list) else []
        if not interactions:
            return "Долгосрочная память: нет накопленных фактов."

        user_messages: List[str] = []
        for row in interactions[-60:]:
            if not isinstance(row, dict):
                continue
            raw = row.get("message")
            if isinstance(raw, str) and raw.strip():
                user_messages.append(raw.strip())
        if not user_messages:
            return "Долгосрочная память: нет накопленных фактов."

        text = " ".join(user_messages).lower()
        hints = []
        if any(x in text for x in ["романт", "свидан", "нежн"]):
            hints.append("Предпочтение: романтичные/нежные образы.")
        if any(x in text for x in ["минимал", "лаконич"]):
            hints.append("Предпочтение: минимализм.")
        if any(x in text for x in ["серебр", "серебро"]):
            hints.append("Материал: интерес к серебру.")
        if any(x in text for x in ["золото", "золот"]):
            hints.append("Материал: интерес к золоту.")
        if any(x in text for x in ["бюджет", "недорог", "дешев"]):
            hints.append("Чувствительность к бюджету.")
        if any(x in text for x in ["налич", "в наличии"]):
            hints.append("Важно наличие в магазине/на складе.")
        if any(x in text for x in ["примерк", "помер"]):
            hints.append("Интерес к примерке.")
        if any(x in text for x in ["корзин", "оформ", "купить"]):
            hints.append("Готовность к покупке/добавлению в корзину.")
        if not hints:
            return "Долгосрочная память: есть общая история запросов по подбору украшений."
        return "Долгосрочная память:\n- " + "\n- ".join(hints[:8])

    @staticmethod
    def _build_memory_summary(
        style_dna: CustomerStyleDNA,
        conversation_history: Optional[List[Dict[str, Any]]],
        user_context: str,
        long_memory_text: str,
    ) -> str:
        """Короткий человечный профиль покупателя для живого продолжения диалога."""
        snippets: List[str] = []

        occasion = str(getattr(style_dna, "occasion", "") or "").strip()
        style = str(getattr(style_dna, "style", "") or "").strip()
        materials = list(getattr(style_dna, "materials", []) or [])
        categories = list(getattr(style_dna, "categories", []) or [])
        brands = list(getattr(style_dna, "brands", []) or [])
        budget_min = getattr(style_dna, "budget_min", None)
        budget_max = getattr(style_dna, "budget_max", None)

        if occasion:
            snippets.append(f"Повод: {occasion}.")
        if style:
            snippets.append(f"Стиль: {style}.")
        if materials:
            snippets.append(f"Материалы: {', '.join(materials[:3])}.")
        if categories:
            snippets.append(f"Категории: {', '.join(categories[:3])}.")
        if brands:
            snippets.append(f"Брендовые сигналы: {', '.join(brands[:3])}.")
        if budget_min or budget_max:
            if budget_min and budget_max:
                snippets.append(f"Бюджетный ориентир: {int(budget_min)}-{int(budget_max)} руб.")
            elif budget_min:
                snippets.append(f"Бюджетный ориентир: от {int(budget_min)} руб.")
            else:
                snippets.append(f"Бюджетный ориентир: до {int(budget_max)} руб.")

        source = f"{user_context}\n{long_memory_text}".lower()
        if "чувствительность к бюджету" in source and not (budget_min or budget_max):
            snippets.append("Покупатель внимательно относится к бюджету.")
        if "важно наличие" in source:
            snippets.append("Приоритет: реальные остатки и наличие.")
        if "интерес к примерке" in source:
            snippets.append("Есть интерес к примерке перед покупкой.")
        if "готовность к покупке" in source:
            snippets.append("Сигнал готовности к покупке уже проявлялся.")

        if conversation_history:
            last_user = ""
            for item in reversed(conversation_history[-8:]):
                if str(item.get("role") or "").lower() == "user":
                    last_user = str(item.get("text") or "").strip()
                    if last_user:
                        break
            if last_user:
                snippets.append(f"Текущий фокус запроса: {last_user[:120]}.")

        if not snippets:
            return (
                "Профиль покупателя: данных пока мало; общайтесь нейтрально и тепло, "
                "соберите 1 ключевую потребность и продолжайте без шаблонов."
            )
        return "Профиль покупателя:\n- " + "\n- ".join(snippets[:8])

    @staticmethod
    def _normalize_reply_length(reply: str, max_chars: int = 1100, max_paragraphs: int = 5) -> str:
        text = (reply or "").strip()
        if not text:
            return text
        parts = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
        if len(parts) > max_paragraphs:
            parts = parts[:max_paragraphs]
        compact = "\n\n".join(parts).strip()
        if len(compact) <= max_chars:
            return compact
        return compact[: max_chars - 1].rstrip() + "…"

    @staticmethod
    def _enforce_compact_dialogue(
        reply: str,
        max_sentences: int = 3,
        max_questions: int = 1,
    ) -> str:
        text = (reply or "").strip()
        if not text:
            return text

        text = re.sub(r"\n{3,}", "\n\n", text)
        raw_sentences = re.split(r"(?<=[.!?])\s+", text)
        sentences = [s.strip() for s in raw_sentences if s and s.strip()]
        if not sentences:
            return text

        compact: List[str] = []
        question_count = 0
        for sentence in sentences:
            is_question = "?" in sentence
            if is_question and question_count >= max_questions:
                # второй и последующие вопросы превращаем в CTA-утверждение
                sentence = re.sub(r"\?+\s*$", ".", sentence).strip()
                sentence = re.sub(r"^(Хочешь|Хотите|Могу|Давай)\b", "Могу", sentence, flags=re.IGNORECASE)
                is_question = False
            if is_question:
                question_count += 1
            compact.append(sentence)
            if len(compact) >= max_sentences:
                break

        result = " ".join(compact).strip()
        # Удаляем маркеры длинных секций, чтобы не тащить структуру "статьи"
        result = re.sub(r"#{1,6}\s*", "", result)
        result = re.sub(r"\s{2,}", " ", result).strip()
        return result

    @staticmethod
    def _enforce_formal_address(reply: str) -> str:
        text = (reply or "").strip()
        if not text:
            return text

        def repl(match: re.Match, lower_form: str, upper_form: str) -> str:
            token = match.group(0)
            return upper_form if token and token[0].isupper() else lower_form

        replacements = [
            (r"\bты\b", "вы", "Вы"),
            (r"\bтебе\b", "вам", "Вам"),
            (r"\bтебя\b", "вас", "Вас"),
            (r"\bтобой\b", "вами", "Вами"),
            (r"\bтвой\b", "ваш", "Ваш"),
            (r"\bтвоя\b", "ваша", "Ваша"),
            (r"\bтвоё\b", "ваше", "Ваше"),
            (r"\bтвое\b", "ваше", "Ваше"),
            (r"\bтвои\b", "ваши", "Ваши"),
            (r"\bтвоем\b", "вашем", "Вашем"),
            (r"\bтвоём\b", "вашем", "Вашем"),
            (r"\bтвоей\b", "вашей", "Вашей"),
            (r"\bтвою\b", "вашу", "Вашу"),
            (r"\bхочешь\b", "хотите", "Хотите"),
            (r"\bподскажи\b", "подскажите", "Подскажите"),
            (r"\bрасскажи\b", "расскажите", "Расскажите"),
        ]
        for pattern, lower_form, upper_form in replacements:
            text = re.sub(
                pattern,
                lambda m, lo=lower_form, up=upper_form: repl(m, lo, up),
                text,
                flags=re.IGNORECASE,
            )
        return text

    @staticmethod
    def _strip_template_openers(reply: str) -> str:
        text = (reply or "").strip()
        if not text:
            return text
        patterns = [
            r"^ой,\s*понимаю\s+ваш\s+(?:вопрос|запрос)!?\s*(?:[^\w\s]+)?\s*",
            r"^понимаю\s+ваш\s+(?:вопрос|запрос)!?\s*(?:[^\w\s]+)?\s*",
        ]
        out = text
        for pattern in patterns:
            out = re.sub(pattern, "", out, flags=re.IGNORECASE).strip()
        if not out:
            return text
        return out

    @staticmethod
    def _first_sentence(text: str) -> str:
        value = (text or "").strip()
        if not value:
            return ""
        parts = re.split(r"(?<=[.!?])\s+", value, maxsplit=1)
        first = parts[0].strip()
        if len(first) > 220:
            first = first[:219].rstrip() + "…"
        return first

    @staticmethod
    def _strip_leading_greeting(text: str) -> str:
        value = (text or "").strip()
        if not value:
            return value
        # Убираем стартовое приветствие, чтобы не "перезапускать" диалог.
        patterns = [
            r"^(привет[!,.:\s-]*)",
            r"^(здравствуй(?:те)?[!,.:\s-]*)",
            r"^(добрый\s+(?:день|вечер|утро)[!,.:\s-]*)",
            r"^(рада\s+вас\s+видеть[!,.:\s-]*)",
        ]
        out = value
        for p in patterns:
            out = re.sub(p, "", out, flags=re.IGNORECASE).strip()
        return out or value

    @staticmethod
    def _build_style_dna_snapshot(
        message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        known_signals: Optional[Dict[str, bool]] = None,
    ) -> Dict[str, bool]:
        """
        Легкий state для discovery-этапа:
        - occasion: повод/контекст использования
        - style: стилевое направление
        - budget: бюджет/ценовой коридор
        - preferences: материал/категория/брендовые предпочтения
        """
        text_parts: List[str] = [str(message or "")]
        if conversation_history:
            for row in conversation_history[-20:]:
                if not isinstance(row, dict):
                    continue
                if str(row.get("role") or "").lower() != "user":
                    continue
                user_text = str(row.get("text") or "").strip()
                if user_text:
                    text_parts.append(user_text)
        text = " ".join(text_parts).lower()

        occasion = any(
            x in text
            for x in [
                "на свидан", "на вечер", "на свадьб", "на работу", "в офис",
                "на каждый день", "повседнев", "на праздник", "на мероприят",
                "выпускн", "prom",
            ]
        )
        style = any(
            x in text
            for x in [
                "минимал", "классик", "романт", "бохо", "casual", "элегант",
                "акцент", "смел", "нежн", "строг",
            ]
        )
        budget = bool(re.search(r"\b\d{3,}\b", text)) or any(
            x in text for x in ["бюджет", "до ", "от ", "дороже", "дешевле", "недорог"]
        )
        preferences = any(
            x in text
            for x in [
                "серебр", "золото", "жемчуг", "камн", "кольц", "серьг",
                "колье", "браслет", "кафф", "бренд", "коллекц",
            ]
        )
        snapshot = {
            "occasion": occasion,
            "style": style,
            "budget": budget,
            "preferences": preferences,
        }
        if known_signals:
            for key in ["occasion", "style", "budget", "preferences"]:
                if known_signals.get(key):
                    snapshot[key] = True
        return snapshot

    @staticmethod
    def _latest_sales_state(session: DBSession) -> Dict[str, Any]:
        interactions = session.interactions if isinstance(session.interactions, list) else []
        for row in reversed(interactions[-80:]):
            if not isinstance(row, dict):
                continue
            sales_state = row.get("sales_state")
            if isinstance(sales_state, dict):
                return sales_state
        return {}

    @staticmethod
    def _merge_unique(left: Optional[List[str]], right: Optional[List[str]], limit: int = 8) -> List[str]:
        result: List[str] = []
        for value in (left or []) + (right or []):
            text = str(value or "").strip().lower()
            if text and text not in result:
                result.append(text)
            if len(result) >= limit:
                break
        return result

    @staticmethod
    def _extract_budget_range(text: str) -> Tuple[Optional[int], Optional[int]]:
        clean = (text or "").lower().replace(" ", "")
        range_match = re.search(r"(?:от)?(\d{3,6})(?:₽|р|руб)?(?:до|-|–)(\d{3,6})(?:₽|р|руб)?", clean)
        if range_match:
            first = int(range_match.group(1))
            second = int(range_match.group(2))
            return (min(first, second), max(first, second))

        upto_match = re.search(r"(?:до|небольше|максимум|max)(\d{3,6})(?:₽|р|руб)?", clean)
        if upto_match:
            return (None, int(upto_match.group(1)))

        from_match = re.search(r"(?:от|минимум|min)(\d{3,6})(?:₽|р|руб)?", clean)
        if from_match:
            return (int(from_match.group(1)), None)

        numbers = [int(x) for x in re.findall(r"\b\d{4,6}\b", text or "")]
        if numbers:
            value = numbers[0]
            return (max(0, int(value * 0.8)), int(value * 1.2))
        return (None, None)

    @staticmethod
    def _extract_freeform_occasion(message: str) -> Optional[str]:
        text = re.sub(r"\s+", " ", str(message or "").strip()).strip(" .,!?:;")
        if not text:
            return None
        lower = text.lower()
        if "?" in text:
            return None

        pattern_checks = [
            r"(?:на|для|под)\s+([а-яёa-z0-9][а-яёa-z0-9\s-]{2,40})",
            r"(?:к|ко)\s+([а-яёa-z0-9][а-яёa-z0-9\s-]{2,40})",
        ]
        generic_object_words = {
            "украшения", "украшение", "серьги", "кольцо", "кольца", "колье",
            "браслет", "кафф", "пусеты", "цепочка", "подвеска", "коробка",
            "покрытие", "цена", "стоимость", "товар", "товары",
        }
        for pattern in pattern_checks:
            match = re.search(pattern, lower, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip(" .,!?:;")
                if value and not any(word in value.split() for word in generic_object_words):
                    return value

        short_text = lower.strip()
        words = [w for w in re.split(r"\s+", short_text) if w]
        banned_starts = {
            "помоги", "помочь", "покажи", "подбери", "посоветуй", "расскажи",
            "какой", "какая", "какие", "сколько", "зачем", "почему", "что",
            "где", "есть", "нужно", "хочу", "ищу", "да", "нет",
        }
        if (
            1 <= len(words) <= 4
            and words[0] not in banned_starts
            and not re.search(r"\b\d{3,}\b", short_text)
            and not any(x in short_text for x in ["серебр", "золот", "жемчуг", "кольц", "серьг", "браслет", "колье"])
        ):
            return short_text
        return None

    @staticmethod
    def _extract_style_dna_profile(
        message: str,
        conversation_history: Optional[List[Dict[str, Any]]],
        previous_style_dna: Optional[Dict[str, Any]],
        known_signals: Optional[Dict[str, bool]] = None,
    ) -> CustomerStyleDNA:
        text_parts: List[str] = []
        if conversation_history:
            for row in conversation_history[-30:]:
                if not isinstance(row, dict):
                    continue
                if str(row.get("role") or "").lower() != "user":
                    continue
                user_text = str(row.get("text") or "").strip()
                if user_text:
                    text_parts.append(user_text)
        if message:
            text_parts.append(message)
        corpus = " ".join(text_parts).lower()
        previous = previous_style_dna if isinstance(previous_style_dna, dict) else {}

        occasion_map = {
            "свидание": ["свидан", "романтичный вечер"],
            "вечер": ["на вечер", "ужин", "вечерин", "торжеств"],
            "работа": ["работ", "офис", "делов"],
            "свадьба": ["свадьб"],
            "выпускной": ["выпускн", "prom", "prom night"],
            "каждый день": ["каждый день", "повседнев"],
            "подарок": ["подар", "дарить", "маме", "подруге", "жене", "девушке"],
        }
        style_map = {
            "минимализм": ["минимал", "лаконич"],
            "классика": ["классик", "базов"],
            "романтика": ["романт", "нежн"],
            "акцентный": ["акцент", "ярк", "смел", "заметн"],
            "деловой": ["строг", "делов", "офис"],
            "casual": ["casual", "кэжуал", "повседнев"],
        }
        materials_map = {
            "серебро": ["серебр"],
            "золото": ["золот"],
            "жемчуг": ["жемчуг"],
            "камни": ["камн", "фианит", "кристалл"],
        }
        category_map = {
            "кольцо": ["кольц"],
            "серьги": ["серьг", "пусет", "кафф"],
            "колье": ["колье", "цепоч", "подвес"],
            "браслет": ["браслет"],
        }
        brand_map = {
            "antura": ["antura", "антура"],
            "uno de 50": ["uno de 50", "uno", "уно"],
            "glame": ["glame", "глэйм", "глам"],
        }

        def first_match(mapping: Dict[str, List[str]]) -> Optional[str]:
            for label, needles in mapping.items():
                if any(needle in corpus for needle in needles):
                    return label
            return None

        def all_matches(mapping: Dict[str, List[str]]) -> List[str]:
            return [
                label
                for label, needles in mapping.items()
                if any(needle in corpus for needle in needles)
            ]

        budget_min, budget_max = StylistAgent._extract_budget_range(corpus)
        occasion_candidate = StylistAgent._extract_freeform_occasion(message)
        dislikes = []
        for match in re.findall(r"(?:не люблю|не хочу|без)\s+([а-яёa-z0-9\s-]{3,40})", corpus, flags=re.IGNORECASE):
            value = match.strip(" .,!?:;").lower()
            if value:
                dislikes.append(value)

        dna = CustomerStyleDNA(
            occasion=occasion_candidate or first_match(occasion_map) or previous.get("occasion"),
            style=first_match(style_map) or previous.get("style"),
            budget_min=budget_min if budget_min is not None else previous.get("budget_min"),
            budget_max=budget_max if budget_max is not None else previous.get("budget_max"),
            materials=StylistAgent._merge_unique(previous.get("materials"), all_matches(materials_map)),
            categories=StylistAgent._merge_unique(previous.get("categories"), all_matches(category_map)),
            brands=StylistAgent._merge_unique(previous.get("brands"), all_matches(brand_map)),
            dislikes=StylistAgent._merge_unique(previous.get("dislikes"), dislikes),
        )

        known = known_signals or {}
        if known.get("budget") and dna.budget_min is None and dna.budget_max is None:
            dna.budget_min = previous.get("budget_min")
            dna.budget_max = previous.get("budget_max")
        if known.get("preferences") and not (dna.materials or dna.categories or dna.brands):
            dna.categories = StylistAgent._merge_unique(previous.get("categories"), ["любимые категории из истории"])
        if known.get("style") and not dna.style:
            dna.style = previous.get("style") or "по сохраненным образам"
        return dna

    @staticmethod
    def _style_dna_presence(style_dna: CustomerStyleDNA) -> Dict[str, bool]:
        return {
            "occasion": bool(style_dna.occasion),
            "style": bool(style_dna.style),
            "budget": style_dna.budget_min is not None or style_dna.budget_max is not None,
            "preferences": bool(style_dna.materials or style_dna.categories or style_dna.brands),
        }

    @staticmethod
    def _format_style_dna_for_prompt(style_dna: CustomerStyleDNA) -> str:
        data = style_dna.to_dict()
        lines = []
        for key, label in [
            ("occasion", "Повод"),
            ("style", "Стиль"),
            ("budget_min", "Бюджет от"),
            ("budget_max", "Бюджет до"),
            ("materials", "Материалы"),
            ("categories", "Категории"),
            ("brands", "Бренды"),
            ("dislikes", "Не нравится"),
        ]:
            value = data.get(key)
            if isinstance(value, list):
                value = ", ".join(value)
            if value:
                lines.append(f"- {label}: {value}")
        return "\n".join(lines) if lines else "- Пока нет устойчивых вводных."

    @staticmethod
    def _is_style_dna_ready(snapshot: Dict[str, bool]) -> bool:
        # Достаточно 2+ базовых сигналов, чтобы переходить к осмысленному подбору.
        return sum(1 for v in snapshot.values() if bool(v)) >= 2

    @staticmethod
    def _next_discovery_question(snapshot: Dict[str, bool]) -> str:
        if not snapshot.get("occasion"):
            return "Подскажите, под какой повод подбираем украшение?"
        if not snapshot.get("style"):
            return "Какой стиль вам ближе: минимализм, классика, романтика или акцентный вариант?"
        if not snapshot.get("budget"):
            return "Какой ориентир по бюджету комфортен?"
        if not snapshot.get("preferences"):
            return "Есть предпочтения по металлу или формату: кольцо, серьги, колье, браслет?"
        return ""

    @staticmethod
    def _detect_sales_objection(message: str, conversation_history: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
        parts = [str(message or "")]
        if conversation_history:
            for row in conversation_history[-8:]:
                if not isinstance(row, dict):
                    continue
                if str(row.get("role") or "").lower() == "user":
                    text = str(row.get("text") or "").strip()
                    if text:
                        parts.append(text)
        text = " ".join(parts).lower()
        checks = [
            ("price", ["дорого", "дороговато", "дешевле", "бюджет", "цена кус", "не потяну"]),
            ("fit", ["подойдет", "подойдёт", "сомневаюсь", "не увер", "будет ли", "сочета"]),
            ("gift", ["подарок", "не знаю размер", "что подарить", "ей понрав"]),
            ("availability", ["в наличии", "есть ли", "наличие", "забрать", "магазин"]),
            ("delivery", ["доставк", "пвз", "сдэк", "cdek", "самовывоз"]),
            ("choice", ["не могу выбрать", "что лучше", "какой лучше", "слишком много"]),
        ]
        for label, needles in checks:
            if any(needle in text for needle in needles):
                return label
        return None

    @staticmethod
    def _build_sales_goal_state(
        message: str,
        conversation_history: Optional[List[Dict[str, Any]]],
        style_dna_snapshot: Dict[str, bool],
        include_products: bool,
        include_looks: bool,
    ) -> Dict[str, bool]:
        user_texts: List[str] = [str(message or "")]
        if conversation_history:
            for row in conversation_history[-40:]:
                if not isinstance(row, dict):
                    continue
                if str(row.get("role") or "").lower() != "user":
                    continue
                txt = str(row.get("text") or "").strip()
                if txt:
                    user_texts.append(txt)
        corpus = " ".join(user_texts).lower()

        rapport = len(user_texts) >= 2
        needs = StylistAgent._is_style_dna_ready(style_dna_snapshot)
        presentation = include_products or include_looks or any(
            x in corpus for x in ["покажи", "вариант", "сравн", "подбери", "подбор"]
        )
        close = any(
            x in corpus for x in ["купить", "оформ", "корзин", "доставк", "оплат", "беру", "заказ"]
        )
        return {
            "rapport": rapport,
            "needs": needs,
            "presentation": presentation,
            "close": close,
        }

    @staticmethod
    def _resolve_sales_stage(
        detected_stage: str,
        previous_stage: Optional[str],
        info_intent: bool,
        goal_state: Dict[str, bool],
        is_affirmative: bool,
    ) -> str:
        if info_intent:
            return previous_stage or (detected_stage if detected_stage in StylistAgent.CJM_STAGES else "inspiration")

        # Не откатываемся назад после явной готовности к покупке.
        if previous_stage == "purchase":
            return "purchase"
        if goal_state.get("close"):
            return "purchase"
        if goal_state.get("presentation"):
            return "consideration"

        if previous_stage == "consideration":
            return "consideration"
        if goal_state.get("needs") and is_affirmative:
            return "consideration"
        return "inspiration"

    @staticmethod
    def _next_sales_action(stage: str, style_dna_question: str, info_intent: bool) -> str:
        if info_intent:
            return "Дай точный ответ на текущий вопрос и мягко уточни, продолжать ли к подбору."
        if stage == "inspiration":
            return f"Выяви одну потребность и задай 1 уточняющий вопрос: {style_dna_question or 'какой повод/бюджет/стиль приоритетнее?'}"
        if stage == "consideration":
            return "Покажи решение: 1-2 релевантных варианта и коротко объясни разницу."
        return "Переведи к покупке: предложи конкретный следующий шаг (корзина/оплата/доставка)."

    @staticmethod
    def _build_sales_decision(
        stage: str,
        style_dna_question: str,
        info_intent: bool,
        objection: Optional[str],
        include_products: bool,
        include_looks: bool,
        is_affirmative: bool,
    ) -> SalesDecision:
        if info_intent:
            return SalesDecision(
                stage=stage,
                next_action="Ответь фактами и предложи перейти к подбору только мягко.",
                cta_type="continue_to_selection",
                should_show_products=False,
                should_show_looks=False,
                objection=objection,
            )

        if objection:
            objection_actions = {
                "price": "Сними ценовое возражение: предложи более комфортную альтернативу и объясни ценность без давления.",
                "fit": "Сними сомнение по сочетанию: объясни, с чем носить, и предложи безопасную альтернативу.",
                "gift": "Помоги выбрать подарок: уточни получателя или предложи универсальный вариант.",
                "availability": "Ответь по наличию и предложи ближайший следующий шаг.",
                "delivery": "Объясни самовывоз/доставку и предложи оформить удобный вариант.",
                "choice": "Сузь выбор до 2 вариантов и дай критерий выбора.",
            }
            return SalesDecision(
                stage="consideration" if stage != "purchase" else stage,
                next_action=objection_actions.get(objection, "Сними возражение и верни к следующему шагу покупки."),
                cta_type="handle_objection",
                should_show_products=include_products,
                should_show_looks=include_looks,
                objection=objection,
            )

        if stage == "purchase":
            return SalesDecision(
                stage=stage,
                next_action="Закрой на действие: подтвердить добавление в корзину или перейти к оформлению.",
                cta_type="add_to_cart_confirm" if include_products else "checkout_or_visit",
                should_show_products=include_products,
                should_show_looks=include_looks,
                objection=None,
            )

        if stage == "consideration":
            return SalesDecision(
                stage=stage,
                next_action="Покажи 1-2 варианта, коротко сравни и предложи выбрать.",
                cta_type="compare_products" if include_products else "show_looks",
                should_show_products=include_products,
                should_show_looks=include_looks,
                objection=None,
            )

        if is_affirmative and not style_dna_question:
            next_action = "Перейди к подбору и покажи 2 релевантных варианта."
            cta_type = "show_products"
        else:
            next_action = f"Выяви одну потребность и задай 1 вопрос: {style_dna_question or 'какой повод/стиль/бюджет важнее?'}"
            cta_type = "ask_discovery_question"
        return SalesDecision(
            stage=stage,
            next_action=next_action,
            cta_type=cta_type,
            should_show_products=include_products,
            should_show_looks=include_looks,
            objection=None,
        )

    @staticmethod
    def _is_affirmative_message(message: str) -> bool:
        text = (message or "").strip().lower()
        if not text:
            return False
        compact = re.sub(r"[^\wа-яё]+", " ", text, flags=re.IGNORECASE).strip()
        short_yes = {
            "да", "хочу", "давай", "давайте", "ок", "оке", "ага",
            "интересно", "подходит", "поехали", "конечно",
        }
        if compact in short_yes:
            return True
        # короткое подтверждение в 1-3 слова
        words = [w for w in compact.split() if w]
        return len(words) <= 3 and any(w in short_yes for w in words)

    @staticmethod
    def _last_assistant_text(conversation_history: Optional[List[Dict[str, Any]]]) -> str:
        if not conversation_history:
            return ""
        for row in reversed(conversation_history[-20:]):
            if not isinstance(row, dict):
                continue
            if str(row.get("role") or "").lower() != "assistant":
                continue
            text = str(row.get("text") or "").strip()
            if text:
                return text
        return ""

    @staticmethod
    def _last_user_text(conversation_history: Optional[List[Dict[str, Any]]]) -> str:
        if not conversation_history:
            return ""
        for row in reversed(conversation_history[-20:]):
            if not isinstance(row, dict):
                continue
            if str(row.get("role") or "").lower() != "user":
                continue
            text = str(row.get("text") or "").strip()
            if text:
                return text
        return ""

    @staticmethod
    def _is_redundant_reply(reply: str, previous_assistant_text: str) -> bool:
        a = re.sub(r"[^\wа-яё]+", " ", (reply or "").lower(), flags=re.IGNORECASE).strip()
        b = re.sub(r"[^\wа-яё]+", " ", (previous_assistant_text or "").lower(), flags=re.IGNORECASE).strip()
        if not a or not b:
            return False
        if a == b:
            return True
        # если почти тот же CTA без новой информации
        common_phrases = [
            "подберу варианты по стилю и бюджету",
            "в следующем шаге подберу варианты",
            "если хотите в следующем шаге",
        ]
        return any(p in a and p in b for p in common_phrases)

    @staticmethod
    def _classify_llm_error(error: Exception) -> str:
        text = str(error or "").lower()
        if any(x in text for x in ["timeout", "timed out", "deadline", "read timed out"]):
            return "timeout"
        if any(x in text for x in ["401", "403", "unauthorized", "forbidden", "api key", "invalid key"]):
            return "auth"
        if any(x in text for x in ["429", "rate limit", "too many requests", "quota"]):
            return "rate_limit"
        if any(x in text for x in ["connection", "network", "dns", "ssl", "name or service not known"]):
            return "network"
        if any(x in text for x in ["openrouter", "provider", "model", "bad gateway", "502", "503"]):
            return "provider"
        return "unknown"

    @staticmethod
    def _extract_info_facts(context: List[Dict[str, Any]], max_facts: int = 2) -> List[str]:
        facts: List[str] = []
        for item in context:
            if not isinstance(item, dict):
                continue
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            text = str(payload.get("text") or "").strip()
            if not text:
                continue
            sentence = re.split(r"(?<=[.!?])\s+", text)[0].strip()
            if not sentence:
                continue
            if len(sentence) > 180:
                sentence = sentence[:179].rstrip() + "…"
            if sentence not in facts:
                facts.append(sentence)
            if len(facts) >= max_facts:
                break
        return facts

    @staticmethod
    def _inject_facts_into_info_reply(reply: str, facts: List[str]) -> str:
        clean = (reply or "").strip()
        if not facts:
            return clean
        if not clean:
            return " ".join(facts)
        # Если факты уже отражены в тексте, не дублируем.
        lower = clean.lower()
        missing = [f for f in facts if f.lower() not in lower]
        if not missing:
            return clean
        return f"{clean} По базе знаний: {' '.join(missing[:2])}"

    def _apply_cjm_turn_template(
        self,
        reply: str,
        cjm_stage: str,
        products: List[Product],
        looks: List[Look],
        city: Optional[str],
        include_products: bool,
        include_looks: bool,
        info_intent: bool,
        style_dna_ready: bool,
        style_dna_question: str,
        greeted_before: bool,
        objection: Optional[str] = None,
        cta_type: Optional[str] = None,
    ) -> str:
        clean = (reply or "").strip()
        if clean:
            if greeted_before:
                clean = self._strip_leading_greeting(clean)
            return clean
        if info_intent:
            return "Сейчас у меня нет подтвержденного ответа по этому вопросу. Могу уточнить и вернуться с точной информацией."
        if not style_dna_ready and style_dna_question:
            return f"Чтобы не гадать, уточню один момент: {style_dna_question}"
        if objection == "price":
            return "Могу подобрать вариант мягче по бюджету и сохранить настроение образа. Показать такую альтернативу?"
        if objection == "fit":
            return "Могу предложить более спокойный вариант, который проще впишется в образ. Показать для сравнения?"
        if objection == "choice":
            return "Давайте сузим выбор до двух близких вариантов и я коротко объясню разницу."
        return "Я рядом и помогу шаг за шагом. Скажите, что для вас сейчас важнее всего в выборе."
    
    async def process(
        self,
        user_id: Optional[UUID],
        message: str,
        city: Optional[str] = None,
        session_id: Optional[UUID] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Основная логика обработки запроса"""
        
        # Загружаем данные пользователя для персонализации
        user_context = ""
        known_customer_signals: Dict[str, bool] = {
            "occasion": False,
            "style": False,
            "budget": False,
            "preferences": False,
        }
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
                favorite_categories: List[str] = []
                favorite_brands: List[str] = []
                
                # Формируем контекст для персонализации
                if user.purchase_preferences:
                    favorite_categories = user.purchase_preferences.get("favorite_categories", [])
                    favorite_brands = user.purchase_preferences.get("favorite_brands", [])
                    if favorite_categories or favorite_brands:
                        known_customer_signals["preferences"] = True
                if (user.average_check or 0) > 0:
                    known_customer_signals["budget"] = True

                recent_purchase_lines = []
                for purchase in list(purchases)[:5]:
                    product_name = getattr(purchase, "product_name", None) or getattr(purchase, "name", None)
                    amount = getattr(purchase, "amount", None) or getattr(purchase, "total_amount", None)
                    if product_name:
                        recent_purchase_lines.append(f"- {product_name}{f' ({amount} руб.)' if amount else ''}")

                user_context = f"""
История покупок покупателя:
- Любимые категории: {', '.join(favorite_categories) if favorite_categories else 'не определены'}
- Любимые бренды: {', '.join(favorite_brands) if favorite_brands else 'не определены'}
- Средний чек: {user.average_check / 100 if user.average_check else 0} руб
- Всего покупок: {user.total_purchases}
- Последняя покупка: {user.last_purchase_date.strftime('%d.%m.%Y') if user.last_purchase_date else 'нет данных'}
{chr(10).join(recent_purchase_lines) if recent_purchase_lines else '- Последние товары: нет данных'}

Учитывай предпочтения покупателя при рекомендациях. Рекомендуй товары в диапазоне среднего чека ±30%.
"""

                saved_looks_result = await self.db.execute(
                    select(SavedLook, Look)
                    .join(Look, SavedLook.look_id == Look.id)
                    .where(SavedLook.user_id == user_id)
                    .order_by(SavedLook.created_at.desc())
                    .limit(6)
                )
                saved_looks_rows = saved_looks_result.all()
                if saved_looks_rows:
                    known_customer_signals["style"] = True
                    saved_lines = []
                    for saved_look, look in saved_looks_rows:
                        saved_lines.append(
                            f"- {look.name} | стиль: {look.style or 'не указан'} | настроение: {look.mood or 'не указано'}"
                        )
                    user_context += (
                        "\nСохраненные образы покупателя (используй как сильный сигнал вкуса):\n"
                        + "\n".join(saved_lines)
                        + "\nЕсли покупатель сомневается, опирайся на эти сохраненные образы при подборе."
                    )
        
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
        
        previous_sales_state = self._latest_sales_state(session)
        previous_style_dna = previous_sales_state.get("style_dna") if isinstance(previous_sales_state, dict) else {}
        style_dna = self._extract_style_dna_profile(
            message=message,
            conversation_history=conversation_history,
            previous_style_dna=previous_style_dna,
            known_signals=known_customer_signals,
        )
        # Определяем персону и CJM этап
        persona = await self.detect_persona(
            message,
            session.interactions if session.interactions else [],
            user_id=user_id
        )
        cjm_stage = await self.detect_cjm_stage(message, session.interactions if session.interactions else [])
        previous_stage = None
        if isinstance(session.interactions, list):
            for row in reversed(session.interactions[-30:]):
                if isinstance(row, dict) and row.get("cjm_stage") in self.CJM_STAGES:
                    previous_stage = row.get("cjm_stage")
                    break
        style_dna_snapshot = self._style_dna_presence(style_dna)
        style_dna_ready = self._is_style_dna_ready(style_dna_snapshot)
        style_dna_question = self._next_discovery_question(style_dna_snapshot)
        is_affirmative = self._is_affirmative_message(message)
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
        short_history_text = self._build_short_history_context(conversation_history, limit=20)
        long_memory_text = self._build_long_memory_from_session(session)
        greeted_before = False
        if conversation_history:
            greeted_before = any(
                str(x.get("role") or "").lower() == "assistant"
                and any(w in str(x.get("text") or "").lower() for w in ["привет", "здравств", "рада приветствовать"])
                for x in conversation_history[-20:]
                if isinstance(x, dict)
            )
        
        previous_user_text = self._last_user_text(conversation_history)
        contextual_message = message
        followup_info_intent = False
        if is_affirmative and previous_user_text:
            # Короткие ответы "хочу/да" должны наследовать контекст предыдущего вопроса.
            if self._is_brand_info_intent(previous_user_text):
                followup_info_intent = True
                contextual_message = f"{previous_user_text}. {message}"

        # Получаем контекст бренда из базы знаний
        import logging
        logger = logging.getLogger(__name__)
        
        # Извлекаем название коллекции из сообщения для более точного поиска
        collection_name = self._extract_collection_name(contextual_message)
        
        # Ищем в нескольких коллекциях: brand_philosophy и collections_info
        brand_context = await self.get_brand_context(contextual_message, limit=3)
        
        # Для поиска коллекций используем более специфичный запрос
        collections_query = collection_name if collection_name else contextual_message
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
            f"всего {len(all_context)} уникальных для запроса: '{contextual_message[:50]}...'"
        )
        
        # Используем объединенный контекст
        brand_context = all_context
        info_facts = self._extract_info_facts(brand_context, max_facts=2)
        
        # Определяем, нужно ли в текущем ответе показывать карточки образов/товаров.
        info_intent = self._is_brand_info_intent(contextual_message) or followup_info_intent
        include_looks = self._is_look_intent(contextual_message, conversation_history)
        include_products = self._is_product_offer_intent(contextual_message)
        objection = self._detect_sales_objection(contextual_message, conversation_history)
        goal_state = self._build_sales_goal_state(
            message=contextual_message,
            conversation_history=conversation_history,
            style_dna_snapshot=style_dna_snapshot,
            include_products=include_products,
            include_looks=include_looks,
        )
        cjm_stage = self._resolve_sales_stage(
            detected_stage=cjm_stage,
            previous_stage=previous_stage,
            info_intent=info_intent,
            goal_state=goal_state,
            is_affirmative=is_affirmative,
        )
        sales_next_action = self._next_sales_action(
            stage=cjm_stage,
            style_dna_question=style_dna_question,
            info_intent=info_intent,
        )
        session.cjm_stage = cjm_stage
        if isinstance(session.interactions, list) and session.interactions:
            if isinstance(session.interactions[-1], dict):
                session.interactions[-1]["cjm_stage"] = cjm_stage
        # Для вопросов о бренде/коллекциях не показываем карточки, если нет явного запроса на подбор.
        if info_intent and not include_looks and not include_products:
            include_looks = False
            include_products = False
        interactive = await self._build_interactive_entities(contextual_message)

        # Подбираем товары и образы с учетом контекста
        tags = self._extract_tags_from_message(contextual_message)
        allow_nomenclature_lookup = include_products or include_looks
        nomenclature_products = (
            await self._find_nomenclature_products(contextual_message, limit=6)
            if allow_nomenclature_lookup
            else []
        )
        include_products = include_products or bool(nomenclature_products) or include_looks
        # Жесткое правило: для чисто инфо-вопросов не показываем товарные карточки.
        if info_intent and not self._is_product_offer_intent(contextual_message) and not include_looks:
            nomenclature_products = []
            include_products = False

        sales_decision = self._build_sales_decision(
            stage=cjm_stage,
            style_dna_question=style_dna_question,
            info_intent=info_intent,
            objection=objection,
            include_products=include_products,
            include_looks=include_looks,
            is_affirmative=is_affirmative,
        )
        cjm_stage = sales_decision.stage
        sales_next_action = sales_decision.next_action
        include_products = sales_decision.should_show_products
        include_looks = sales_decision.should_show_looks
        # На этапе подбора карточки должны идти сразу в этом же сообщении.
        if cjm_stage == "consideration" and not info_intent:
            include_products = True
        session.cjm_stage = cjm_stage
        if isinstance(session.interactions, list) and session.interactions:
            if isinstance(session.interactions[-1], dict):
                session.interactions[-1]["cjm_stage"] = cjm_stage
                session.interactions[-1]["sales_state"] = {
                    "style_dna": style_dna.to_dict(),
                    "sales_decision": sales_decision.to_dict(),
                }

        products: List[Product] = []
        if include_products:
            # Используем улучшенный метод с учетом истории пользователя
            products = await self.recommendation_service.recommend_products_by_context(
                user_id=user_id,
                query_text=contextual_message,
                cjm_stage=cjm_stage,
                persona=persona,
                limit=10,
                use_vector_search=True,
                require_images=True,
            )
            
            # Если новый метод не вернул достаточно товаров, используем старый
            if len(products) < 5:
                products_fallback = await self.recommendation_service.recommend_products(
                    persona=persona,
                    tags=tags,
                    limit=12,  # Увеличиваем лимит, чтобы было больше товаров для карточек
                    require_images=True,
                )
                existing_ids = {p.id for p in products}
                for fallback in products_fallback:
                    if fallback.id not in existing_ids:
                        products.append(fallback)
                        existing_ids.add(fallback.id)

        # Добавляем точечные товары по номенклатуре/артикулу/коду, если они найдены
        if nomenclature_products:
            existing_ids = {p.id for p in products}
            merged = []
            for p in nomenclature_products + products:
                if p.id not in existing_ids:
                    merged.append(p)
                    existing_ids.add(p.id)
                elif p in nomenclature_products:
                    merged.append(p)
            if merged:
                products = merged + [p for p in products if p.id not in {x.id for x in merged}]
        
        looks: List[Look] = []
        if include_looks:
            # Подбираем образы только по запросу/контексту образа.
            looks = await self.recommendation_service.recommend_looks_by_query(
                query_text=contextual_message,
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

        # Финальная защита: в чат отдаем только одобренные образы.
        looks = [
            look
            for look in looks
            if (str(look.approval_status or "").lower() == "approved")
            or (str(look.status or "").lower() == "approved")
        ]
        
        # Формируем промпт для LLM
        site_app_context_text = await self._collect_site_app_context(message=message, city=city)
        products_info = "\n".join([
            f"- {p.name} ({p.brand or 'GLAME'}) - {p.price/100:.0f} руб. Теги: {', '.join(p.tags) if p.tags else 'нет тегов'}"
            for p in products[:5]
        ]) if products else "Пока нет доступных товаров"
        
        looks_info = "\n".join([
            f"- {l.name}: {l.description or l.mood or l.style}. Товары: {', '.join([str(pid) for pid in l.product_ids[:3]])}"
            for l in looks
        ]) if looks else "Пока нет доступных образов"

        show_stores = self._is_store_intent(contextual_message)
        store_city_filter = city
        asked_store_city = self._detect_store_city_from_message(contextual_message)
        if asked_store_city:
            store_city_filter = asked_store_city
        elif self._is_broad_store_request(contextual_message):
            # Для общего вопроса о магазинах не ограничиваемся городом профиля.
            store_city_filter = None

        stores_context_text = (
            await self._build_stores_context(city=store_city_filter, limit=10)
            if show_stores
            else "Контекст магазинов не запрошен в текущем сообщении."
        )
        stores_payload = (
            await self._get_stores_payload(city=store_city_filter, limit=6)
            if show_stores
            else []
        )
        store_stock_context_text = await self._build_store_stock_context(products=products[:6], city=city)
        purchase_options_text = """- Онлайн покупка: добавить в корзину, обновить количество, удалить товар, перейти к checkout.
- Варианты доставки: самовывоз из магазина, доставка через CDEK ПВЗ.
- Оплата: карта онлайн, а также доступные варианты на этапе checkout.
- Примерка: предложить примерку образа (виртуальную или в офлайн-магазине по записи)."""
        
        # Форматируем контекст бренда для промпта с использованием улучшенного метода
        brand_context_text = self.format_brand_context_for_prompt(brand_context) if brand_context else "Философия GLAME: стиль как отражение характера. Мы предлагаем уникальные украшения от известных брендов."
        
        memory_summary_text = self._build_memory_summary(
            style_dna=style_dna,
            conversation_history=conversation_history,
            user_context=user_context,
            long_memory_text=long_memory_text,
        )

        prompt = f"""Пользователь написал: "{message}"

Персона: {persona} ({self.PERSONAS.get(persona, '')})
Этап CJM: {cjm_stage} ({self.CJM_STAGES.get(cjm_stage, '')})
Город: {city or 'не указан'}
{user_context if user_context else ''}

Style DNA покупателя:
{self._format_style_dna_for_prompt(style_dna)}

Решение продавца на этот ход:
- Следующее действие: {sales_decision.next_action}
- CTA type: {sales_decision.cta_type}
- Возражение: {sales_decision.objection or 'нет'}

Короткая история диалога (последние сообщения):
{short_history_text}

{long_memory_text}

Память о человеке (memory summary):
{memory_summary_text}

ВАЖНО: Используй следующий контекст бренда GLAME для формирования ответа:
{brand_context_text}

Контекст сайта/приложения (каталог, разделы, контент):
{site_app_context_text}

Доступные товары:
{products_info}

Доступные образы:
{looks_info}

Магазины GLAME:
{stores_context_text}

Наличие выбранных товаров по магазинам:
{store_stock_context_text}

Варианты покупки:
{purchase_options_text}

Сформируй ответ стилиста:
1. Продолжай разговор в контексте истории, НЕ начинай диалог заново.
2. Если приветствие уже было ({'да' if greeted_before else 'нет'}), не повторяй длинное приветствие.
3. Тон общения: живой и человечный, как знакомый профессиональный консультант, а не CRM-скрипт.
4. На этапе inspiration собери Style DNA (повод, стиль, бюджет, предпочтения) и задавай только 1 уточняющий вопрос за сообщение.
5. После ключевых вводных веди по сценарию: потребность -> решение/сравнение -> мягкий переход к покупке.
6. Если вопрос про артикул/код/номенклатуру, дай точный ответ по товару и остаткам в магазинах.
7. Если данных не хватает, задай ОДИН уточняющий вопрос вместо монолога.
8. Если вопрос информационный о бренде/коллекциях/происхождении ({'да' if info_intent else 'нет'}), отвечай фактами из контекста и НЕ предлагай образы/товары без явного запроса.
9. Для информационного вопроса добавь 1-2 подтвержденных факта; если фактов нет — честно сообщи об этом.
10. Следующий шаг этого хода: {sales_next_action}
11. При возражении сначала признай его, затем дай короткое решение и только потом CTA.
12. Не используй однотипные шаблоны в каждом сообщении.
13. Не показывай товары и не упоминай конкретные позиции, если пользователь не просит подбор и не обсуждает конкретный товар.
14. На короткие уточнения ("почему", "долго держится", "как ухаживать") отвечай по сути, без резкого перевода в продажу.

КРИТИЧЕСКИ ВАЖНО:
- Всегда обращайся к покупателю на «Вы/Вам/Ваш», без перехода на «ты».
- Используй конкретные факты и формулировки из контекста бренда GLAME
- Используй факты из контекста сайта/приложения (каталог/разделы/контент), когда вопрос про коллекции, товары, разделы, новости, акции.
- Отражай философию и ценности бренда в своем ответе
- Будь вдохновляющим и профессиональным, но лаконичным
- Используй конкретные названия товаров
- Опирайся на контекст бренда при объяснении, почему образы подходят
- Не придумывай остатки/адреса/артикулы: используй только данные из контекста выше
- Не заканчивай каждый ответ продажным CTA; предлагай следующий шаг только когда он естественно вытекает из запроса
- Формат ответа: коротко, разговорно, не более 3 предложений, не более 1 вопроса.
- Допускается одна уместная легкая шутка/теплая фраза в ответе, если это не снижает профессионализм и не уводит от цели этапа.
- Используй memory summary как приоритетный контекст: не повторяй уже выясненные вопросы и продолжай разговор от текущего шага."""
        
        # Получаем системный промпт из БД
        system_prompt = await self.get_active_system_prompt(
            self.db,
            self.PROMPT_AGENT_TYPE,
            self.BRAND_SYSTEM_PROMPT,
        )
        
        # Генерируем ответ
        llm_fallback = False
        llm_fallback_reason: Optional[str] = None
        try:
            reply = await self.generate_response(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.55,
                max_tokens=900
            )
        except (ValueError, Exception) as e:
            # Fallback ответ при сбое LLM: сохраняем контекст, этап и следующую цель хода.
            import logging
            logger = logging.getLogger(__name__)
            llm_fallback = True
            llm_fallback_reason = self._classify_llm_error(e)
            logger.warning(
                "StylistAgent LLM fallback triggered: reason=%s error=%r",
                llm_fallback_reason,
                e,
            )

            if info_intent:
                if info_facts:
                    reply = f"{info_facts[0]} {sales_next_action}"
                else:
                    reply = (
                        "Уточню по базе знаний и сразу вернусь с точными данными. "
                        "Пока могу продолжить консультацию по подбору, если хотите."
                    )
            elif cjm_stage == "inspiration":
                reply = (
                    f"Поняла вас. Чтобы не промахнуться с подбором, уточню один момент: "
                    f"{style_dna_question or 'какой стиль и повод сейчас приоритетнее?'}"
                )
            elif cjm_stage == "consideration":
                if products:
                    top_names = ", ".join([p.name for p in products[:2] if getattr(p, "name", None)])
                    if top_names:
                        reply = (
                            f"Покажу сравнение по делу: {top_names}. "
                            "Сразу отмечу разницу по стилю, цене и наличию."
                        )
                    else:
                        reply = "Покажу 2 релевантных варианта и коротко сравню их по стилю, цене и наличию."
                else:
                    reply = "Покажу 2 релевантных варианта и коротко сравню их по стилю, цене и наличию."
            else:
                reply = "Готово, веду к покупке: могу сразу добавить выбранный вариант в корзину и подсказать по оплате/доставке."
        if info_intent:
            if not brand_context:
                reply = (
                    "По этому вопросу в базе знаний GLAME сейчас нет подтвержденных данных. "
                    "Могу уточнить у команды и вернуться с точной информацией."
                )
            else:
                reply = self._inject_facts_into_info_reply(reply, info_facts)
        reply = self._normalize_reply_length(reply)
        reply = self._enforce_compact_dialogue(reply, max_sentences=3, max_questions=1)
        reply = self._apply_cjm_turn_template(
            reply=reply,
            cjm_stage=cjm_stage,
            products=products,
            looks=looks,
            city=city,
            include_products=include_products,
            include_looks=include_looks,
            info_intent=info_intent,
            style_dna_ready=style_dna_ready,
            style_dna_question=style_dna_question,
            greeted_before=greeted_before,
            objection=sales_decision.objection,
            cta_type=sales_decision.cta_type,
        )
        previous_assistant_text = self._last_assistant_text(conversation_history)
        if self._is_redundant_reply(reply, previous_assistant_text):
            if cjm_stage == "inspiration" and style_dna_question:
                reply = f"Чтобы лучше понять ваш запрос, уточню один момент: {style_dna_question}"
            elif cjm_stage == "consideration":
                reply = "Сейчас сузлю выбор до пары релевантных вариантов и коротко покажу разницу между ними."
        if not info_intent and cjm_stage == "inspiration" and style_dna_question:
            low = reply.lower()
            if "подберу варианты" in low and "уточ" not in low:
                reply = f"{self._strip_leading_greeting(self._first_sentence(reply))} Чтобы не гадать, уточню один момент: {style_dna_question}"
        reply = self._strip_template_openers(reply)
        reply = self._enforce_compact_dialogue(reply, max_sentences=3, max_questions=1)
        reply = self._enforce_formal_address(reply)
        session.interactions.append({
            "assistant_reply": reply[:600],
            "cjm_stage": cjm_stage,
            "sales_state": {
                "style_dna": style_dna.to_dict(),
                "sales_decision": sales_decision.to_dict(),
            },
        })
        
        # Формируем структурированный ответ
        selected_looks = []
        all_products_in_looks = set()  # Для отслеживания товаров, уже включенных в образы
        if include_looks:
            for look in looks[:2]:
                look_products = await self.recommendation_service.get_look_products(look.id)
                display_look_products: List[Product] = []
                for p in look_products:
                    display_look_products.append(await self._resolve_product_for_display(p))
                product_list = []
                for p in display_look_products:
                    payload = await self._to_product_payload(p)
                    if self._payload_has_images(payload):
                        product_list.append(payload)
                if not product_list:
                    continue
                selected_looks.append({
                    "id": str(look.id),
                    "name": look.name,
                    "products": product_list,
                    "mood": look.mood,
                    "style": look.style,
                    "description": look.description,
                    "image_url": self._resolve_look_image_url(look),
                })
                # Добавляем ID товаров из образа в множество
                all_products_in_looks.update(str(p.id) for p in display_look_products)
        
        # Формируем отдельный список всех рекомендованных товаров для карточек
        # Включаем товары из образов + дополнительные товары, если их меньше 6
        recommended_products = []
        
        if include_products:
            # Сначала добавляем товары из образов
            for look in selected_looks:
                for product in look["products"]:
                    if product["id"] not in [p["id"] for p in recommended_products]:
                        recommended_products.append(product)
            
            # Добавляем дополнительные товары из общего списка, если их меньше 6
            if len(recommended_products) < 6 and products:
                for p in products:
                    if str(p.id) not in all_products_in_looks and len(recommended_products) < 6:
                        payload = await self._to_product_payload(p)
                        # Вне утвержденного образа показываем только товары в наличии.
                        if self._payload_has_images(payload) and bool(payload.get("in_stock")):
                            recommended_products.append(payload)

            # Если в тексте ответа упомянуты товары, добавляем карточки только когда в целом уместен товарный блок.
            mentioned_products = await self._find_products_from_reply(reply, limit=6)
            if mentioned_products:
                existing_ids = {str(p.get("id")) for p in recommended_products}
                mentioned_payloads = []
                for p in mentioned_products:
                    payload = await self._to_product_payload(p)
                    if not self._payload_has_images(payload):
                        continue
                    # Вне утвержденного образа показываем только товары в наличии.
                    # Исключение: товар уже входит в утвержденный образ.
                    if (not bool(payload.get("in_stock"))) and payload["id"] not in all_products_in_looks:
                        continue
                    if payload["id"] in existing_ids:
                        continue
                    mentioned_payloads.append(payload)
                    existing_ids.add(payload["id"])
                if mentioned_payloads:
                    # Если нашли явные упоминания товаров — показываем только согласованные
                    # с текстом карточки, чтобы не было рассинхрона "в тексте одно, внизу другое".
                    combined = mentioned_payloads + recommended_products
                    dedup: List[Dict[str, Any]] = []
                    seen = set()
                    for payload in combined:
                        pid = str(payload.get("id"))
                        if not pid or pid in seen:
                            continue
                        seen.add(pid)
                        dedup.append(payload)
                    aligned = [
                        p for p in dedup
                        if self._is_payload_mentioned_in_reply(reply, p)
                    ]
                    if aligned:
                        recommended_products = aligned[:8]
            # Если явных упоминаний нет, не вычищаем карточки на этапе подбора.
            # Пользователь уже запросил подбор, товары должны отображаться сразу.
            if not mentioned_products and cjm_stage == "consideration":
                recommended_products = recommended_products[:8]

            # Страховка: в этапе подбора показываем хотя бы 2 товара, если есть кандидаты.
            if not recommended_products and cjm_stage == "consideration" and products:
                for p in products:
                    payload = await self._to_product_payload(p)
                    if self._payload_has_images(payload) and bool(payload.get("in_stock")):
                        recommended_products.append(payload)
                    if len(recommended_products) >= 2:
                        break
        
        # Сохраняем сессию
        await self.db.commit()
        
        # Формируем CTA
        cta = f"Записаться в пространство GLAME{' в ' + city if city else ''}" if city else "Записаться в пространство GLAME"
        
        return {
            "persona": persona,
            "cjm_stage": cjm_stage,
            "dialog_step": cjm_stage,
            "reply": reply,
            "collections": interactive.get("collections") or [],
            "brands": interactive.get("brands") or [],
            "sections": interactive.get("sections") or [],
            "looks": selected_looks,
            "products": recommended_products,  # Отдельный список товаров для карточек
            "stores_context": stores_context_text,
            "stores": stores_payload,
            "show_stores": show_stores,
            "store_stock_context": store_stock_context_text,
            "purchase_options": purchase_options_text,
            "cta": cta,
            "cta_type": sales_decision.cta_type,
            "next_action": sales_decision.next_action,
            "sales_decision": sales_decision.to_dict(),
            "style_dna": style_dna.to_dict(),
            "llm_fallback": llm_fallback,
            "llm_fallback_reason": llm_fallback_reason,
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

    @staticmethod
    def _is_look_intent(message: str, conversation_history: Optional[List[Dict[str, Any]]] = None) -> bool:
        text = (message or "").lower()
        look_keywords = [
            "образ", "лук", "комплект", "сочет", "подбери образ", "собери образ",
            "на вечер", "на свидание", "на свадьбу", "на корпоратив",
        ]
        if any(k in text for k in look_keywords):
            return True
        # Не тащим "образный" контекст из прошлых реплик в инфо-вопросы.
        return False

    @staticmethod
    def _is_product_offer_intent(message: str) -> bool:
        text = (message or "").lower()
        product_keywords = [
            "подбери", "посовет", "покажи", "что купить", "варианты",
            "товар", "артикул", "код", "в корзин", "купить", "замена",
            "аналог", "серьги", "кольцо", "кольца", "колье", "браслет",
            "кафф", "пусеты", "подвес", "цепочка",
        ]
        return any(k in text for k in product_keywords)

    @staticmethod
    def _is_brand_info_intent(message: str) -> bool:
        text = (message or "").lower()
        info_keywords = [
            "о бренде", "о компании", "кто вы", "кто такие", "история бренда",
            "откуда", "производ", "где производ", "материал", "состав",
            "коллекци", "философ", "миссия", "о glame", "о украшениях",
            "какие бренды", "какой бренд", "бренды продаете", "бренды представлены",
            "что за бренды", "ассортимент брендов", "какие марки",
            "покрыти", "родий", "позолот", "уход", "ухаживать", "как чистить",
            "долго держится", "срок службы", "темнеет", "слезает покрытие",
            "средняя цена", "в среднем", "какая цена", "сколько в среднем",
            "зачем", "почему", "что значит", "что это", "как это работает",
        ]
        return any(k in text for k in info_keywords)

    @staticmethod
    def _extract_collection_title(raw: str) -> str:
        value = (raw or "").strip()
        value = re.sub(r"\.pdf$|\.json$", "", value, flags=re.IGNORECASE)
        value = re.sub(r"^(коллекция|collection)\s+", "", value, flags=re.IGNORECASE).strip()
        return value.strip(" -_")

    async def _get_catalog_sections_list(self, limit: int = 12) -> List[str]:
        rows = list(
            (
                await self.db.execute(
                    select(CatalogSection.name)
                    .where(CatalogSection.is_active == True)
                    .order_by(CatalogSection.name.asc())
                    .limit(limit * 2)
                )
            ).all()
        )
        values: List[str] = []
        for row in rows:
            name = str(row.name or "").strip()
            if not name or name in values:
                continue
            values.append(name)
            if len(values) >= limit:
                break
        return values

    async def _get_brands_list(self, limit: int = 12) -> List[str]:
        rows = list(
            (
                await self.db.execute(
                    select(Product.brand)
                    .where(Product.is_active == True, Product.brand.is_not(None))
                    .order_by(Product.brand.asc())
                    .distinct()
                    .limit(limit * 3)
                )
            ).all()
        )
        values: List[str] = []
        for row in rows:
            brand = str(row.brand or "").strip()
            if not brand or brand in values:
                continue
            values.append(brand)
            if len(values) >= limit:
                break
        return values

    async def _get_collections_list(self, limit: int = 12) -> List[str]:
        # Берем из реестра загруженных документов коллекций (collections_info),
        # чтобы список соответствовал контенту БЗ.
        rows = list(
            (
                await self.db.execute(
                    select(KnowledgeDocument.filename, KnowledgeDocument.source)
                    .where(
                        KnowledgeDocument.collection_name == "collections_info",
                        KnowledgeDocument.status == "completed",
                    )
                    .order_by(KnowledgeDocument.created_at.desc())
                    .limit(limit * 5)
                )
            ).all()
        )
        values: List[str] = []
        for row in rows:
            for candidate in [row.filename, row.source]:
                title = self._extract_collection_title(str(candidate or ""))
                if not title or len(title) < 2 or title in values:
                    continue
                values.append(title)
                if len(values) >= limit:
                    return values
        return values

    @staticmethod
    def _interactive_tokens(message: str) -> List[str]:
        raw = re.findall(r"[a-zA-Zа-яА-Я0-9]{2,}", (message or "").lower())
        stop_words = {
            "какие", "какая", "какой", "какое", "какие", "покажи", "показать", "есть",
            "у", "вас", "мне", "про", "по", "и", "или", "в", "на", "о", "об", "что",
            "все", "всё", "можно", "нужно", "нужны", "подскажи", "скажи", "где",
            "коллекции", "коллекция", "бренды", "бренд", "разделы", "раздел",
            "каталог", "ассортимент",
        }
        return [t for t in raw if t not in stop_words]

    @staticmethod
    def _score_interactive_label(label: str, message: str, tokens: List[str]) -> float:
        value = (label or "").strip().lower()
        if not value:
            return 0.0
        msg = (message or "").lower()
        score = 0.0
        if value in msg:
            score += 5.0
        if any(token and token in value for token in tokens):
            score += 2.0
        for token in tokens:
            if not token:
                continue
            if value.startswith(token):
                score += 1.2
            elif token in value:
                score += 0.8
        # Короткие названия немного удобнее как быстрые действия.
        score += max(0.0, 1.0 - min(len(value), 30) / 30.0)
        return score

    def _rank_interactive_items(self, items: List[str], message: str, limit: int = 12) -> List[str]:
        tokens = self._interactive_tokens(message)
        scored = [
            (self._score_interactive_label(label=item, message=message, tokens=tokens), item)
            for item in items
        ]
        scored.sort(key=lambda x: (x[0], x[1].lower()), reverse=True)
        return [item for _, item in scored[:limit]]

    async def _build_interactive_entities(self, message: str) -> Dict[str, List[Dict[str, str]]]:
        text = (message or "").lower()
        ask_collections = any(k in text for k in ["коллекц", "collection"])
        ask_brands = any(k in text for k in ["бренд", "марк", "производ"])
        ask_sections = any(k in text for k in ["раздел", "категор", "что есть", "ассортимент"])

        # Для широкого вопроса "что есть / ассортимент" показываем все основные блоки.
        if any(k in text for k in ["что у вас есть", "ассортимент", "каталог", "покажи все"]):
            ask_collections = True
            ask_brands = True
            ask_sections = True

        payload: Dict[str, List[Dict[str, str]]] = {
            "collections": [],
            "brands": [],
            "sections": [],
        }
        if ask_collections:
            ranked_collections = self._rank_interactive_items(
                await self._get_collections_list(limit=24),
                message=message,
                limit=16,
            )
            payload["collections"] = [
                {"label": name, "search": name, "action": "open_catalog"}
                for name in ranked_collections
            ]
        if ask_brands:
            ranked_brands = self._rank_interactive_items(
                await self._get_brands_list(limit=24),
                message=message,
                limit=16,
            )
            payload["brands"] = [
                {"label": name, "search": name, "action": "open_catalog"}
                for name in ranked_brands
            ]
        if ask_sections:
            ranked_sections = self._rank_interactive_items(
                await self._get_catalog_sections_list(limit=24),
                message=message,
                limit=16,
            )
            payload["sections"] = [
                {"label": name, "category": name, "action": "open_catalog"}
                for name in ranked_sections
            ]
        return payload
    
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

    async def _collect_site_app_context(self, message: str, city: Optional[str]) -> str:
        """
        Единый контекст сайта/приложения:
        - разделы каталога и связанные товары из БД
        - контент приложения (лукбуки/акции/новости)
        - релевантные фрагменты из векторных коллекций product_knowledge/content_pieces/looks_descriptions
        """
        msg = (message or "").strip()
        tokens = [t for t in re.findall(r"[a-zA-Zа-яА-Я0-9_\-]{3,}", msg.lower())][:8]
        like_clauses = [f"%{t}%" for t in tokens]

        lines: List[str] = []

        # 1) Каталог: разделы (живые данные БД)
        section_stmt = select(CatalogSection).where(CatalogSection.is_active == True)
        if like_clauses:
            section_stmt = section_stmt.where(
                or_(*[CatalogSection.name.ilike(cl) for cl in like_clauses])
            )
        section_rows = list((await self.db.execute(section_stmt.limit(6))).scalars().all())
        if section_rows:
            lines.append("Разделы каталога:")
            for s in section_rows[:5]:
                lines.append(f"- {s.name} (код: {s.external_code or '—'})")

        # 2) Товары + привязка к разделам (живые данные БД)
        product_stmt = select(Product).where(Product.is_active == True)
        if like_clauses:
            product_stmt = product_stmt.where(
                or_(
                    *[Product.name.ilike(cl) for cl in like_clauses],
                    *[Product.category.ilike(cl) for cl in like_clauses],
                    *[Product.brand.ilike(cl) for cl in like_clauses],
                )
            )
        product_rows = list((await self.db.execute(product_stmt.limit(12))).scalars().all())
        if product_rows:
            pids = [p.id for p in product_rows if p.id]
            sec_map: Dict[UUID, List[str]] = {}
            if pids:
                rel_rows = (
                    await self.db.execute(
                        select(ProductCatalogSection.product_id, CatalogSection.name)
                        .join(CatalogSection, CatalogSection.id == ProductCatalogSection.catalog_section_id)
                        .where(ProductCatalogSection.product_id.in_(pids))
                    )
                ).all()
                for r in rel_rows:
                    sec_map.setdefault(r.product_id, []).append(r.name)

            lines.append("Товары каталога:")
            for p in product_rows[:6]:
                price = int(p.price or 0) / 100 if int(p.price or 0) > 0 else 0
                sec_names = ", ".join(sec_map.get(p.id, [])[:2]) or "раздел не указан"
                lines.append(
                    f"- {p.name} | бренд: {p.brand or 'GLAME'} | категория: {p.category or '—'} | "
                    f"цена: {price:.0f} руб | раздел: {sec_names}"
                )

        # 3) Контент приложения (лукбуки/акции/новости)
        lookbook_stmt = select(AppLookbook).where(AppLookbook.is_published == True)
        if like_clauses:
            lookbook_stmt = lookbook_stmt.where(
                or_(*[AppLookbook.title.ilike(cl) for cl in like_clauses])
            )
        lookbooks = list((await self.db.execute(lookbook_stmt.limit(4))).scalars().all())
        if lookbooks:
            lines.append("Лукбуки приложения:")
            for lb in lookbooks[:3]:
                lines.append(f"- {lb.title}: {lb.description or 'описание не указано'}")

        promotions_stmt = select(AppPromotion).where(AppPromotion.status == "published")
        if like_clauses:
            promotions_stmt = promotions_stmt.where(
                or_(*[AppPromotion.title.ilike(cl) for cl in like_clauses])
            )
        promotions = list((await self.db.execute(promotions_stmt.limit(4))).scalars().all())
        if promotions:
            lines.append("Актуальные акции:")
            for promo in promotions[:2]:
                body = (promo.body or "").strip()
                if len(body) > 140:
                    body = body[:139].rstrip() + "…"
                lines.append(f"- {promo.title}: {body}")

        news_stmt = select(AppNews).where(AppNews.status == "published")
        if like_clauses:
            news_stmt = news_stmt.where(or_(*[AppNews.title.ilike(cl) for cl in like_clauses]))
        news_rows = list((await self.db.execute(news_stmt.limit(4))).scalars().all())
        if news_rows:
            lines.append("Новости:")
            for n in news_rows[:2]:
                body = (n.body or "").strip()
                if len(body) > 120:
                    body = body[:119].rstrip() + "…"
                lines.append(f"- {n.title}: {body}")

        # 4) Векторные знания (сайтовые/товарные тексты)
        vector_blocks: List[str] = []
        for coll in ["product_knowledge", "content_pieces", "looks_descriptions"]:
            try:
                ctx = self.vector_db.get_context(coll, msg, limit=3, score_threshold=0.25)
            except Exception:
                ctx = []
            if not ctx:
                continue
            vector_blocks.append(f"{coll}:")
            for item in ctx[:2]:
                payload = item.get("payload", {}) if isinstance(item.get("payload"), dict) else {}
                text = str(payload.get("text") or "").strip()
                if not text:
                    continue
                if len(text) > 140:
                    text = text[:139].rstrip() + "…"
                vector_blocks.append(f"- {text}")
        if vector_blocks:
            lines.append("Векторные знания:")
            lines.extend(vector_blocks)

        if city and city.strip():
            lines.append(f"Городовой контекст клиента: {city.strip()}")

        if not lines:
            return "Контекст сайта/приложения: релевантные данные не найдены."
        return "\n".join(lines)
    
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
        use_default_model: bool = False,
        digital_model: Optional[str] = None,
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
            use_default_model=use_default_model,
            digital_model=digital_model,
        )
        
        await self.db.commit()
        
        # Получаем товары образа
        products = await self.recommendation_service.get_look_products(look.id)
        
        return {
            "id": str(look.id),
            "name": look.name,
            "description": look.description,
            "product_ids": [str(pid) for pid in (look.product_ids or [])],
            "style": look.style,
            "mood": look.mood,
            "image_url": look.image_url,
            "image_urls": look.image_urls or [],
            "current_image_index": look.current_image_index,
            "status": look.status,
            "approval_status": look.approval_status,
            "try_on_image_url": look.try_on_image_url,
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
