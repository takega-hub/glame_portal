"""Shared accessory/supplementary product exclusion policy for GLAME analytics.

Accessory rows (packaging, bags, cases, certificates, service materials) are kept in
raw 1C sales tables for audit, but must not participate in product analytics,
customer average/purchase-count metrics, seller KPI item/check/average metrics, or
recommendation/product-demand calculations.
"""
from __future__ import annotations

from typing import Any, Optional

ACCESSORY_PRODUCT_TERMS = (
    "упаков",
    "пакет",
    "короб",
    "футляр",
    "мешочек",
    "салфет",
    "сертификат",
    "gift card",
    "certificate",
    "packaging",
    "сопутств",
    "открытк",
    "холдер",
    "карточк",
    "уход",
)

ACCESSORY_PRODUCT_IDS = (
    "1fee8e94-bdab-11f0-9138-fa163e4cc04e",
    "2169e1d8-bdab-11f0-9138-fa163e4cc04e",
    "51026f84-c23b-11f0-8314-fa163e4cc04e",
    "51e7b0a8-c23b-11f0-8314-fa163e4cc04e",
    "528be556-c23b-11f0-8314-fa163e4cc04e",
    "1aa57e48-bdab-11f0-9138-fa163e4cc04e",
    "22359e5e-bdab-11f0-9138-fa163e4cc04e",
    "16adf77a-baf4-11f0-836e-fa163e4cc04e",
    "1baaa872-bdab-11f0-9138-fa163e4cc04e",
    "150b5f2a-baf4-11f0-836e-fa163e4cc04e",
    "1f263868-bdab-11f0-9138-fa163e4cc04e",
    "22eada08-bdab-11f0-9138-fa163e4cc04e",
    "0135f798-bb1d-11f0-836e-fa163e4cc04e",
    "245f8a6e-bdab-11f0-9138-fa163e4cc04e",
    "a2a2b022-bccf-11f0-9138-fa163e4cc04e",
    "1e69afd6-bdab-11f0-9138-fa163e4cc04e",
    "15cb6522-baf4-11f0-836e-fa163e4cc04e",
)

ACCESSORY_ARTICLE_PREFIXES = ("400", "500")
ACCESSORY_AMOUNT_THRESHOLD_KOPECKS = 500


def _norm(value: Optional[Any]) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").strip().lower().split())


def is_accessory_product(
    *,
    product_name: Optional[Any] = None,
    product_category: Optional[Any] = None,
    product_article: Optional[Any] = None,
    product_type: Optional[Any] = None,
    product_id: Optional[Any] = None,
    raw_text: Optional[Any] = None,
    total_amount_kopecks: Optional[int] = None,
) -> bool:
    product_id_norm = _norm(product_id)
    if product_id_norm and product_id_norm in ACCESSORY_PRODUCT_IDS:
        return True

    article = _norm(product_article)
    if article and article.startswith(ACCESSORY_ARTICLE_PREFIXES):
        return True

    combined = _norm(" ".join(str(part or "") for part in (product_name, product_category, product_article, product_type, raw_text)))
    if any(term in combined for term in ACCESSORY_PRODUCT_TERMS):
        return True

    if total_amount_kopecks is not None and total_amount_kopecks >= 0 and total_amount_kopecks < ACCESSORY_AMOUNT_THRESHOLD_KOPECKS:
        return True

    return False


def is_analytics_eligible_product(**kwargs: Any) -> bool:
    return not is_accessory_product(**kwargs)


def sales_record_product_text_sql(sales_alias: str = "sr", product_alias: str = "p") -> str:
    sr = sales_alias
    p = product_alias
    return (
        f"LOWER(COALESCE({sr}.product_name, '') || ' ' || COALESCE({sr}.product_category, '') || ' ' || "
        f"COALESCE({sr}.product_article, '') || ' ' || COALESCE({sr}.product_type, '') || ' ' || "
        f"COALESCE({p}.name, '') || ' ' || COALESCE({p}.category, '') || ' ' || COALESCE({p}.article, '') || ' ' || "
        f"COALESCE({sr}.raw_data->>'Номенклатура', '') || ' ' || COALESCE({sr}.raw_data->>'НоменклатураНаименование', '') || ' ' || "
        f"COALESCE({sr}.raw_data->>'Номенклатура_Description', '') || ' ' || COALESCE({sr}.raw_data->>'product_name', '') || ' ' || "
        f"COALESCE({sr}.raw_data->>'category', ''))"
    )


def analytics_eligible_product_sql(sales_alias: str = "sr", product_alias: str = "p") -> str:
    text_expr = sales_record_product_text_sql(sales_alias=sales_alias, product_alias=product_alias)
    id_list = ", ".join([f"'{product_id}'" for product_id in ACCESSORY_PRODUCT_IDS])
    clauses = [f"{text_expr} NOT LIKE '%{term}%'" for term in ACCESSORY_PRODUCT_TERMS]
    clauses.append(f"COALESCE({sales_alias}.product_id, {sales_alias}.raw_data->>'Номенклатура_Key', '') NOT IN ({id_list})")
    for prefix in ACCESSORY_ARTICLE_PREFIXES:
        clauses.append(f"COALESCE({sales_alias}.product_article, {product_alias}.article, '') NOT LIKE '{prefix}%'")
    return "(" + " AND ".join(clauses) + ")"


ANALYTICS_ELIGIBLE_PRODUCT_SQL = analytics_eligible_product_sql()


def sales_record_eligible_product_filter(SalesRecord: Any, func: Any, and_: Any, Product: Optional[Any] = None) -> Any:
    """Build a SQLAlchemy condition without importing SQLAlchemy in this helper."""
    text_parts = [
        SalesRecord.product_name,
        SalesRecord.product_category,
        SalesRecord.product_article,
        SalesRecord.product_type,
    ]
    if Product is not None:
        text_parts.extend([Product.name, Product.category, Product.article])
    text_expr = func.lower(func.concat(*sum(([func.coalesce(part, ""), " "] for part in text_parts), [])))
    conditions = [text_expr.not_like(f"%{term}%") for term in ACCESSORY_PRODUCT_TERMS]
    conditions.append(func.coalesce(SalesRecord.product_id, "").notin_(ACCESSORY_PRODUCT_IDS))
    article_expr = func.coalesce(SalesRecord.product_article, Product.article if Product is not None else "")
    for prefix in ACCESSORY_ARTICLE_PREFIXES:
        conditions.append(article_expr.not_like(f"{prefix}%"))
    return and_(*conditions)


def product_eligible_filter(Product: Any, func: Any, and_: Any) -> Any:
    """SQLAlchemy condition for product/stock-only assortment views."""
    text_expr = func.lower(
        func.concat(
            func.coalesce(Product.name, ""),
            " ",
            func.coalesce(Product.category, ""),
            " ",
            func.coalesce(Product.article, ""),
        )
    )
    conditions = [text_expr.not_like(f"%{term}%") for term in ACCESSORY_PRODUCT_TERMS]
    conditions.append(func.coalesce(Product.external_id, "").notin_(ACCESSORY_PRODUCT_IDS))
    article_expr = func.coalesce(Product.article, "")
    for prefix in ACCESSORY_ARTICLE_PREFIXES:
        conditions.append(article_expr.not_like(f"{prefix}%"))
    return and_(*conditions)
