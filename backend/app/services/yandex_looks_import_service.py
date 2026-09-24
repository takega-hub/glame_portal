import io
import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import httpx
from PIL import Image, ImageOps
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.look import Look
from app.models.product import Product

logger = logging.getLogger(__name__)

YANDEX_LOOKS_PUBLIC_URL = "https://disk.yandex.ru/d/MpXQ7xrhhguxkQ"
YANDEX_PUBLIC_RESOURCES_URL = "https://cloud-api.yandex.net/v1/disk/public/resources"
YANDEX_LOOKS_PROVIDER = "yandex_disk"
LOOK_SOURCE_PROVIDER = "real_shoot"


def _static_root() -> Path:
    candidates = [
        Path("static"),
        Path("backend/static"),
        Path(__file__).resolve().parents[2] / "static",
    ]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists() and resolved.is_dir():
            return resolved
    fallback = Path(__file__).resolve().parents[2] / "static"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def extract_articles(value: str) -> list[str]:
    raw = Path(value or "").stem
    matches = re.findall(r"(?<![A-Za-zА-Яа-я0-9])\d{4,6}(?:-[A-Za-zА-Яа-я])?(?![A-Za-zА-Яа-я0-9])", raw)
    result: list[str] = []
    seen: set[str] = set()
    for match in matches:
        normalized = match.upper()
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]+", "_", value.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:140] or uuid4().hex


def _image_download_url(item: dict[str, Any]) -> str | None:
    if item.get("file"):
        return str(item["file"])
    sizes = item.get("sizes") if isinstance(item.get("sizes"), list) else []
    for preferred in ("ORIGINAL", "XXXL", "XXL", "XL", "DEFAULT"):
        for size in sizes:
            if isinstance(size, dict) and size.get("name") == preferred and size.get("url"):
                return str(size["url"])
    return None


def _optimize_image(image_bytes: bytes) -> bytes:
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="WEBP", quality=82, method=6)
        return output.getvalue()


async def _fetch_resource(client: httpx.AsyncClient, public_key: str, path: str = "/", limit: int = 200) -> dict[str, Any]:
    response = await client.get(
        YANDEX_PUBLIC_RESOURCES_URL,
        params={"public_key": public_key, "path": path, "limit": limit},
    )
    response.raise_for_status()
    return response.json()


async def _download_image(client: httpx.AsyncClient, item: dict[str, Any], folder_slug: str) -> str | None:
    download_url = _image_download_url(item)
    if not download_url:
        return None
    response = await client.get(download_url)
    response.raise_for_status()
    optimized = _optimize_image(response.content)

    target_dir = _static_root() / "look_images" / "yandex_disk" / folder_slug
    target_dir.mkdir(parents=True, exist_ok=True)
    file_slug = _slug(Path(str(item.get("name") or "image")).stem)
    target_path = target_dir / f"{file_slug}.webp"
    target_path.write_bytes(optimized)
    return f"/static/look_images/yandex_disk/{folder_slug}/{target_path.name}"


async def _products_by_articles(db: AsyncSession, articles: list[str]) -> dict[str, Product]:
    if not articles:
        return {}
    normalized = [article.upper() for article in articles]
    lower_values = [article.lower() for article in normalized]
    stmt = select(Product).where(
        or_(
            func.lower(Product.article).in_(lower_values),
            func.lower(Product.external_code).in_(lower_values),
            func.lower(Product.vendor_code).in_(lower_values),
        )
    )
    rows = list((await db.execute(stmt)).scalars().all())
    by_article: dict[str, Product] = {}
    for product in rows:
        for value in (product.article, product.external_code, product.vendor_code):
            key = (value or "").strip().upper()
            if key and key in normalized and key not in by_article:
                by_article[key] = product
    return by_article


def _look_name(products: list[Product], articles: list[str]) -> str:
    categories = [str(p.category or "").lower() for p in products]
    suffixes = [article.rsplit("-", 1)[-1] for article in articles if "-" in article]
    metal = "Золотой" if suffixes.count("G") > suffixes.count("S") else "Серебряный"
    if any("серь" in c for c in categories) and any("коль" in c for c in categories):
        return f"{metal} акцент"
    if any("колье" in c or "цеп" in c or "чок" in c for c in categories):
        return f"{metal} силуэт"
    if any("брасл" in c for c in categories):
        return f"{metal} ритм"
    return f"{metal} комплект"


def _description(products: list[Product], articles: list[str]) -> str:
    names = [p.name for p in products if p.name][:5]
    intro = "Собранный образ GLAME из украшений, которые работают вместе как единый комплект."
    if names:
        intro = f"Собранный образ GLAME: {', '.join(names)}."
    return (
        f"{intro} Комплект построен на сочетании акцентных деталей и чистых линий, "
        "его легко носить как цельный образ или разбирать на отдельные украшения под настроение."
    )


async def import_yandex_looks(
    db: AsyncSession,
    *,
    public_url: str = YANDEX_LOOKS_PUBLIC_URL,
    limit: Optional[int] = None,
    publish: bool = False,
) -> dict[str, Any]:
    imported: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    timeout = httpx.Timeout(90.0, connect=20.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        root_limit = max(limit or 1000, 50)
        root = await _fetch_resource(client, public_url, "/", limit=root_limit)
        items = ((root.get("_embedded") or {}).get("items") or [])
        folders = [item for item in items if item.get("type") == "dir"]

        folders_to_import = folders[:limit] if limit else folders
        for folder in folders_to_import:
            folder_path = str(folder.get("path") or "")
            folder_name = str(folder.get("name") or Path(folder_path).name)
            source_media_key = folder_path or f"/{folder_name}"
            source_media_id = f"yd:{hashlib.sha256(source_media_key.encode('utf-8')).hexdigest()[:40]}"

            existing = (
                await db.execute(
                    select(Look).where(
                        and_(
                            Look.source_provider == LOOK_SOURCE_PROVIDER,
                            Look.source_media_id == source_media_id,
                        )
                    )
                )
            ).scalar_one_or_none()
            if existing:
                skipped.append({"folder": folder_name, "reason": "already_imported", "look_id": str(existing.id)})
                continue

            try:
                folder_resource = await _fetch_resource(client, public_url, folder_path, limit=200)
                raw_files = ((folder_resource.get("_embedded") or {}).get("items") or [])
                image_files = [
                    item
                    for item in raw_files
                    if item.get("type") == "file"
                    and str(item.get("mime_type") or "").startswith("image/")
                    and _image_download_url(item)
                ]
                if not image_files:
                    skipped.append({"folder": folder_name, "reason": "no_images"})
                    continue

                folder_articles = extract_articles(folder_name)
                products_by_article = await _products_by_articles(db, folder_articles)
                ordered_products: list[Product] = []
                seen_product_ids: set[str] = set()
                for article in folder_articles:
                    product = products_by_article.get(article)
                    product_id = str(product.id) if product else ""
                    if product and product_id not in seen_product_ids:
                        seen_product_ids.add(product_id)
                        ordered_products.append(product)

                folder_slug = _slug(folder_name)
                image_payloads: list[dict[str, Any]] = []
                for item in image_files:
                    url = await _download_image(client, item, folder_slug)
                    if not url:
                        continue
                    image_articles = extract_articles(str(item.get("name") or ""))
                    image_name = str(item.get("name") or "")
                    image_payloads.append(
                        {
                            "url": url,
                            "name": image_name,
                            "articles": image_articles,
                            "article_count": len(image_articles),
                            "is_main": "main" in image_name.lower(),
                        }
                    )

                if not image_payloads:
                    skipped.append({"folder": folder_name, "reason": "download_failed"})
                    continue

                image_payloads.sort(
                    key=lambda x: (
                        1 if x.get("is_main") else 0,
                        int(x.get("article_count") or 0),
                        len(str(x.get("name") or "")),
                    ),
                    reverse=True,
                )
                main_image = image_payloads[0]
                image_items = [
                    {
                        "url": item["url"],
                        "source": YANDEX_LOOKS_PROVIDER,
                        "filename": item["name"],
                        "articles": item["articles"],
                        "is_main": bool(item.get("is_main")),
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                    }
                    for item in image_payloads
                ]
                media_items = [{"type": "image", "url": item["url"], "source": YANDEX_LOOKS_PROVIDER} for item in image_payloads]
                product_ids = [str(product.id) for product in ordered_products]
                product_layout = [
                    {
                        "product_id": str(product.id),
                        "position": idx + 1,
                        "article": folder_articles[idx] if idx < len(folder_articles) else product.article,
                        "product_name": product.name,
                        "source": YANDEX_LOOKS_PROVIDER,
                    }
                    for idx, product in enumerate(ordered_products)
                ]
                missing_articles = [article for article in folder_articles if article not in products_by_article]

                name = _look_name(ordered_products, folder_articles)
                description = _description(ordered_products, folder_articles)
                look = Look(
                    name=name,
                    product_ids=product_ids,
                    description=description,
                    caption=description,
                    image_url=main_image["url"],
                    image_urls=image_items,
                    current_image_index=0,
                    media_items=media_items,
                    product_layout=product_layout,
                    source_provider=LOOK_SOURCE_PROVIDER,
                    source_media_id=source_media_id,
                    source_permalink=public_url,
                    status="approved" if publish else "draft",
                    approval_status="approved" if publish else "pending",
                    is_published=publish,
                    published_at=datetime.now(timezone.utc) if publish else None,
                    is_new=True,
                    generation_metadata={
                        "source": YANDEX_LOOKS_PROVIDER,
                        "yandex_folder_name": folder_name,
                        "yandex_folder_path": folder_path,
                        "yandex_source_media_key": source_media_key,
                        "folder_articles": folder_articles,
                        "missing_articles": missing_articles,
                        "imported_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                db.add(look)
                await db.commit()
                await db.refresh(look)
                imported.append(
                    {
                        "look_id": str(look.id),
                        "folder": folder_name,
                        "name": look.name,
                        "products": len(product_ids),
                        "images": len(image_payloads),
                        "missing_articles": missing_articles,
                    }
                )
            except Exception as exc:
                await db.rollback()
                logger.exception("Failed to import Yandex look folder %s", folder_name)
                errors.append({"folder": folder_name, "error": str(exc)})

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "summary": {
            "imported": len(imported),
            "skipped": len(skipped),
            "errors": len(errors),
        },
    }
