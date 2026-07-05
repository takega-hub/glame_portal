from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cart import Cart
from app.models.cart_item import CartItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.user import User


@dataclass
class ProductRecommendation:
    product: Product
    score: float
    reasons: list[str]


class CustomerProductRecommendationAgent:
    """Hybrid product-card recommender for the customer app.

    The first production pass is deterministic: it blends visual/style similarity
    from product data with personal signals from customer profile, cart and orders.
    A later vector index can replace or enrich `_token_similarity` without changing
    the API contract used by the app.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def recommend_for_product(
        self,
        product_id: UUID,
        user: Optional[User] = None,
        limit: int = 3,
    ) -> list[ProductRecommendation]:
        current = await self._get_product(product_id)
        if not current:
            return []

        personal = await self._personal_profile(user)
        current_tokens = self._product_tokens(current)
        current_price = int(current.price or 0)

        candidates = await self._candidate_products(current, personal)
        scored: list[ProductRecommendation] = []

        for candidate in candidates:
            if candidate.id == current.id:
                continue
            if personal["purchased_ids"] and candidate.id in personal["purchased_ids"]:
                continue

            score = 0.0
            reasons: list[str] = []

            token_score = self._token_similarity(current_tokens, self._product_tokens(candidate))
            if token_score:
                score += token_score * 46
                reasons.append("похожее настроение")

            if current.category and candidate.category == current.category:
                score += 22
                reasons.append("та же категория")

            candidate_specs = candidate.specifications if isinstance(candidate.specifications, dict) else {}
            current_specs = current.specifications if isinstance(current.specifications, dict) else {}
            for key in ("Металл", "Материал", "Цвет", "Покрытие", "Вставка"):
                if current_specs.get(key) and current_specs.get(key) == candidate_specs.get(key):
                    score += 8
                    reasons.append(str(key).lower())
                    break

            if current_price > 0 and candidate.price:
                price_distance = abs(int(candidate.price) - current_price) / max(current_price, 1)
                score += max(0.0, 14.0 * (1.0 - min(price_distance, 1.0)))

            if candidate.category in personal["favorite_categories"]:
                score += 18
                reasons.append("по вашей истории")
            if candidate.brand and candidate.brand in personal["favorite_brands"]:
                score += 10
                reasons.append("любимый бренд")
            if candidate.id in personal["cart_ids"]:
                score += 12
                reasons.append("сочетается с корзиной")

            budget_min, budget_max = personal["budget"]
            if candidate.price and budget_min is not None and candidate.price < budget_min:
                score -= 8
            if candidate.price and budget_max is not None and candidate.price > budget_max:
                score -= 14

            if self._has_images(candidate):
                score += 7
            if bool(candidate.is_core_assortment):
                score += 4
            if bool(candidate.supports_brand_concept):
                score += 4

            if score <= 0:
                continue

            scored.append(
                ProductRecommendation(
                    product=candidate,
                    score=round(score, 2),
                    reasons=list(dict.fromkeys(reasons))[:3],
                )
            )

        scored.sort(key=lambda item: (-item.score, str(item.product.id)))
        return self._dedupe_by_base_article(scored)[:limit]

    async def _get_product(self, product_id: UUID) -> Optional[Product]:
        result = await self.db.execute(select(Product).where(Product.id == product_id))
        return result.scalar_one_or_none()

    async def _candidate_products(self, current: Product, personal: dict) -> list[Product]:
        query = (
            select(Product)
            .where(
                Product.is_active == True,
                Product.price > 0,
                Product.id != current.id,
            )
            .limit(240)
        )
        result = await self.db.execute(query)
        products = list(result.scalars().all())
        return [p for p in products if self._is_sellable_variant(p)]

    async def _personal_profile(self, user: Optional[User]) -> dict:
        profile = {
            "favorite_categories": set(),
            "favorite_brands": set(),
            "cart_ids": set(),
            "purchased_ids": set(),
            "budget": (None, None),
        }
        if not user:
            return profile

        prefs = user.preferences if isinstance(user.preferences, dict) else {}
        purchase_prefs = user.purchase_preferences if isinstance(user.purchase_preferences, dict) else {}

        profile["favorite_categories"].update(self._values_from_pref(purchase_prefs, "categories"))
        profile["favorite_categories"].update(self._values_from_pref(purchase_prefs, "favorite_categories"))
        profile["favorite_brands"].update(self._values_from_pref(purchase_prefs, "brands"))
        profile["favorite_brands"].update(self._values_from_pref(prefs, "favorite_brands"))

        budget = prefs.get("budget_range") if isinstance(prefs.get("budget_range"), dict) else {}
        profile["budget"] = (self._as_int(budget.get("min")), self._as_int(budget.get("max")))
        if profile["budget"] == (None, None) and user.average_check:
            avg = int(user.average_check)
            profile["budget"] = (math.floor(avg * 0.55), math.ceil(avg * 1.65))

        cart_result = await self.db.execute(select(Cart).where(Cart.user_id == user.id))
        cart = cart_result.scalar_one_or_none()
        if cart:
            items_result = await self.db.execute(select(CartItem).where(CartItem.cart_id == cart.id))
            profile["cart_ids"].update(item.product_id for item in items_result.scalars().all())

        orders_result = await self.db.execute(
            select(Order.id)
            .where(Order.user_id == user.id)
            .order_by(desc(Order.created_at))
            .limit(12)
        )
        order_ids = [row[0] for row in orders_result.all()]
        if order_ids:
            items_result = await self.db.execute(select(OrderItem).where(OrderItem.order_id.in_(order_ids)))
            profile["purchased_ids"].update(item.product_id for item in items_result.scalars().all())

        history_ids = list(profile["cart_ids"] | profile["purchased_ids"])
        if history_ids:
            products_result = await self.db.execute(select(Product).where(Product.id.in_(history_ids)))
            for product in products_result.scalars().all():
                if product.category:
                    profile["favorite_categories"].add(product.category)
                if product.brand:
                    profile["favorite_brands"].add(product.brand)

        return profile

    @staticmethod
    def _values_from_pref(data: dict, key: str) -> set[str]:
        value = data.get(key)
        if isinstance(value, dict):
            value = value.keys()
        if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
            return set()
        result = set()
        for item in value:
            if isinstance(item, (list, tuple)) and item:
                item = item[0]
            text = str(item or "").strip()
            if text:
                result.add(text)
        return result

    @staticmethod
    def _product_tokens(product: Product) -> set[str]:
        chunks: list[str] = [
            product.name or "",
            product.brand or "",
            product.category or "",
            product.description or "",
            product.full_description or "",
        ]
        if isinstance(product.tags, list):
            chunks.extend(str(tag) for tag in product.tags)
        if isinstance(product.specifications, dict):
            chunks.extend(str(value) for value in product.specifications.values())
        text = " ".join(chunks).lower()
        return {
            token
            for token in re.findall(r"[a-zа-яё0-9]+", text)
            if len(token) >= 3 and token not in {"для", "или", "with", "the"}
        }

    @staticmethod
    def _token_similarity(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)

    @staticmethod
    def _has_images(product: Product) -> bool:
        return isinstance(product.images, list) and any(str(image or "").strip() for image in product.images)

    @staticmethod
    def _is_sellable_variant(product: Product) -> bool:
        if not product.price or product.price <= 0:
            return False
        specs = product.specifications if isinstance(product.specifications, dict) else {}
        sync = product.sync_metadata if isinstance(product.sync_metadata, dict) else {}
        return bool(
            specs.get("parent_external_id")
            or specs.get("Parent_Key")
            or specs.get("parent_key")
            or sync.get("parent_external_id")
            or sync.get("Parent_Key")
            or sync.get("parent_key")
        )

    @staticmethod
    def _base_article(article: Optional[str]) -> str:
        raw = (article or "").strip()
        for separator in ("-", "_", " "):
            if separator in raw:
                return raw.split(separator, 1)[0].strip() or raw
        return raw

    def _dedupe_by_base_article(
        self,
        recommendations: list[ProductRecommendation],
    ) -> list[ProductRecommendation]:
        seen: set[str] = set()
        result: list[ProductRecommendation] = []
        for item in recommendations:
            key = self._base_article(item.product.article) or str(item.product.id)
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    @staticmethod
    def _as_int(value) -> Optional[int]:
        try:
            if value is None or value == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None
