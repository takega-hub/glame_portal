from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import os
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer_message import CustomerMessage
from app.models.crm_service_case import CrmServiceCase
from app.models.customer_request import CustomerRequest
from app.models.crm_task import CrmTask, CrmTaskEvent
from app.models.product import Product
from app.models.product_arrival_subscription import ProductArrivalSubscription
from app.models.product_stock_arrival_event import ProductStockArrivalEvent
from app.models.product_stock import ProductStock
from app.models.purchase_history import PurchaseHistory
from app.models.store import Store
from app.models.user import User
from app.services.crm_task_service import CrmTaskService
from app.services.sales_record_filters import product_eligible_filter
from app.services.store_aliases import MEGANOM_TO_MRIYA_START_DATE, crm_store_key as effective_crm_store_key, effective_store_name

CRM_NEW_ARRIVAL_SOURCE = "crm_new_arrival"
CRM_NEW_ARRIVAL_CAMPAIGN_ID = "new-arrival-clienteling"
CRM_NEW_ARRIVAL_CAMPAIGN_NAME = "Новое поступление"
CRM_NEW_ARRIVAL_GROUP = "new_arrival"
COMMERCIAL_COOLDOWN_DAYS = int(os.getenv("CRM_COMMERCIAL_COOLDOWN_DAYS", "30"))
LEGACY_MEGANOM_MRIYA_START_DATE = MEGANOM_TO_MRIYA_START_DATE
MIN_RELEVANT_TASKS_BEFORE_WARM_EXPANSION = 7
OPEN_STATUSES = {"new", "in_progress", "postponed"}

CRM_STORE_MANAGER_NAMES = {
    "CENTRUM": "Бешлиева Аджере Айдеровна",
    "YALTA": "Рогалевич Ирина Евгеньевна",
}


@dataclass
class ArrivalGroup:
    arrival_id: str
    physical_store: str
    physical_store_id: str
    crm_store: str
    display_store_name: str
    brand: str
    received_at: datetime
    items: List[Dict[str, Any]]
    media: List[str]
    min_price: int
    categories: List[str]
    product_uuids: List[Any]
    event_ids: List[Any]
    novelty_type: str = "REPLENISHMENT"
    strength: str = "MEDIUM_BRAND_TRIGGER"


def _clean_text(value: Any) -> Optional[str]:
    text = " ".join(str(value or "").strip().split())
    return text or None


def _normalize(value: Any) -> str:
    return (_clean_text(value) or "").lower().replace("ё", "е")


def _first_name(user: User) -> str:
    name = _clean_text(user.full_name) or _clean_text(user.phone) or "Клиент"
    parts = name.split()
    # Most 1C customer names in the project are stored as "Фамилия Имя ...".
    if len(parts) >= 2 and not parts[0].startswith("+") and not parts[0].isdigit():
        return parts[1]
    return parts[0] if parts else "Клиент"


def _coerce_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def _display_store_name(value: Optional[str], event_date: Any = None) -> Optional[str]:
    return effective_store_name(value, event_date)


def _crm_store_key(store_name: Optional[str], city: Optional[str] = None, event_date: Any = None) -> Optional[str]:
    alias_key = effective_crm_store_key(store_name, city, event_date)
    if alias_key == "MRIYA":
        return "YALTA"
    if alias_key in {"CENTRUM", "YALTA"}:
        return alias_key
    source = _normalize(" ".join([str(store_name or ""), str(city or "")]))
    if not source:
        return None
    if "ялта" in source or "мрия" in source or "mriya" in source:
        return "YALTA"
    if "меганом" in source or "meganom" in source:
        day = _coerce_date(event_date) or date.today()
        return "YALTA" if day >= LEGACY_MEGANOM_MRIYA_START_DATE else "CENTRUM"
    if "центрум" in source or "centrum" in source or "симфер" in source:
        return "CENTRUM"
    return None


def _crm_store_label(crm_store: str) -> str:
    if crm_store == "YALTA":
        return "Ялта"
    return "ТРК Центрум"


def _first_images(product: Product, limit: int = 2) -> List[str]:
    images = product.images if isinstance(product.images, list) else []
    result: List[str] = []
    for image in images:
        value = str(image or "").strip()
        if value:
            result.append(value)
        if len(result) >= limit:
            break
    return result


def _seller_external_id(user: Optional[User]) -> Optional[str]:
    if not user:
        return None
    prefs = user.preferences if isinstance(user.preferences, dict) else {}
    return (
        str(prefs.get("seller_external_id") or "").strip()
        or str(prefs.get("onec_seller_id") or "").strip()
        or str(prefs.get("employee_external_id") or "").strip()
        or None
    )


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class CrmNewArrivalService:
    """CRM clienteling generator for primary purchase/receipt arrivals.

    Business rule: store transfers and stock availability changes are not a
    "new arrival" touchpoint. This service consumes only curated receipt events
    that represent primary закупка/приходная накладная on the main warehouse.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.crm_service = CrmTaskService(db)

    async def generate_tasks(
        self,
        work_date: Optional[date] = None,
        *,
        received_since: Optional[datetime] = None,
        lookback_hours: int = 48,
        limit_arrivals: int = 10,
        limit_clients_per_arrival: int = 25,
        use_polling_fallback: bool = False,
        dry_run: bool = True,
        batch_id: Optional[str] = None,
        actor: Optional[User] = None,
    ) -> Dict[str, Any]:
        work_date = work_date or date.today()
        received_since = received_since or (datetime.now(timezone.utc) - timedelta(hours=max(1, lookback_hours)))
        arrivals = await self._load_arrivals_from_events(received_since=received_since, limit=max(1, limit_arrivals))
        if batch_id:
            arrivals = [
                arrival
                for arrival in arrivals
                if arrival.arrival_id == batch_id or arrival.arrival_id.startswith(f"{batch_id}:")
            ]
        # Важно: перемещения/остатки магазинов не являются новым поступлением.
        # Параметр use_polling_fallback оставлен для обратной совместимости API,
        # но больше не включает генерацию задач по product_stocks.
        if not arrivals and use_polling_fallback:
            pass
        staff = await self._staff_users()

        summary: Dict[str, Any] = {
            "work_date": work_date.isoformat(),
            "received_since": received_since.isoformat(),
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [],
            "by_arrival": {},
            "dry_run": dry_run,
            "tasks_previewed": 0,
        }

        for arrival in arrivals:
            arrival_stats = {
                "created": 0,
                "skipped": 0,
                "errors": 0,
                "brand": arrival.brand,
                "crm_store": arrival.crm_store,
                "novelty_type": arrival.novelty_type,
                "strength": arrival.strength,
            }
            try:
                if await self._arrival_recently_used(arrival, work_date):
                    summary["skipped"] += 1
                    arrival_stats["skipped"] += 1
                    arrival_stats["skip_reason"] = "arrival_cooldown_same_products"
                    await self._mark_arrival_events_processed(arrival)
                    summary["by_arrival"][arrival.arrival_id] = arrival_stats
                    continue
                candidates = await self._candidates_for_arrival(arrival, limit=limit_clients_per_arrival)
                manager = self._manager_for_crm_store(arrival.crm_store, staff)
                for candidate in candidates:
                    customer = candidate["customer"]
                    block_reason = await self._block_reason(customer, arrival, work_date, candidate=candidate)
                    if block_reason:
                        summary["skipped"] += 1
                        arrival_stats["skipped"] += 1
                        continue
                    idempotency_key = f"{CRM_NEW_ARRIVAL_SOURCE}:{arrival.arrival_id}:{customer.id}"
                    existing = await self.db.scalar(select(CrmTask).where(CrmTask.source_idempotency_key == idempotency_key))
                    if existing:
                        summary["skipped"] += 1
                        arrival_stats["skipped"] += 1
                        continue
                    channel = self._channel_for(candidate)
                    script_text = self._script_text(arrival, customer, candidate, channel=channel)
                    task = CrmTask(
                        customer_id=customer.id,
                        assigned_seller_user_id=getattr(manager, "id", None),
                        assigned_seller_external_id=_seller_external_id(manager),
                        assigned_seller_name=getattr(manager, "full_name", None),
                        store_id=arrival.physical_store_id,
                        store_name=arrival.display_store_name,
                        work_date=work_date,
                        due_date=datetime.combine(work_date, time(hour=20), tzinfo=timezone.utc),
                        priority=int(candidate["priority_rank"]),
                        crm_group=CRM_NEW_ARRIVAL_GROUP,
                        reason=candidate["selection_reason"],
                        seller_action=self._seller_action(arrival, channel),
                        script_key=f"new_arrival_{channel.lower()}_{candidate['priority']}",
                        script_text=script_text,
                        status="new",
                        campaign_id=CRM_NEW_ARRIVAL_CAMPAIGN_ID,
                        campaign_name=CRM_NEW_ARRIVAL_CAMPAIGN_NAME,
                        source=CRM_NEW_ARRIVAL_SOURCE,
                        source_row_id=arrival.arrival_id,
                        source_idempotency_key=idempotency_key,
                        source_payload={
                            "task_type": "NEW_ARRIVAL",
                            "arrival_id": arrival.arrival_id,
                            "physical_store": arrival.physical_store,
                            "physical_store_id": arrival.physical_store_id,
                            "crm_store": arrival.crm_store,
                            "brand": arrival.brand,
                            "selection_reason": candidate["selection_reason"],
                            "selection_reason_type": candidate["priority"],
                            "priority": candidate["priority"],
                            "priority_rank": candidate["priority_rank"],
                            "geo_status": candidate["geo_status"],
                            "channel": channel,
                            "goal": "Получить ответ, визит, онлайн-подбор или продажу по новому поступлению.",
                            "message_template_id": f"new_arrival_{channel.lower()}_{candidate['priority']}",
                            "approved_strategy": self._approved_strategy(channel, candidate),
                            "novelty_type": arrival.novelty_type,
                            "strength": arrival.strength,
                            "media_ids": arrival.media[:5],
                            "media": arrival.media[:5],
                            "items": arrival.items[:8],
                            "received_at": arrival.received_at.isoformat(),
                            "commercial_cooldown_days": COMMERCIAL_COOLDOWN_DAYS,
                            "ready_for_sale": True,
                            "auto_send": False,
                        },
                        created_by_user_id=getattr(actor, "id", None),
                        updated_at=datetime.now(timezone.utc),
                    )
                    if dry_run:
                        summary["tasks_previewed"] += 1
                        arrival_stats["tasks_previewed"] = arrival_stats.get("tasks_previewed", 0) + 1
                    else:
                        self.db.add(task)
                        await self.db.flush()
                        self.db.add(CrmTaskEvent(
                            task_id=task.id,
                            event_type="created_from_new_arrival_rule",
                            actor_user_id=getattr(actor, "id", None),
                            actor_name=self.crm_service._actor_name(actor),
                            previous_status=None,
                            next_status=task.status,
                            payload={
                                "arrival_id": arrival.arrival_id,
                                "brand": arrival.brand,
                                "crm_store": arrival.crm_store,
                                "priority": candidate["priority"],
                                "channel": channel,
                            },
                        ))
                        summary["created"] += 1
                        arrival_stats["created"] += 1
            except Exception as exc:
                summary["errors"].append({"arrival_id": arrival.arrival_id, "error": str(exc)})
                arrival_stats["errors"] += 1
            else:
                if dry_run:
                    summary["by_arrival"][arrival.arrival_id] = arrival_stats
                    continue
                await self._mark_arrival_events_processed(arrival)
            summary["by_arrival"][arrival.arrival_id] = arrival_stats

        if dry_run:
            await self.db.rollback()
        else:
            await self.db.commit()
        return summary

    async def _load_arrivals_from_events(self, *, received_since: datetime, limit: int) -> List[ArrivalGroup]:
        stmt = (
            select(ProductStockArrivalEvent, Product)
            .join(Product, Product.id == ProductStockArrivalEvent.product_id)
            .where(
                ProductStockArrivalEvent.processed_at.is_(None),
                ProductStockArrivalEvent.received_at >= received_since,
                ProductStockArrivalEvent.available_quantity > 0,
                # Only a primary supplier receipt may create a new-arrival
                # batch. Transfers remain availability data and are excluded.
                ProductStockArrivalEvent.source == "onec_purchase_receipt",
                Product.is_active.is_(True),
                product_eligible_filter(Product, func, and_),
            )
            .order_by(ProductStockArrivalEvent.received_at.desc(), Product.brand.asc().nullslast())
            .limit(limit * 120)
        )
        rows = (await self.db.execute(stmt)).all()
        product_ids = list({product.id for _event, product in rows})
        if not product_ids:
            return []
        stock_stmt = (
            select(ProductStock, Store)
            .join(Store, Store.external_id == ProductStock.store_id)
            .where(
                ProductStock.product_id.in_(product_ids),
                ProductStock.available_quantity > 0,
                Store.is_active.is_(True),
                Store.external_id.isnot(None),
                ~Store.name.ilike("%склад%"),
                ~Store.name.ilike("%основной%"),
                ~Store.name.ilike("%меганом%"),
            )
        )
        stock_by_product: Dict[Any, List[tuple[ProductStock, Store]]] = defaultdict(list)
        for stock, store in (await self.db.execute(stock_stmt)).all():
            stock_by_product[stock.product_id].append((stock, store))
        grouped: Dict[str, Dict[str, Any]] = {}
        for event, product in rows:
            available_stores = stock_by_product.get(product.id) or []
            if not available_stores:
                continue
            for stock, store in available_stores:
                crm_store = _crm_store_key(store.name, store.city, event.received_at)
                if not crm_store:
                    continue
                brand = _clean_text(product.brand) or "GLAME"
                physical_store = _display_store_name(store.name, event.received_at) or store.name
                payload = event.source_payload if isinstance(event.source_payload, dict) else {}
                batch_ref = _clean_text(payload.get("batch_id")) or _clean_text(event.source_sync_id) or event.received_at.date().isoformat()
                key = f"{crm_store}:{store.external_id}:{brand}:{batch_ref}"
                group = grouped.setdefault(key, {
                    "arrival_id": key.replace(" ", "_"),
                    "physical_store": physical_store,
                    "physical_store_id": store.external_id,
                    "crm_store": crm_store,
                    "display_store_name": physical_store,
                    "brand": brand,
                    "received_at": event.received_at,
                    "items": [],
                    "media": [],
                    "product_uuids": [],
                    "event_ids": [],
                    "min_price": int(product.price or 0),
                    "categories": set(),
                    "event_types": set(),
                })
                if event.received_at and event.received_at > group["received_at"]:
                    group["received_at"] = event.received_at
                price = int(product.price or 0)
                if price and (not group["min_price"] or price < group["min_price"]):
                    group["min_price"] = price
                if product.category:
                    group["categories"].add(product.category)
                group["event_types"].add(event.event_type)
                media = _first_images(product, limit=2)
                for item in media:
                    if item not in group["media"]:
                        group["media"].append(item)
                if product.id not in group["product_uuids"]:
                    group["product_uuids"].append(product.id)
                if event.id not in group["event_ids"]:
                    group["event_ids"].append(event.id)
                group["items"].append({
                    "product_id": str(product.id),
                    "external_id": product.external_id,
                    "sku": product.article or product.external_code or product.external_id,
                    "name": product.name,
                    "brand": brand,
                    "category": product.category,
                    "price": price,
                    "qty": float(stock.available_quantity or 0),
                    "delta_qty": float(event.delta_quantity or 0),
                    "media": media,
                    "first_time_in_store": event.event_type == "PRIMARY_RECEIPT",
                    "restock": False,
                })
        arrivals: List[ArrivalGroup] = []
        for group in grouped.values():
            if len(group["items"]) < 2 and not group["media"]:
                continue
            event_types = set(group["event_types"])
            novelty_type = "NEW_TO_STORE" if "NEW_TO_STORE" in event_types else "RESTOCK" if "RESTOCK" in event_types else "REPLENISHMENT"
            strength = self._arrival_strength(group["brand"], group["items"], group["media"])
            arrivals.append(ArrivalGroup(
                arrival_id=group["arrival_id"],
                physical_store=group["physical_store"],
                physical_store_id=group["physical_store_id"],
                crm_store=group["crm_store"],
                display_store_name=group["display_store_name"],
                brand=group["brand"],
                received_at=group["received_at"],
                items=group["items"][:12],
                media=group["media"][:8],
                min_price=int(group["min_price"] or 0),
                categories=sorted(group["categories"]),
                product_uuids=group["product_uuids"],
                event_ids=group["event_ids"],
                novelty_type=novelty_type,
                strength=strength,
            ))
        arrivals.sort(key=lambda item: (item.received_at, len(item.items)), reverse=True)
        return arrivals[:limit]

    async def _load_arrivals(self, *, received_since: datetime, limit: int) -> List[ArrivalGroup]:
        stmt = (
            select(ProductStock, Product, Store)
            .join(Product, Product.id == ProductStock.product_id)
            .join(Store, Store.external_id == ProductStock.store_id)
            .where(
                ProductStock.available_quantity > 0,
                ProductStock.last_synced_at >= received_since,
                Product.is_active.is_(True),
                Store.is_active.is_(True),
                Store.external_id.isnot(None),
                ~Store.name.ilike("%склад%"),
                ~Store.name.ilike("%основной%"),
                product_eligible_filter(Product, func, and_),
            )
            .order_by(ProductStock.last_synced_at.desc(), Store.name.asc(), Product.brand.asc().nullslast())
            .limit(limit * 80)
        )
        rows = (await self.db.execute(stmt)).all()
        grouped: Dict[str, Dict[str, Any]] = {}
        for stock, product, store in rows:
            crm_store = _crm_store_key(store.name, store.city, stock.last_synced_at)
            if not crm_store:
                continue
            brand = _clean_text(product.brand) or "GLAME"
            physical_store = _display_store_name(store.name, stock.last_synced_at) or store.name
            key = f"{crm_store}:{store.external_id}:{brand}:{stock.last_synced_at.date().isoformat()}"
            group = grouped.setdefault(key, {
                "arrival_id": key.replace(" ", "_"),
                "physical_store": physical_store,
                "physical_store_id": store.external_id,
                "crm_store": crm_store,
                "display_store_name": physical_store,
                "brand": brand,
                "received_at": stock.last_synced_at,
                "items": [],
                "media": [],
                "product_uuids": [],
                "min_price": int(product.price or 0),
                "categories": set(),
            })
            if stock.last_synced_at and stock.last_synced_at > group["received_at"]:
                group["received_at"] = stock.last_synced_at
            price = int(product.price or 0)
            if price and (not group["min_price"] or price < group["min_price"]):
                group["min_price"] = price
            if product.category:
                group["categories"].add(product.category)
            media = _first_images(product, limit=2)
            for item in media:
                if item not in group["media"]:
                    group["media"].append(item)
            group["product_uuids"].append(product.id)
            group["items"].append({
                "product_id": str(product.id),
                "external_id": product.external_id,
                "sku": product.article or product.external_code or product.external_id,
                "name": product.name,
                "brand": brand,
                "category": product.category,
                "price": price,
                "qty": float(stock.available_quantity or 0),
                "media": media,
                "first_time_in_store": bool(product.created_at and product.created_at >= received_since),
                "restock": bool(stock.available_quantity and stock.available_quantity > 0),
            })
        arrivals: List[ArrivalGroup] = []
        for group in grouped.values():
            if len(group["items"]) < 2 and not group["media"]:
                continue
            novelty_type = self._novelty_type(group["items"], group["received_at"], received_since)
            strength = self._arrival_strength(group["brand"], group["items"], group["media"])
            arrivals.append(ArrivalGroup(
                arrival_id=group["arrival_id"],
                physical_store=group["physical_store"],
                physical_store_id=group["physical_store_id"],
                crm_store=group["crm_store"],
                display_store_name=group["display_store_name"],
                brand=group["brand"],
                received_at=group["received_at"],
                items=group["items"][:12],
                media=group["media"][:8],
                min_price=int(group["min_price"] or 0),
                categories=sorted(group["categories"]),
                product_uuids=group["product_uuids"],
                event_ids=[],
                novelty_type=novelty_type,
                strength=strength,
            ))
        arrivals.sort(key=lambda item: (item.received_at, len(item.items)), reverse=True)
        return arrivals[:limit]

    async def _candidates_for_arrival(self, arrival: ArrivalGroup, *, limit: int) -> List[Dict[str, Any]]:
        candidates: Dict[Any, Dict[str, Any]] = {}
        product_ids = list(getattr(arrival, "product_uuids", []) or [])
        if product_ids:
            subscription_result = await self.db.execute(
                select(ProductArrivalSubscription, User)
                .join(User, User.id == ProductArrivalSubscription.user_id)
                .where(
                    ProductArrivalSubscription.status == "pending",
                    ProductArrivalSubscription.user_id.isnot(None),
                    ProductArrivalSubscription.variant_product_id.in_(product_ids),
                    User.is_customer.is_(True),
                )
                .limit(limit)
            )
            for subscription, user in subscription_result.all():
                candidates[user.id] = {
                    "customer": user,
                    "priority": "P1",
                    "priority_rank": 1,
                    "geo_status": self._geo_status(user, arrival),
                    "selection_reason": f"Клиент оставлял заявку «сообщить о поступлении» по товару {subscription.variant_label or arrival.brand}.",
                }

        brand_rows = await self._purchase_candidates(arrival, by_brand=True, limit=limit * 3)
        for user, stats in brand_rows:
            if user.id in candidates:
                continue
            candidates[user.id] = {
                "customer": user,
                "priority": "P2",
                "priority_rank": 2,
                "geo_status": self._geo_status(user, arrival),
                "selection_reason": (
                    f"Покупал(а) бренд {arrival.brand}: чеков {int(stats['checks'] or 0)}, "
                    f"сумма {int(stats['amount'] or 0) // 100:,} ₽, последняя покупка {stats['last_date'].date().isoformat() if stats.get('last_date') else '—'}."
                ).replace(",", " "),
            }

        category_rows = await self._purchase_candidates(arrival, by_brand=False, limit=limit * 4)
        for user, stats in category_rows:
            if len(candidates) >= limit:
                break
            if user.id in candidates:
                continue
            candidates[user.id] = {
                "customer": user,
                "priority": "P3",
                "priority_rank": 3,
                "geo_status": self._geo_status(user, arrival),
                "selection_reason": (
                    f"Покупки соответствуют категории нового поступления ({', '.join(arrival.categories[:2]) or 'украшения'}): "
                    f"чеков {int(stats['checks'] or 0)}, сумма {int(stats['amount'] or 0) // 100:,} ₽."
                ).replace(",", " "),
            }

        if len(candidates) < min(limit, MIN_RELEVANT_TASKS_BEFORE_WARM_EXPANSION):
            vip_rows = await self._vip_candidates(arrival, limit=limit * 2)
            for user, stats in vip_rows:
                if len(candidates) >= limit:
                    break
                if user.id in candidates:
                    continue
                candidates[user.id] = {
                    "customer": user,
                    "priority": "P4",
                    "priority_rank": 4,
                    "geo_status": self._geo_status(user, arrival),
                    "selection_reason": (
                        f"VIP/ценный клиент {arrival.display_store_name}: история покупок соответствует уровню поступления, "
                        f"чеков {int(stats['checks'] or 0)}, сумма {int(stats['amount'] or 0) // 100:,} ₽."
                    ).replace(",", " "),
                }

        if len(candidates) < min(limit, MIN_RELEVANT_TASKS_BEFORE_WARM_EXPANSION) and arrival.strength != "WEAK_BRAND_TRIGGER":
            warm_rows = await self._warm_expansion_candidates(arrival, limit=limit * 2)
            for user, stats in warm_rows:
                if len(candidates) >= limit:
                    break
                if user.id in candidates:
                    continue
                candidates[user.id] = {
                    "customer": user,
                    "priority": "P5",
                    "priority_rank": 5,
                    "geo_status": self._geo_status(user, arrival),
                    "selection_reason": (
                        f"Тёплый клиент {arrival.display_store_name}: недавняя активная покупка и уровень чека подходят под поступление, "
                        f"последняя покупка {stats['last_date'].date().isoformat() if stats.get('last_date') else '—'}."
                    ),
                }

        values = list(candidates.values())
        values.sort(key=lambda item: (int(item["priority_rank"]), -int(getattr(item["customer"], "total_spent", 0) or 0)))
        return values[:limit]

    async def _purchase_candidates(self, arrival: ArrivalGroup, *, by_brand: bool, limit: int) -> List[tuple[User, Dict[str, Any]]]:
        conditions = [PurchaseHistory.total_amount > 0]
        if by_brand:
            conditions.append(func.lower(func.coalesce(PurchaseHistory.brand, "")) == arrival.brand.lower())
        else:
            if not arrival.categories:
                return []
            conditions.append(PurchaseHistory.category.in_(arrival.categories))
            if arrival.min_price:
                conditions.append(PurchaseHistory.total_amount >= int(arrival.min_price * 0.6))
        result = await self.db.execute(
            select(
                User,
                func.count(func.distinct(PurchaseHistory.document_id_1c)).label("checks"),
                func.sum(PurchaseHistory.total_amount).label("amount"),
                func.max(PurchaseHistory.purchase_date).label("last_date"),
            )
            .join(PurchaseHistory, PurchaseHistory.user_id == User.id)
            .where(User.is_customer.is_(True), *conditions)
            .group_by(User.id)
            .order_by(func.sum(PurchaseHistory.total_amount).desc().nullslast(), func.max(PurchaseHistory.purchase_date).desc().nullslast())
            .limit(limit)
        )
        rows: List[tuple[User, Dict[str, Any]]] = []
        for user, checks, amount, last_date in result.all():
            if self._customer_crm_store(user) != arrival.crm_store:
                continue
            rows.append((user, {"checks": checks, "amount": amount, "last_date": last_date}))
        return rows

    async def _vip_candidates(self, arrival: ArrivalGroup, *, limit: int) -> List[tuple[User, Dict[str, Any]]]:
        min_amount = int(arrival.min_price * 0.6) if arrival.min_price else 0
        result = await self.db.execute(
            select(
                User,
                func.count(func.distinct(PurchaseHistory.document_id_1c)).label("checks"),
                func.sum(PurchaseHistory.total_amount).label("amount"),
                func.max(PurchaseHistory.purchase_date).label("last_date"),
            )
            .join(PurchaseHistory, PurchaseHistory.user_id == User.id)
            .where(
                User.is_customer.is_(True),
                User.total_spent >= 300_000_00,
                PurchaseHistory.total_amount >= min_amount,
            )
            .group_by(User.id)
            .order_by(func.sum(PurchaseHistory.total_amount).desc().nullslast())
            .limit(limit)
        )
        rows: List[tuple[User, Dict[str, Any]]] = []
        for user, checks, amount, last_date in result.all():
            if self._customer_crm_store(user) != arrival.crm_store:
                continue
            rows.append((user, {"checks": checks, "amount": amount, "last_date": last_date}))
        return rows

    async def _warm_expansion_candidates(self, arrival: ArrivalGroup, *, limit: int) -> List[tuple[User, Dict[str, Any]]]:
        min_amount = int(arrival.min_price * 0.5) if arrival.min_price else 0
        since = datetime.now(timezone.utc) - timedelta(days=365)
        result = await self.db.execute(
            select(
                User,
                func.count(func.distinct(PurchaseHistory.document_id_1c)).label("checks"),
                func.sum(PurchaseHistory.total_amount).label("amount"),
                func.max(PurchaseHistory.purchase_date).label("last_date"),
            )
            .join(PurchaseHistory, PurchaseHistory.user_id == User.id)
            .where(
                User.is_customer.is_(True),
                PurchaseHistory.purchase_date >= since,
                PurchaseHistory.total_amount >= min_amount,
            )
            .group_by(User.id)
            .having(func.count(func.distinct(PurchaseHistory.document_id_1c)) >= 2)
            .order_by(func.max(PurchaseHistory.purchase_date).desc().nullslast(), func.sum(PurchaseHistory.total_amount).desc().nullslast())
            .limit(limit)
        )
        rows: List[tuple[User, Dict[str, Any]]] = []
        for user, checks, amount, last_date in result.all():
            if self._customer_crm_store(user) != arrival.crm_store:
                continue
            rows.append((user, {"checks": checks, "amount": amount, "last_date": last_date}))
        return rows

    def _customer_crm_store(self, user: User) -> Optional[str]:
        return (
            _crm_store_key(getattr(user, "preferred_store_name", None), getattr(user, "city", None))
            or _crm_store_key(getattr(user, "secondary_store_name", None), getattr(user, "city", None))
            or _crm_store_key(None, getattr(user, "city", None))
        )

    def _geo_status(self, user: User, arrival: ArrivalGroup) -> str:
        city = _normalize(getattr(user, "city", None))
        if not city:
            return "UNKNOWN"
        if arrival.crm_store == "YALTA":
            if "ялта" in city or "крым" in city:
                return "LOCAL"
            return "UNKNOWN"
        if "симфер" in city or "крым" in city:
            return "LOCAL"
        return "NON_LOCAL"

    async def _block_reason(self, customer: User, arrival: ArrivalGroup, work_date: date, *, candidate: Dict[str, Any]) -> Optional[str]:
        prefs = customer.preferences if isinstance(customer.preferences, dict) else {}
        if prefs.get("do_not_contact") or prefs.get("do_not_disturb") or prefs.get("open_service_case"):
            return "do_not_contact"
        open_service_case = await self.db.scalar(
            select(CrmServiceCase.id).where(
                CrmServiceCase.customer_id == customer.id,
                CrmServiceCase.status.in_(["open", "in_progress", "pending"]),
            ).limit(1)
        )
        if open_service_case:
            return "open_service_case"
        open_customer_request = await self.db.scalar(
            select(CustomerRequest.id).where(
                CustomerRequest.client_id == customer.id,
                CustomerRequest.request_type.in_(["REPAIR_CUSTOMER", "RETURN", "EXCHANGE", "SERVICE_CLAIM"]),
                CustomerRequest.status.in_(["WAITING", "ORDERED", "ARRIVED_STORE", "IN_PROGRESS", "NEW", "UNDER_REVIEW", "DECISION_READY", "IN_REPAIR", "READY", "CUSTOMER_NOTIFIED"]),
            ).limit(1)
        )
        if open_customer_request:
            return "open_customer_request"
        open_task = await self.db.scalar(
            select(CrmTask.id).where(
                CrmTask.customer_id == customer.id,
                CrmTask.status.in_(list(OPEN_STATUSES)),
            ).limit(1)
        )
        if open_task:
            return "open_crm_task"
        active_message = await self.db.scalar(
            select(CustomerMessage.id).where(
                CustomerMessage.user_id == customer.id,
                CustomerMessage.created_at >= datetime.now(timezone.utc) - timedelta(days=3),
                or_(
                    CustomerMessage.status.in_(["new", "pending", "in_progress"]),
                    CustomerMessage.payload["active_conversation"].astext == "true",
                ),
            ).limit(1)
        )
        if active_message:
            return "active_conversation"
        if candidate.get("priority") == "P1":
            return None
        cooldown_start = work_date - timedelta(days=COMMERCIAL_COOLDOWN_DAYS)
        recent_silent = await self.db.scalar(
            select(CrmTask.id).where(
                CrmTask.customer_id == customer.id,
                CrmTask.work_date >= cooldown_start,
                CrmTask.crm_group.in_([CRM_NEW_ARRIVAL_GROUP, "segmented_message", "personal_message"]),
                CrmTask.seller_outcome.in_(["no_answer", "sent_no_reply"]),
            ).limit(1)
        )
        if recent_silent:
            return "commercial_cooldown"
        return None

    async def _mark_arrival_events_processed(self, arrival: ArrivalGroup) -> None:
        if not arrival.event_ids:
            return
        now = datetime.now(timezone.utc)
        result = await self.db.execute(select(ProductStockArrivalEvent).where(ProductStockArrivalEvent.id.in_(arrival.event_ids)))
        for event in result.scalars().all():
            if event.processed_at is None:
                event.processed_at = now

    async def _arrival_recently_used(self, arrival: ArrivalGroup, work_date: date) -> bool:
        """Avoid treating a nightly stock sync as a new commercial reason every day."""
        product_ids = {str(item.get("product_id")) for item in arrival.items if item.get("product_id")}
        if not product_ids:
            return False
        since = work_date - timedelta(days=COMMERCIAL_COOLDOWN_DAYS)
        result = await self.db.execute(
            select(CrmTask.source_payload).where(
                CrmTask.source == CRM_NEW_ARRIVAL_SOURCE,
                CrmTask.work_date >= since,
                CrmTask.source_payload["brand"].astext == arrival.brand,
                CrmTask.source_payload["crm_store"].astext == arrival.crm_store,
                or_(
                    CrmTask.seller_outcome.is_(None),
                    CrmTask.seller_outcome != "archived_initial_wave",
                ),
            )
        )
        for payload in result.scalars().all():
            items = payload.get("items") if isinstance(payload, dict) else []
            if not isinstance(items, list):
                continue
            previous_product_ids = {str(item.get("product_id")) for item in items if isinstance(item, dict) and item.get("product_id")}
            if product_ids & previous_product_ids:
                return True
        return False

    def _novelty_type(self, items: List[Dict[str, Any]], received_at: datetime, received_since: datetime) -> str:
        first_time_count = sum(1 for item in items if item.get("first_time_in_store"))
        if first_time_count >= max(1, len(items) // 2):
            return "NEW_TO_STORE"
        if received_at >= received_since and first_time_count > 0:
            return "NEW_COLLECTION"
        if any(item.get("restock") for item in items):
            return "RESTOCK"
        return "REPLENISHMENT"

    def _arrival_strength(self, brand: str, items: List[Dict[str, Any]], media: List[str]) -> str:
        brand_norm = _normalize(brand)
        known_brand = bool(brand_norm and brand_norm not in {"glame", "без бренда", "no name", "noname"})
        expensive_items = sum(1 for item in items if _safe_int(item.get("price")) >= 15_000_00)
        if known_brand and (len(items) >= 6 or expensive_items >= 2 or len(media) >= 3):
            return "STRONG_BRAND_TRIGGER"
        if known_brand or len(media) >= 3 or expensive_items:
            return "MEDIUM_BRAND_TRIGGER"
        return "WEAK_BRAND_TRIGGER"

    def _approved_strategy(self, channel: str, candidate: Dict[str, Any]) -> str:
        if channel == "CALL":
            return "C"
        if candidate.get("geo_status") in {"NON_LOCAL", "UNKNOWN"}:
            return "D"
        return "A"

    async def _staff_users(self) -> List[User]:
        result = await self.db.execute(
            select(User).where(User.is_customer.is_(False), User.role.in_(["seller", "manager", "admin"]), User.full_name.isnot(None))
        )
        return list(result.scalars().all())

    def _manager_for_crm_store(self, crm_store: str, staff: Iterable[User]) -> Optional[User]:
        target = _normalize(CRM_STORE_MANAGER_NAMES.get(crm_store))
        if not target:
            return None
        for user in staff:
            if _normalize(user.full_name) == target:
                return user
        return None

    def _channel_for(self, candidate: Dict[str, Any]) -> str:
        if candidate["priority"] == "P1":
            return "MESSAGE"
        if candidate["geo_status"] in {"NON_LOCAL", "UNKNOWN"}:
            return "MESSAGE"
        if candidate["priority"] == "P2" and int(getattr(candidate["customer"], "total_spent", 0) or 0) >= 100_000_00:
            return "CALL"
        return "MESSAGE"

    def _seller_action(self, arrival: ArrivalGroup, channel: str) -> str:
        if channel == "CALL":
            return (
                f"Позвонить клиенту по новому поступлению {arrival.brand}. "
                "Цель — получить живой интерес, договориться о визите или онлайн-подборе. "
                "Перед приглашением проверить наличие; если клиент не в городе — предложить фото/видео и дистанционное оформление."
            )
        return (
            f"Отправить сообщение по новому поступлению {arrival.brand}. "
            "Если есть визуалы, приложить 3–5 лучших фото/короткое видео сразу, не спрашивая разрешение на отправку фото. "
            "Не отправлять весь каталог. Зафиксировать ответ и следующий шаг."
        )

    def _script_text(self, arrival: ArrivalGroup, customer: User, candidate: Dict[str, Any], *, channel: str) -> str:
        name = _first_name(customer)
        consultant = CRM_STORE_MANAGER_NAMES.get(arrival.crm_store, "GLAME").split()[1] if arrival.crm_store in CRM_STORE_MANAGER_NAMES else "GLAME"
        store_label = arrival.display_store_name
        media_note = "Визуал: приложить 3–5 фото/короткое видео из карточки задачи сразу." if arrival.media else "Визуал пока не найден: перед отправкой добавьте фото/видео товара или выберите звонок."
        if channel == "CALL":
            return (
                f"{name}, здравствуйте! Это {consultant} из GLAME, {store_label}.\n"
                f"Звоню, потому что у нас пришло новое поступление {arrival.brand}. "
                "Есть несколько украшений, которые действительно лучше увидеть вживую.\n\n"
                "Если клиент заинтересовался: предложить визит, отправить фото после звонка или собрать онлайн-подбор.\n"
                "Если клиент не в городе: предложить видео/фото, дистанционный подбор, оформление и доставку."
            )
        if candidate["priority"] == "P2":
            return (
                f"{name}, здравствуйте! Это {consultant} из GLAME, {store_label}.\n"
                f"В {store_label} пришло новое поступление {arrival.brand}.\n"
                "Вы уже выбирали этот бренд у нас, поэтому показываем Вам поступление до общего релиза.\n"
                "Оставлю здесь несколько вещей, которые особенно хорошо выглядят вживую.\n\n"
                "Если что-то зацепит — напишите, посмотрим наличие и оставим к примерке.\n\n"
                f"{media_note}"
            )
        if candidate["geo_status"] in {"NON_LOCAL", "UNKNOWN"}:
            return (
                f"{name}, здравствуйте! Это {consultant} из GLAME.\n"
                f"У нас пришло новое поступление {arrival.brand}. "
                "Покажу несколько новых вещей — если что-то откликнется, можем показать подробнее по видео, "
                "собрать онлайн-подбор и оформить дистанционно.\n\n"
                f"{media_note}"
            )
        return (
            f"{name}, здравствуйте! Это {consultant} из GLAME, {store_label}.\n"
            "В магазин пришло новое поступление, и там есть несколько украшений, которые действительно стоит увидеть.\n"
            "Оставлю здесь самые сильные позиции.\n\n"
            f"{media_note}"
        )
