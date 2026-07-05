"""
Единая синхронизация истории покупок и бонусных баллов по номеру карты/телефона.

Использование:
  cd backend
  python3 sync_customer_sales_and_points.py 79787891424
  python3 sync_customer_sales_and_points.py 79787891424 --start 2025-03-01 --end 2026-04-30
  python3 sync_customer_sales_and_points.py 79787891424 --merge
"""
import argparse
import asyncio
import httpx
import os
import re
import sys
from datetime import datetime, time, timezone
from typing import Any, Dict, Optional

from sqlalchemy import and_, func, or_, select

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.connection import AsyncSessionLocal
from app.models.loyalty_transaction import LoyaltyTransaction
from app.models.product import Product
from app.models.purchase_history import PurchaseHistory
from app.models.user import User
from app.services.customer_analytics_service import CustomerAnalyticsService
from app.services.onec_sales_service import OneCSalesService
from app.services.onec_customers_service import OneCCustomersService
from app.services.purchase_product_fields import derive_purchase_brand, derive_purchase_category
from app.services.sales_product_link_service import SalesProductLinkService


DEFAULT_LIMIT = 10000
ZERO_GUID = "00000000-0000-0000-0000-000000000000"


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 11 and digits.startswith("8"):
        return "7" + digits[1:]
    if len(digits) == 10:
        return "7" + digits
    return digits


def parse_date(value: Optional[str], end: bool = False) -> Optional[datetime]:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = datetime.combine(dt.date(), time.max if end else time.min, tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_1c_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_kopecks(amount: Any) -> int:
    try:
        return int(round(float(amount or 0) * 100))
    except (TypeError, ValueError):
        return 0


async def find_or_create_user(db, onec: OneCCustomersService, phone: str) -> User:
    normalized = normalize_phone(phone)
    stmt = select(User).where(
        User.is_customer == True,
        or_(User.phone == normalized, User.discount_card_number == normalized),
    )
    result = await db.execute(stmt)
    user = result.scalars().first()

    card = None
    if not user or not user.customer_id_1c or not user.discount_card_id_1c:
        card = await find_card_by_phone(onec, normalized, phone)

    if not user and not card:
        raise RuntimeError(f"Покупатель с телефоном/картой {phone} не найден ни в БД, ни в 1С")

    if not user:
        user = User(
            phone=normalized,
            discount_card_number=normalized,
            discount_card_id_1c=card.get("Ref_Key"),
            customer_id_1c=card.get("ВладелецКарты_Key"),
            full_name=card.get("Description") or normalized,
            role="customer",
            is_customer=True,
        )
        db.add(user)
        await db.flush()
    elif card:
        user.phone = normalized
        user.discount_card_number = normalized
        user.discount_card_id_1c = user.discount_card_id_1c or card.get("Ref_Key")
        user.customer_id_1c = user.customer_id_1c or card.get("ВладелецКарты_Key")
        if not user.full_name:
            user.full_name = card.get("Description")

    await db.commit()
    return user


async def find_card_by_phone(onec: OneCCustomersService, normalized: str, raw_phone: str) -> Optional[Dict[str, Any]]:
    phones = {normalized, normalize_phone(raw_phone), str(raw_phone or "").strip()}
    phones.discard("")

    for phone in phones:
        try:
            card = await onec.get_customer_by_phone(phone)
            if card:
                return card
        except Exception as e:
            print(f"Предупреждение: поиск карты через OData filter упал для {phone}: {e}")

    print("Ищу карту постранично без OData filter...")
    offset = 0
    batch_size = 1000
    while True:
        cards = await onec.fetch_discount_cards(limit=batch_size, offset=offset)
        if not cards:
            return None

        for card in cards:
            card_phone = normalize_phone(card.get("КодКартыШтрихкод") or "")
            if card_phone and card_phone in phones:
                return card

        if len(cards) < batch_size:
            return None
        offset += len(cards)


async def resolve_product(db, onec: OneCCustomersService, purchase: Dict[str, Any], cache: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    product_key = purchase.get("Номенклатура_Key")
    characteristic_key = purchase.get("Характеристика_Key")
    if characteristic_key == ZERO_GUID:
        characteristic_key = None

    product = None
    if product_key and characteristic_key:
        result = await db.execute(
            select(Product).where(Product.external_id == f"{product_key}#{characteristic_key}").limit(1)
        )
        product = result.scalars().first()

    if not product and product_key:
        result = await db.execute(select(Product).where(Product.external_id == product_key).limit(1))
        product = result.scalars().first()

    if product:
        product_name = product.name
        return {
            "product": product,
            "article": product.article or product.external_code,
            "barcode": product.barcode,
            "name": product_name,
            "category": derive_purchase_category(product_name, product.category),
            "brand": derive_purchase_brand(product_name, product.brand, product.category),
            "details": {},
        }

    product_details = None
    if product_key:
        product_details = cache.get(product_key)
        if product_details is None:
            product_details = await onec.fetch_product_details(product_key) or {}
            cache[product_key] = product_details

    product_article = (product_details or {}).get("article") or (product_details or {}).get("code")
    product_barcode = (product_details or {}).get("barcode")
    product_name = purchase.get("Номенклатура_Description") or (product_details or {}).get("name")
    product_category = (product_details or {}).get("category")
    product_brand = (product_details or {}).get("brand")

    if not product and product_article:
        result = await db.execute(
            select(Product)
            .where(or_(Product.article == product_article, Product.external_code == product_article))
            .limit(1)
        )
        product = result.scalars().first()

    if not product and product_barcode:
        result = await db.execute(select(Product).where(Product.barcode == product_barcode).limit(1))
        product = result.scalars().first()

    if product:
        product_article = product_article or product.article or product.external_code
        product_barcode = product_barcode or product.barcode
        product_name = product.name or product_name
        product_category = derive_purchase_category(product_name, product.category or product_category)
        product_brand = derive_purchase_brand(product_name, product.brand or product_brand, product.category)
    else:
        raw_product_category = product_category
        product_category = derive_purchase_category(product_name, raw_product_category)
        product_brand = derive_purchase_brand(product_name, product_brand, raw_product_category)

    return {
        "product": product,
        "article": product_article,
        "barcode": product_barcode,
        "name": product_name,
        "category": product_category,
        "brand": product_brand,
        "details": product_details or {},
    }


async def resolve_document_date(
    onec: OneCCustomersService,
    document_type: Optional[str],
    document_id: Optional[str],
    cache: Dict[str, Optional[datetime]],
) -> Optional[datetime]:
    if not document_type or not document_id:
        return None

    doc_name = str(document_type).split(".")[-1]
    if not doc_name.startswith("Document_"):
        return None

    cache_key = f"{doc_name}:{document_id}"
    if cache_key in cache:
        return cache[cache_key]

    cache[cache_key] = None
    if not onec.client:
        return None

    try:
        url = f"{onec.api_url.rstrip('/')}/{doc_name}(guid'{document_id}')"
        response = await onec.client.get(url)
        response.raise_for_status()
        document = response.json()
        date_value = document.get("Date")
        if date_value:
            cache[cache_key] = parse_1c_datetime(date_value)
    except Exception as e:
        print(f"Предупреждение: не удалось получить дату документа {doc_name} {document_id}: {e}")

    return cache[cache_key]


async def resolve_document_store(
    onec: OneCCustomersService,
    document_type: Optional[str],
    document_id: Optional[str],
    cache: Dict[str, Optional[str]],
) -> Optional[str]:
    if not document_type or not document_id:
        return None

    doc_name = str(document_type).split(".")[-1]
    if not doc_name.startswith("Document_"):
        return None

    cache_key = f"{doc_name}:{document_id}"
    if cache_key in cache:
        return cache[cache_key]

    cache[cache_key] = None
    if not onec.client:
        return None

    try:
        url = f"{onec.api_url.rstrip('/')}/{doc_name}(guid'{document_id}')"
        response = await onec.client.get(url)
        response.raise_for_status()
        document = response.json()
        for field in ("Склад_Key", "СтруктурнаяЕдиница_Key", "Магазин_Key"):
            value = document.get(field)
            if value:
                cache[cache_key] = value
                break
    except Exception as e:
        print(f"Предупреждение: не удалось получить магазин документа {doc_name} {document_id}: {e}")

    return cache[cache_key]


async def upsert_purchase(db, user: User, onec: OneCCustomersService, purchase: Dict[str, Any], product_cache: Dict[str, Dict[str, Any]]) -> str:
    document_id = purchase.get("Документ") or purchase.get("Recorder")
    product_key = purchase.get("Номенклатура_Key")
    period = purchase.get("Period")
    if not document_id or not period:
        return "skipped"

    document_type = purchase.get("Документ_Type") or purchase.get("Recorder_Type")
    document_date = None
    document_cache = product_cache.setdefault("__document_dates__", {})
    if "ВводНачальныхОстатков" in str(document_type or ""):
        document_date = await resolve_document_date(onec, document_type, document_id, document_cache)
    purchase_date = document_date or parse_1c_datetime(period)
    store_id_1c = purchase.get("Склад_Key")
    if not store_id_1c and "ОтчетОРозничныхПродажах" in str(document_type or ""):
        store_cache = product_cache.setdefault("__document_stores__", {})
        store_id_1c = await resolve_document_store(onec, document_type, document_id, store_cache)
    amount_kopecks = to_kopecks(purchase.get("Сумма", 0))
    if amount_kopecks == 0:
        return "skipped"
    quantity = int(float(purchase.get("Количество") or 1))
    price_kopecks = amount_kopecks // quantity if quantity > 0 else 0
    linked = await resolve_product(db, onec, purchase, product_cache)

    conditions = [
        PurchaseHistory.user_id == user.id,
        func.date(PurchaseHistory.purchase_date) == purchase_date.date(),
        PurchaseHistory.document_id_1c == document_id,
    ]
    if product_key:
        conditions.append(PurchaseHistory.product_id_1c == product_key)
    else:
        conditions.append(PurchaseHistory.product_id_1c.is_(None))

    result = await db.execute(select(PurchaseHistory).where(and_(*conditions)).order_by(PurchaseHistory.created_at))
    existing = result.scalars().first()

    values = {
        "purchase_date": purchase_date,
        "document_id_1c": document_id,
        "store_id_1c": store_id_1c,
        "product_id": linked["product"].id if linked["product"] else None,
        "product_id_1c": product_key,
        "product_article": linked["article"],
        "product_name": linked["name"],
        "quantity": quantity,
        "price": price_kopecks,
        "total_amount": amount_kopecks,
        "category": linked["category"],
        "brand": linked["brand"],
        "sync_metadata": {
            **purchase,
            "resolved_barcode": linked["barcode"],
            "resolved_from_catalog": bool(linked["product"]),
        },
    }

    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        return "updated"

    db.add(PurchaseHistory(user_id=user.id, **values))
    # Flush immediately so duplicate lines later in the same sync batch are
    # visible to the SELECT above. With autoflush disabled, otherwise SQLAlchemy
    # may queue duplicate INSERTs and fail on uq_purchase_history_unique at commit.
    await db.flush()
    return "created"


async def sync_loyalty(db, onec: OneCCustomersService, user: User) -> Dict[str, Any]:
    current_balance = int(user.loyalty_points or 0)
    info = await onec.fetch_loyalty_balance(
        customer_key=user.customer_id_1c,
        discount_card_key=user.discount_card_id_1c,
    )
    if not info or info.get("balance") is None:
        return {"updated": False, "balance": current_balance}

    balance = int(info["balance"])
    if balance == current_balance:
        return {"updated": False, "balance": balance}

    user.loyalty_points = balance
    db.add(
        LoyaltyTransaction(
            user_id=user.id,
            transaction_type="sync_from_1c",
            points=balance - current_balance,
            balance_after=balance,
            reason="sync_from_1c",
            description="Синхронизация баланса из 1С",
            source="1c",
            source_id=info.get("source_id"),
        )
    )
    return {"updated": True, "balance": balance}


def _in_period(period: str, start_date: Optional[datetime], end_date: Optional[datetime]) -> bool:
    if not period:
        return False
    try:
        dt = parse_1c_datetime(period)
    except Exception:
        return True
    if start_date and dt < start_date:
        return False
    if end_date and dt > end_date:
        return False
    return True


def _purchase_document_id(purchase: Dict[str, Any]) -> str:
    return str(purchase.get("Документ") or purchase.get("Recorder") or "")


def _purchase_document_type(purchase: Dict[str, Any]) -> str:
    return str(purchase.get("Документ_Type") or purchase.get("Recorder_Type") or "")


def _purchase_period(purchase: Dict[str, Any]) -> Optional[datetime]:
    try:
        return parse_1c_datetime(str(purchase.get("Period") or ""))
    except Exception:
        return None


def _is_night_retail_report(items: list[Dict[str, Any]], document_type: str) -> bool:
    if "ОтчетОРозничныхПродажах" not in document_type:
        return False

    for item in items:
        dt = _purchase_period(item)
        if not dt:
            continue
        if dt.hour >= 20 or dt.hour <= 5:
            return True
    return False


async def fetch_sales_from_register_parsing(
    user: User,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    limit: int = DEFAULT_LIMIT,
) -> list[Dict[str, Any]]:
    """Быстрый путь из get_1c_sales_parsing.py: AccumulationRegister_Продажи -> RecordSet."""
    if not user.customer_id_1c:
        return []

    api_url = os.getenv("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata")
    api_token = os.getenv("ONEC_API_TOKEN", "your_1c_api_token_here")
    headers = {"Accept": "application/json", "Authorization": f"Basic {api_token}"}
    url = f"{api_url.rstrip('/')}/AccumulationRegister_Продажи"

    all_purchases: list[Dict[str, Any]] = []
    batch_size = int(os.getenv("ONEC_SALES_PARSE_BATCH_SIZE", "100"))
    skip = 0

    request_timeout = float(os.getenv("ONEC_SALES_REQUEST_TIMEOUT", "45"))
    async with httpx.AsyncClient(timeout=request_timeout, headers=headers) as client:
        while True:
            print(f"Запрос продаж из 1С: skip={skip}, найдено={len(all_purchases)}")
            response = await client.get(url, params={"$top": batch_size, "$skip": skip})
            if response.status_code != 200:
                print(f"  1С вернула статус {response.status_code}: {response.text[:300]}")
                break

            records = response.json().get("value", [])
            if not records:
                break

            for record in records:
                record_set = record.get("RecordSet", [])
                if not isinstance(record_set, list):
                    continue

                for movement in record_set:
                    if movement.get("Контрагент_Key", "") != user.customer_id_1c:
                        continue
                    period = movement.get("Period", "")
                    if not _in_period(period, start_date, end_date):
                        continue

                    all_purchases.append({
                        "Period": period,
                        "Сумма": movement.get("Сумма", 0),
                        "Количество": movement.get("Количество", 0),
                        "Номенклатура_Key": movement.get("Номенклатура_Key"),
                        "Номенклатура_Description": movement.get("Номенклатура_Description"),
                        "Характеристика_Key": movement.get("Характеристика_Key"),
                        "Документ": movement.get("Документ"),
                        "Документ_Type": movement.get("Документ_Type"),
                        "Склад_Key": movement.get("Склад_Key"),
                        "Контрагент_Key": movement.get("Контрагент_Key"),
                        "raw_1c_data": movement,
                    })

            skip += batch_size
            if len(all_purchases) >= limit:
                all_purchases = all_purchases[:limit]
                break
            if len(records) < batch_size:
                break

    unique = {}
    for purchase in all_purchases:
        key = (
            purchase.get("Документ") or "",
            purchase.get("Номенклатура_Key") or "",
            purchase.get("Характеристика_Key") or "",
            str(purchase.get("Period") or "")[:10],
        )
        unique[key] = purchase

    def parse_period(item: Dict[str, Any]) -> datetime:
        try:
            return parse_1c_datetime(item.get("Period", ""))
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    return sorted(unique.values(), key=parse_period, reverse=True)


async def fetch_sales_by_discount_card_recordtype(
    discount_card_key: Optional[str],
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    limit: int = DEFAULT_LIMIT,
) -> list[Dict[str, Any]]:
    """Продажи по ДК, включая Document_ВводНачальныхОстатков из регистра ДК."""
    if not discount_card_key:
        return []

    api_url = os.getenv("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata")
    api_token = os.getenv("ONEC_API_TOKEN", "your_1c_api_token_here")
    endpoint = os.getenv(
        "ONEC_SALES_BY_CARD_ENDPOINT",
        "/AccumulationRegister_ПродажиПоДисконтнымКартам_RecordType",
    )
    headers = {"Accept": "application/json", "Authorization": f"Basic {api_token}"}
    url = f"{api_url.rstrip('/')}{endpoint}"

    all_purchases: list[Dict[str, Any]] = []
    batch_size = int(os.getenv("ONEC_SALES_BY_CARD_BATCH_SIZE", "1000"))
    skip = 0

    request_timeout = float(os.getenv("ONEC_SALES_REQUEST_TIMEOUT", "45"))
    async with httpx.AsyncClient(timeout=request_timeout, headers=headers) as client:
        while True:
            print(f"Запрос продаж по ДК из 1С: skip={skip}, найдено={len(all_purchases)}")
            response = await client.get(url, params={"$top": batch_size, "$skip": skip})
            if response.status_code != 200:
                print(f"  1С вернула статус {response.status_code}: {response.text[:300]}")
                break

            records = response.json().get("value", [])
            if not records:
                break

            for record in records:
                candidates = record.get("RecordSet", [])
                if not isinstance(candidates, list):
                    candidates = []
                if not candidates:
                    candidates = [record]

                for movement in candidates:
                    if movement.get("ДисконтнаяКарта_Key") != discount_card_key:
                        continue
                    period = movement.get("Period", "")
                    if not _in_period(period, start_date, end_date):
                        continue

                    all_purchases.append({
                        "Period": period,
                        "Сумма": movement.get("Сумма", movement.get("СуммаПродаж", 0)),
                        "Количество": movement.get("Количество", movement.get("КоличествоОборот", 1)),
                        "Номенклатура_Key": movement.get("Номенклатура_Key"),
                        "Номенклатура_Description": movement.get("Номенклатура_Description"),
                        "Характеристика_Key": movement.get("Характеристика_Key"),
                        "Документ": movement.get("Документ") or movement.get("Recorder"),
                        "Документ_Type": movement.get("Документ_Type") or movement.get("Recorder_Type"),
                        "Recorder": movement.get("Recorder"),
                        "Recorder_Type": movement.get("Recorder_Type"),
                        "Склад_Key": movement.get("Склад_Key"),
                        "ДисконтнаяКарта_Key": movement.get("ДисконтнаяКарта_Key"),
                        "raw_1c_data": movement,
                    })

            skip += batch_size
            if len(all_purchases) >= limit:
                all_purchases = all_purchases[:limit]
                break
            if len(records) < batch_size:
                break

    return all_purchases


async def fetch_sales_from_check_documents(
    user: User,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    limit: int = DEFAULT_LIMIT,
) -> list[Dict[str, Any]]:
    """Fetch exact customer purchase lines from posted Document_ЧекККМ documents."""
    if not user.customer_id_1c or not start_date:
        return []
    if not end_date:
        end_date = datetime.now(timezone.utc)

    async with OneCSalesService() as sales_service:
        sales_data = await sales_service.fetch_sales_from_api(
            start_date=start_date,
            end_date=end_date,
            customer_key=user.customer_id_1c,
        )

    if sales_data.get("source") != "Document_ЧекККМ":
        return []

    purchases: list[Dict[str, Any]] = []
    for order in sales_data.get("orders", [])[:limit]:
        raw_data = order.get("raw_1c_data") or {}
        document_id = order.get("document_id") or raw_data.get("Recorder")
        period = order.get("date") or raw_data.get("Period")
        if not document_id or not period:
            continue

        purchases.append({
            "Period": period,
            "Сумма": order.get("revenue", 0),
            "Количество": order.get("items_count", 0),
            "Номенклатура_Key": order.get("product_id") or raw_data.get("Номенклатура_Key"),
            "Номенклатура_Description": order.get("product_name") or raw_data.get("Номенклатура_Description"),
            "Характеристика_Key": raw_data.get("Характеристика_Key"),
            "Документ": document_id,
            "Документ_Type": "StandardODATA.Document_ЧекККМ",
            "Recorder": document_id,
            "Recorder_Type": "StandardODATA.Document_ЧекККМ",
            "Склад_Key": order.get("store_id") or raw_data.get("СтруктурнаяЕдиница_Key") or raw_data.get("Склад_Key"),
            "Контрагент_Key": order.get("customer_id") or raw_data.get("Контрагент_Key"),
            "raw_1c_data": raw_data,
        })

    return purchases


async def fetch_all_customer_sales(
    onec: OneCCustomersService,
    user: User,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    limit: int = DEFAULT_LIMIT,
) -> tuple[list[Dict[str, Any]], Dict[str, int]]:
    """Объединяет продажи по контрагенту, по ДК и переносы из регистра ДК."""
    source_stats: Dict[str, int] = {}
    all_purchases: list[Dict[str, Any]] = []

    try:
        by_checks = await fetch_sales_from_check_documents(user, start_date, end_date, limit)
    except Exception as e:
        print(f"Предупреждение: продажи по чекам Document_ЧекККМ не получены: {e}")
        by_checks = []
    source_stats["by_check_documents"] = len(by_checks)
    if by_checks:
        purchases = sorted(
            by_checks,
            key=lambda item: _purchase_period(item) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        source_stats["deduplicated"] = len(purchases)
        source_stats["fallback_used"] = 0
        return purchases[:limit], source_stats

    source_stats["fallback_used"] = 1

    by_customer = await fetch_sales_from_register_parsing(user, start_date, end_date, limit)
    source_stats["by_customer"] = len(by_customer)
    all_purchases.extend(by_customer)

    if user.discount_card_id_1c:
        include_main_card_scan = os.getenv("ONEC_INCLUDE_MAIN_CARD_SCAN", "0").lower() in {"1", "true", "yes"}
        by_card_main: list[Dict[str, Any]] = []
        if include_main_card_scan:
            try:
                by_card_main = await onec.fetch_sales_by_discount_card(
                    discount_card_key=user.discount_card_id_1c,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit,
                )
            except Exception as e:
                print(f"Предупреждение: продажи по ДК из AccumulationRegister_Продажи не получены: {e}")
        source_stats["by_card_main"] = len(by_card_main)
        all_purchases.extend(by_card_main)

        try:
            by_card_recordtype = await fetch_sales_by_discount_card_recordtype(
                discount_card_key=user.discount_card_id_1c,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
            )
        except Exception as e:
            print(f"Предупреждение: продажи по ДК из RecordType не получены: {e}")
            by_card_recordtype = []
        source_stats["by_card_recordtype"] = len(by_card_recordtype)
        all_purchases.extend(by_card_recordtype)

    document_groups: Dict[tuple[str, str], list[Dict[str, Any]]] = {}
    for purchase in all_purchases:
        doc = _purchase_document_id(purchase)
        if not doc:
            continue
        dtype = _purchase_document_type(purchase)
        document_groups.setdefault((doc, dtype), []).append(purchase)

    report_signatures = set()
    for (_doc, dtype), items in document_groups.items():
        if "ОтчетОРозничныхПродажах" not in dtype:
            continue
        date_key = str(items[0].get("Period") or "")[:10]
        total_key = sum(to_kopecks(item.get("Сумма", 0)) for item in items)
        report_signatures.add((date_key, total_key))

    check_documents_to_drop = set()
    for (doc, dtype), items in document_groups.items():
        if "ЧекККМ" not in dtype:
            continue
        date_key = str(items[0].get("Period") or "")[:10]
        total_key = sum(to_kopecks(item.get("Сумма", 0)) for item in items)
        if (date_key, total_key) in report_signatures:
            check_documents_to_drop.add(doc)

    if check_documents_to_drop:
        all_purchases = [
            item for item in all_purchases
            if _purchase_document_id(item) not in check_documents_to_drop
        ]
    source_stats["dropped_check_documents"] = len(check_documents_to_drop)

    # 1C can return an additional night consolidated retail report with the
    # same items/amount as several earlier reports from the same business day.
    # Keep the daytime source documents and drop only the synthetic night copy.
    retail_docs = []
    for (doc, dtype), items in document_groups.items():
        if "ОтчетОРозничныхПродажах" not in dtype or not items:
            continue
        first_period = _purchase_period(items[0])
        if not first_period:
            continue
        retail_docs.append({
            "doc": doc,
            "date": first_period.date().isoformat(),
            "total": sum(to_kopecks(item.get("Сумма", 0)) for item in items),
            "is_night": _is_night_retail_report(items, dtype),
        })

    night_report_documents_to_drop = set()
    for night_doc in retail_docs:
        if not night_doc["is_night"]:
            continue
        daytime_total = sum(
            doc["total"]
            for doc in retail_docs
            if doc["date"] == night_doc["date"]
            and doc["doc"] != night_doc["doc"]
            and not doc["is_night"]
        )
        if daytime_total and daytime_total == night_doc["total"]:
            night_report_documents_to_drop.add(night_doc["doc"])

    if night_report_documents_to_drop:
        all_purchases = [
            item for item in all_purchases
            if _purchase_document_id(item) not in night_report_documents_to_drop
        ]
    source_stats["dropped_night_report_documents"] = len(night_report_documents_to_drop)

    unique = {}
    for purchase in all_purchases:
        key = (
            _purchase_document_id(purchase),
            purchase.get("Номенклатура_Key") or "",
            purchase.get("Характеристика_Key") or "",
            str(purchase.get("Period") or "")[:10],
        )
        unique[key] = purchase

    def parse_period(item: Dict[str, Any]) -> datetime:
        try:
            return parse_1c_datetime(item.get("Period", ""))
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    purchases = sorted(unique.values(), key=parse_period, reverse=True)
    source_stats["deduplicated"] = len(purchases)
    return purchases[:limit], source_stats


async def recalculate_customer_metrics(db, user: User) -> None:
    await db.flush()
    result = await db.execute(select(PurchaseHistory).where(PurchaseHistory.user_id == user.id))
    purchases = result.scalars().all()
    metric_purchases = [p for p in purchases if int(p.total_amount or 0) != 0]
    total_purchases = len(metric_purchases)
    total_spent = sum(int(p.total_amount or 0) for p in metric_purchases)
    user.total_purchases = total_purchases
    user.total_spent = total_spent
    user.average_check = total_spent // total_purchases if total_purchases else None
    user.last_purchase_date = max((p.purchase_date for p in metric_purchases if p.purchase_date), default=None)


async def sync_customer(phone: str, start: Optional[str], end: Optional[str], merge: bool) -> None:
    start_date = parse_date(start)
    end_date = parse_date(end, end=True)
    async with AsyncSessionLocal() as db:
        async with OneCCustomersService() as onec:
            user = await find_or_create_user(db, onec, phone)
            print(f"Покупатель: {user.full_name or user.phone}")
            print(f"1C Customer ID: {user.customer_id_1c or 'нет'}")
            print(f"1C Discount Card ID: {user.discount_card_id_1c or 'нет'}")

            if not user.customer_id_1c and not user.discount_card_id_1c:
                raise RuntimeError("У покупателя нет customer_id_1c и discount_card_id_1c")

            print("Получаю продажи из 1С: контрагент + дисконтная карта + начальный перенос ДК...")
            purchases, source_stats = await fetch_all_customer_sales(
                onec=onec,
                user=user,
                start_date=start_date,
                end_date=end_date,
                limit=DEFAULT_LIMIT,
            )
            print(f"Получено покупок из 1С после дедупликации: {len(purchases)}")
            print(f"Источники: {source_stats}")

            if not merge:
                print("Очищаю старую историю покупок пользователя перед импортом...")
                result = await db.execute(select(PurchaseHistory).where(PurchaseHistory.user_id == user.id))
                for purchase in result.scalars().all():
                    await db.delete(purchase)
                await db.flush()

            stats = {"created": 0, "updated": 0, "skipped": 0}
            product_cache: Dict[str, Dict[str, Any]] = {}
            for purchase in purchases:
                status = await upsert_purchase(db, user, onec, purchase, product_cache)
                stats[status] += 1

            link_service = SalesProductLinkService(db)
            linked_products = await link_service.backfill_missing_purchase_product_links(user_id=user.id)
            normalized_fields = await link_service.normalize_purchase_product_fields(user_id=user.id)

            print("Синхронизирую бонусные баллы...")
            try:
                loyalty = await sync_loyalty(db, onec, user)
            except Exception as e:
                print(f"Не удалось синхронизировать бонусы, покупки сохраняю: {e}")
                loyalty = {"updated": False, "balance": int(user.loyalty_points or 0)}
            await recalculate_customer_metrics(db, user)
            await CustomerAnalyticsService(db).refresh_preferred_store_by_count(user.id, commit=False)
            user.synced_at = datetime.now(timezone.utc)
            await db.commit()

            total_rub = sum(to_kopecks(item.get("Сумма", 0)) for item in purchases) / 100
            print("=" * 80)
            print("СИНХРОНИЗАЦИЯ ЗАВЕРШЕНА")
            print("=" * 80)
            print(f"Покупатель: {user.full_name or user.phone}")
            print(f"Телефон/карта: {user.phone}")
            print(f"Источники продаж: {source_stats}")
            print(f"Покупок из 1С: {len(purchases)}")
            print(f"Сумма из 1С: {total_rub:.2f} руб")
            print(f"Создано: {stats['created']}, обновлено: {stats['updated']}, пропущено: {stats['skipped']}")
            print(f"Связано с каталогом: {linked_products}, нормализовано категорий/брендов: {normalized_fields}")
            print(f"Бонусные баллы: {loyalty['balance']} ({'обновлены' if loyalty['updated'] else 'без изменений'})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Синхронизация продаж и бонусов покупателя по номеру карты/телефона")
    parser.add_argument("phone", help="Номер карты/телефона, например 79787891424")
    parser.add_argument("--start", help="Дата начала YYYY-MM-DD")
    parser.add_argument("--end", help="Дата окончания YYYY-MM-DD")
    parser.add_argument("--merge", action="store_true", help="Не удалять старую историю перед импортом")
    args = parser.parse_args()

    asyncio.run(sync_customer(args.phone, args.start, args.end, args.merge))


if __name__ == "__main__":
    main()
