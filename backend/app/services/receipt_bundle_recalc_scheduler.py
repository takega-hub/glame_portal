"""
Ночной планировщик пересчета рекомендательной системы комплектов по чекам.

После синхронизации новых продаж из 1С система должна обновлять association rules,
чтобы AI Stylist, живые стилисты и карточки клиентов работали на свежих данных.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _seconds_until(hour: int, minute: int) -> float:
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def run_receipt_bundle_recalc() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    script_path = backend_dir / "analyze_receipt_bundles.py"

    if not script_path.exists():
        logger.error("Receipt bundle analyzer script not found: %s", script_path)
        return

    days = os.getenv("RECEIPT_BUNDLES_ANALYSIS_DAYS", "730")
    limit = os.getenv("RECEIPT_BUNDLES_ANALYSIS_LIMIT", "500")
    min_pair_support = os.getenv("RECEIPT_BUNDLES_MIN_PAIR_SUPPORT", "3")
    min_confidence = os.getenv("RECEIPT_BUNDLES_MIN_CONFIDENCE", "0.03")
    source = os.getenv("RECEIPT_BUNDLES_SOURCE", "auto")
    output_dir = os.getenv("RECEIPT_BUNDLES_OUTPUT_DIR", "data/receipt_bundle_analysis")
    timeout_seconds = int(os.getenv("RECEIPT_BUNDLES_RECALC_TIMEOUT_SECONDS", "1800"))

    cmd = [
        sys.executable,
        str(script_path),
        "--source",
        source,
        "--days",
        days,
        "--limit",
        limit,
        "--min-pair-support",
        min_pair_support,
        "--min-confidence",
        min_confidence,
        "--output-dir",
        output_dir,
    ]

    logger.info("Starting receipt bundle recommendation recalculation: %s", " ".join(cmd))

    def _run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            cwd=str(backend_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )

    try:
        result = await asyncio.to_thread(_run)
    except subprocess.TimeoutExpired:
        logger.error("Receipt bundle recalculation timed out after %s seconds", timeout_seconds)
        return

    if result.returncode == 0:
        logger.info("Receipt bundle recalculation finished successfully")
        if result.stdout:
            logger.info("Receipt bundle recalculation output:\n%s", result.stdout.strip())
    else:
        logger.error("Receipt bundle recalculation failed with code %s", result.returncode)
        if result.stdout:
            logger.error("Receipt bundle recalculation stdout:\n%s", result.stdout.strip())
        if result.stderr:
            logger.error("Receipt bundle recalculation stderr:\n%s", result.stderr.strip())


async def receipt_bundle_recalc_loop(stop_event: asyncio.Event) -> None:
    hour = int(os.getenv("RECEIPT_BUNDLES_RECALC_HOUR", "4"))
    minute = int(os.getenv("RECEIPT_BUNDLES_RECALC_MINUTE", "30"))

    while not stop_event.is_set():
        try:
            wait_seconds = max(60, _seconds_until(hour, minute))
            logger.info(
                "Receipt bundle recalculation scheduled for %02d:%02d (waiting %.1f hours)",
                hour,
                minute,
                wait_seconds / 3600,
            )
            await asyncio.wait_for(stop_event.wait(), timeout=wait_seconds)
        except asyncio.TimeoutError:
            try:
                await run_receipt_bundle_recalc()
            except Exception as exc:
                logger.error("Receipt bundle recalculation failed: %s", exc, exc_info=True)


async def start_receipt_bundle_recalc_scheduler(app) -> None:
    if not _env_bool("RECEIPT_BUNDLES_RECALC_ENABLED", "true"):
        logger.info("Receipt bundle recalculation scheduler disabled by env.")
        return

    stop_event = asyncio.Event()
    task = asyncio.create_task(receipt_bundle_recalc_loop(stop_event))

    app.state.receipt_bundle_recalc_stop_event = stop_event
    app.state.receipt_bundle_recalc_task = task

    logger.info(
        "Receipt bundle recalculation scheduler started (time=%s:%s).",
        os.getenv("RECEIPT_BUNDLES_RECALC_HOUR", "4"),
        os.getenv("RECEIPT_BUNDLES_RECALC_MINUTE", "30"),
    )


async def stop_receipt_bundle_recalc_scheduler(app) -> None:
    stop_event = getattr(app.state, "receipt_bundle_recalc_stop_event", None)
    task = getattr(app.state, "receipt_bundle_recalc_task", None)

    if stop_event:
        stop_event.set()

    if task:
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except asyncio.TimeoutError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    logger.info("Receipt bundle recalculation scheduler stopped")
