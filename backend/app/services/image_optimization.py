from __future__ import annotations

import asyncio
import io
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_DIRS = [
    "backend/static/look_images",
    "backend/static/content_post_images",
    "backend/static/app_admin_media",
    "backend/static/product_images",
    "backend/static/jewelry_processed",
]


@dataclass
class OptimizedImage:
    source: Path
    target: Path
    original_bytes: int
    optimized_bytes: int
    width: int
    height: int
    changed: bool
    reason: str = ""

    @property
    def saved_bytes(self) -> int:
        return self.original_bytes - self.optimized_bytes


@dataclass
class ImageOptimizationSummary:
    scanned_files: int
    eligible_files: int
    optimized_files: int
    skipped_small_files: int
    failed_files: int
    scanned_bytes: int
    optimized_original_bytes: int
    optimized_result_bytes: int
    saved_bytes: int
    changed_extensions: int
    db_rows_updated: int
    min_original_bytes: int
    format: str
    quality: int
    max_side: int
    dirs: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def iter_images(root: Path, dirs: list[str], limit: int = 0) -> list[Path]:
    files: list[Path] = []
    for rel in dirs:
        base = (root / rel).resolve()
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
                files.append(path)
                if limit and len(files) >= limit:
                    return files
    return files


def output_target(path: Path, fmt: str) -> tuple[Path, str]:
    suffix = path.suffix.lower()
    if fmt == "keep":
        if suffix in {".jpg", ".jpeg"}:
            return path, "JPEG"
        if suffix == ".png":
            return path, "PNG"
        return path, "WEBP"
    if fmt == "jpeg":
        return path.with_suffix(".jpg"), "JPEG"
    return path.with_suffix(".webp"), "WEBP"


def optimize_one(path: Path, fmt: str, quality: int, max_side: int) -> OptimizedImage:
    original_bytes = path.stat().st_size
    target, pil_format = output_target(path, fmt)

    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            if max_side > 0:
                img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

            width, height = img.size
            out = io.BytesIO()

            if pil_format == "JPEG":
                if img.mode not in ("RGB", "L"):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode in ("RGBA", "LA"):
                        background.paste(img.convert("RGBA"), mask=img.getchannel("A"))
                    else:
                        background.paste(img.convert("RGB"))
                    img = background
                else:
                    img = img.convert("RGB")
                img.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
            elif pil_format == "PNG":
                img.save(out, format="PNG", optimize=True)
            else:
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
                img.save(out, format="WEBP", quality=quality, method=6)

            data = out.getvalue()
            return OptimizedImage(
                source=path,
                target=target,
                original_bytes=original_bytes,
                optimized_bytes=len(data),
                width=width,
                height=height,
                changed=True,
            )
    except Exception as exc:
        return OptimizedImage(
            source=path,
            target=target,
            original_bytes=original_bytes,
            optimized_bytes=original_bytes,
            width=0,
            height=0,
            changed=False,
            reason=str(exc),
        )


def should_write(item: OptimizedImage, min_saving_pct: float, min_saving_bytes: int) -> bool:
    if not item.changed:
        return False
    if item.optimized_bytes >= item.original_bytes:
        return False
    saved_pct = (item.saved_bytes / item.original_bytes) * 100 if item.original_bytes else 0
    return item.saved_bytes >= min_saving_bytes and saved_pct >= min_saving_pct


def backup_file(path: Path, root: Path, backup_root: Path) -> None:
    rel = path.resolve().relative_to(root.resolve())
    dest = backup_root / rel
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)


def write_optimized(path: Path, target: Path, fmt: str, quality: int, max_side: int) -> None:
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        if max_side > 0:
            img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

        target.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "jpeg" or (fmt == "keep" and target.suffix.lower() in {".jpg", ".jpeg"}):
            if img.mode not in ("RGB", "L"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode in ("RGBA", "LA"):
                    background.paste(img.convert("RGBA"), mask=img.getchannel("A"))
                else:
                    background.paste(img.convert("RGB"))
                img = background
            else:
                img = img.convert("RGB")
            img.save(target, format="JPEG", quality=quality, optimize=True, progressive=True)
        elif fmt == "keep" and target.suffix.lower() == ".png":
            img.save(target, format="PNG", optimize=True)
        else:
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
            img.save(target, format="WEBP", quality=quality, method=6)


def static_url(path: Path, root: Path) -> str | None:
    try:
        rel = path.resolve().relative_to((root / "backend/static").resolve())
    except ValueError:
        return None
    return f"/static/{rel.as_posix()}"


async def _update_db_references(url_map: dict[str, str], root: Path) -> int:
    if not url_map:
        return 0

    sys.path.insert(0, str((root / "backend").resolve()))
    from sqlalchemy import select
    from app.database.connection import AsyncSessionLocal
    from app.models.app_banner import AppBanner
    from app.models.app_lookbook import AppLookbook
    from app.models.app_news import AppNews
    from app.models.app_promotion import AppPromotion
    from app.models.content_item import ContentItem
    from app.models.look import Look
    from app.models.product import Product

    def replace_value(value: Any) -> tuple[Any, bool]:
        if isinstance(value, str):
            new_value = url_map.get(value)
            return (new_value, True) if new_value else (value, False)
        if isinstance(value, list):
            changed = False
            out = []
            for item in value:
                next_item, item_changed = replace_value(item)
                changed = changed or item_changed
                out.append(next_item)
            return out, changed
        if isinstance(value, dict):
            changed = False
            out = {}
            for key, item in value.items():
                next_item, item_changed = replace_value(item)
                changed = changed or item_changed
                out[key] = next_item
            return out, changed
        return value, False

    async with AsyncSessionLocal() as db:
        updated = 0

        for model in [Look, ContentItem, AppBanner, AppLookbook, AppNews, AppPromotion, Product]:
            result = await db.execute(select(model))
            rows = list(result.scalars().all())
            for row in rows:
                row_changed = False
                for column in row.__table__.columns:
                    value = getattr(row, column.name)
                    new_value, changed = replace_value(value)
                    if changed:
                        setattr(row, column.name, new_value)
                        row_changed = True
                if row_changed:
                    updated += 1

        if updated:
            await db.commit()
        return updated


def run_image_optimization(
    *,
    root: Path,
    dirs: list[str] | None = None,
    fmt: str = "keep",
    quality: int = 82,
    max_side: int = 1800,
    min_saving_pct: float = 5.0,
    min_saving_bytes: int = 20 * 1024,
    min_original_bytes: int = 150 * 1024,
    backup_dir: str | None = None,
    delete_originals: bool = False,
    update_db: bool = False,
    limit: int = 0,
) -> tuple[ImageOptimizationSummary, list[dict[str, Any]]]:
    scan_dirs = list(dirs or DEFAULT_DIRS)
    files = iter_images(root, scan_dirs, limit)

    results: list[OptimizedImage] = []
    write_candidates: list[OptimizedImage] = []
    url_map: dict[str, str] = {}
    skipped_small_files = 0
    failed_files = 0
    errors: list[str] = []
    scanned_bytes = 0

    for path in files:
        original_bytes = path.stat().st_size
        scanned_bytes += original_bytes
        if original_bytes < min_original_bytes:
            skipped_small_files += 1
            continue

        item = optimize_one(path, fmt, quality, max_side)
        results.append(item)
        if item.reason:
            failed_files += 1
            if len(errors) < 20:
                errors.append(f"{item.source}: {item.reason}")
        if should_write(item, min_saving_pct, min_saving_bytes):
            write_candidates.append(item)

    backup_root = Path(backup_dir).resolve() if backup_dir else None
    for item in write_candidates:
        old_url = static_url(item.source, root)
        new_url = static_url(item.target, root)
        if backup_root:
            backup_file(item.source, root, backup_root)
        write_optimized(item.source, item.target, fmt, quality, max_side)
        if item.target != item.source and delete_originals:
            item.source.unlink()
        if old_url and new_url and old_url != new_url:
            url_map[old_url] = new_url

    db_rows_updated = 0
    if update_db and url_map:
        db_rows_updated = asyncio.run(_update_db_references(url_map, root))

    summary = ImageOptimizationSummary(
        scanned_files=len(files),
        eligible_files=len(results),
        optimized_files=len(write_candidates),
        skipped_small_files=skipped_small_files,
        failed_files=failed_files,
        scanned_bytes=scanned_bytes,
        optimized_original_bytes=sum(x.original_bytes for x in write_candidates),
        optimized_result_bytes=sum(x.optimized_bytes for x in write_candidates),
        saved_bytes=sum(x.saved_bytes for x in write_candidates),
        changed_extensions=len(url_map),
        db_rows_updated=db_rows_updated,
        min_original_bytes=min_original_bytes,
        format=fmt,
        quality=quality,
        max_side=max_side,
        dirs=scan_dirs,
        errors=errors,
    )

    details = [
        {
            "source": str(x.source),
            "target": str(x.target),
            "original_bytes": x.original_bytes,
            "optimized_bytes": x.optimized_bytes,
            "saved_bytes": x.saved_bytes,
            "will_write": x in write_candidates,
            "reason": x.reason,
        }
        for x in results
    ]
    return summary, details
