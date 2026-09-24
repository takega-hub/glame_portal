"""Generate a YML price list compatible with Yandex Business product imports."""
from __future__ import annotations

import os
import hashlib
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable
from urllib.parse import urljoin
from xml.etree import ElementTree as ET


DEFAULT_PRODUCT_URL_TEMPLATE = "https://glamejewelry.ru/products/{id}"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _absolute_url(value: str, public_base_url: str) -> str:
    value = _text(value)
    return urljoin(public_base_url.rstrip("/") + "/", value) if value.startswith("/") else value


def _product_url(product_id: Any) -> str:
    template = os.getenv("YANDEX_BUSINESS_PRODUCT_URL_TEMPLATE", DEFAULT_PRODUCT_URL_TEMPLATE).strip()
    return template.replace("{id}", str(product_id))


def _price_rub(kopecks: Any) -> str:
    value = (Decimal(str(kopecks or 0)) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(value, "f").rstrip("0").rstrip(".")


def _yandex_offer_id(source_id: Any, assigned_ids: set[str]) -> str:
    """Return a stable positive numeric identifier accepted by Yandex Business.

    GLAME and 1C commonly use UUIDs, which the Business import rejects as an
    offer ID. A deterministic 15-digit value keeps repeated exports stable.
    """

    digest = hashlib.sha256(f"glame-yandex-business:{source_id}".encode("utf-8")).digest()
    candidate = 900_000_000_000_000 + (int.from_bytes(digest[:8], "big") % 100_000_000_000_000)
    while str(candidate) in assigned_ids:
        candidate += 1
    result = str(candidate)
    assigned_ids.add(result)
    return result


def build_yandex_business_feed(products: Iterable[Any], stock_by_product_id: dict[str, float | None]) -> tuple[bytes, dict[str, Any]]:
    """Build XML and a compact validation report without writing to disk.

    Products without a positive price or a usable image are excluded because Yandex
    Business imports would otherwise create incomplete card entries.
    """

    public_base_url = (
        os.getenv("PUBLIC_STATIC_BASE_URL")
        or os.getenv("APP_PUBLIC_BASE_URL")
        or os.getenv("API_PUBLIC_BASE_URL")
        or "https://glamejewelry.ru"
    )
    valid: list[Any] = []
    skipped: list[dict[str, str]] = []
    category_names: dict[str, int] = {}

    for product in products:
        images = getattr(product, "images", None) or []
        image = next((_absolute_url(str(item), public_base_url) for item in images if _text(item)), "")
        product_id = str(getattr(product, "id", ""))
        if not product_id:
            skipped.append({"name": _text(getattr(product, "name", "")), "reason": "нет ID товара"})
            continue
        if int(getattr(product, "price", 0) or 0) <= 0:
            skipped.append({"name": _text(getattr(product, "name", "")), "reason": "не задана цена"})
            continue
        if not image.startswith(("http://", "https://")):
            skipped.append({"name": _text(getattr(product, "name", "")), "reason": "нет публичного изображения"})
            continue
        category = _text(getattr(product, "category", "")) or "Украшения"
        if category not in category_names:
            category_names[category] = len(category_names) + 1
        valid.append((product, image, category))

    root = ET.Element("yml_catalog")
    shop = ET.SubElement(root, "shop")
    categories = ET.SubElement(shop, "categories")
    for category, category_id in category_names.items():
        ET.SubElement(categories, "category", {"id": str(category_id)}).text = category

    offers = ET.SubElement(shop, "offers")
    assigned_offer_ids: set[str] = set()
    for product, image, category in valid:
        product_id = str(product.id)
        stock = stock_by_product_id.get(product_id)
        availability = "unknown" if stock is None else ("true" if stock > 0 else "false")
        offer_id = _yandex_offer_id(getattr(product, "external_id", None) or product_id, assigned_offer_ids)
        offer = ET.SubElement(offers, "offer", {"id": offer_id, "available": availability})
        ET.SubElement(offer, "name").text = _text(product.name)
        ET.SubElement(offer, "vendor").text = _text(getattr(product, "brand", None)) or "GLAME"
        ET.SubElement(offer, "price").text = _price_rub(product.price)
        ET.SubElement(offer, "currencyId").text = "RUR"
        ET.SubElement(offer, "categoryId").text = str(category_names[category])
        ET.SubElement(offer, "picture").text = image
        ET.SubElement(offer, "url").text = _product_url(product_id)
        description = _text(getattr(product, "full_description", None) or getattr(product, "description", None))
        if description:
            ET.SubElement(offer, "description").text = description
        short_description = _text(getattr(product, "description", None) or getattr(product, "name", None))
        if short_description:
            ET.SubElement(offer, "shortDescription").text = short_description[:250]
        article = _text(getattr(product, "article", None) or getattr(product, "vendor_code", None))
        if article:
            ET.SubElement(offer, "vendorCode").text = article

    ET.indent(root, space="  ")
    xml = b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")
    return xml, {
        "total_active": len(valid) + len(skipped),
        "included": len(valid),
        "skipped": len(skipped),
        "categories": len(category_names),
        "skipped_items": skipped[:50],
    }
