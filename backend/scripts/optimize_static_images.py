#!/usr/bin/env python3
"""
Оптимизация существующих изображений в backend/static.

По умолчанию работает в dry-run и ничего не меняет:
    python backend/scripts/optimize_static_images.py

Применить изменения с бэкапом оригиналов:
    python backend/scripts/optimize_static_images.py --apply --backup-dir backend/static_originals_backup

Конвертировать PNG/JPEG в WebP и обновить ссылки в БД:
    python backend/scripts/optimize_static_images.py --apply --format webp --update-db

Безопасность:
- dry-run по умолчанию;
- по умолчанию обрабатываются только файлы больше 150 KB;
- файлы меньше заданного порога экономии не заменяются;
- при смене расширения старый файл сохраняется, если не указан --delete-originals;
- обновление БД делается только с --update-db.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.image_optimization import DEFAULT_DIRS, run_image_optimization


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize images under backend/static")
    parser.add_argument("--apply", action="store_true", help="Actually write optimized files")
    parser.add_argument("--root", default=".", help="Repo root path")
    parser.add_argument(
        "--dirs",
        nargs="*",
        default=DEFAULT_DIRS,
        help="Directories to scan, relative to repo root",
    )
    parser.add_argument("--format", choices=["webp", "jpeg", "keep"], default="keep")
    parser.add_argument("--quality", type=int, default=int(os.getenv("IMAGE_OPTIMIZE_QUALITY", "82")))
    parser.add_argument("--max-side", type=int, default=int(os.getenv("IMAGE_OPTIMIZE_MAX_SIDE", "1800")))
    parser.add_argument("--min-saving-pct", type=float, default=5.0)
    parser.add_argument("--min-saving-bytes", type=int, default=20 * 1024)
    parser.add_argument("--min-original-bytes", type=int, default=150 * 1024)
    parser.add_argument("--backup-dir", default=None, help="Backup originals before replacing")
    parser.add_argument("--delete-originals", action="store_true", help="Delete old file when extension changes")
    parser.add_argument("--update-db", action="store_true", help="Update DB URL references when extension changes")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N images")
    parser.add_argument("--json-report", default=None, help="Write JSON report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    summary, details = run_image_optimization(
        root=root,
        dirs=args.dirs,
        fmt=args.format,
        quality=args.quality,
        max_side=args.max_side,
        min_saving_pct=args.min_saving_pct,
        min_saving_bytes=args.min_saving_bytes,
        min_original_bytes=args.min_original_bytes,
        backup_dir=args.backup_dir if args.apply else None,
        delete_originals=args.delete_originals if args.apply else False,
        update_db=args.update_db if args.apply else False,
        limit=args.limit,
    )

    print(f"Found {summary.scanned_files} images")
    print(f"Eligible (>={summary.min_original_bytes // 1024} KB): {summary.eligible_files}")
    print(f"Skipped as small: {summary.skipped_small_files}")
    print(f"Will optimize: {summary.optimized_files}")
    print(f"Estimated saving: {summary.saved_bytes / 1024 / 1024:.1f} MB")

    if args.apply:
        print(f"Optimized {summary.optimized_files} files")
        if summary.changed_extensions and not args.update_db:
            print(
                f"Extension changed for {summary.changed_extensions} files. "
                "Use --update-db to update URL references."
            )
        if summary.db_rows_updated:
            print(f"DB references updated in {summary.db_rows_updated} rows")
    else:
        print("Dry-run only. Add --apply to write files.")

    if args.json_report:
        report_path = Path(args.json_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "summary": summary.to_dict(),
                    "files": details,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Report written to {report_path}")

    if summary.errors:
        print(f"Errors: {len(summary.errors)}")
        for error in summary.errors[:10]:
            print(f"- {error}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
