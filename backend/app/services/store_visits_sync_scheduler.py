"""
Ночной планировщик синхронизации данных счетчиков магазинов с FTP сервера.
Использует существующий скрипт sync_ftp_stores.py
"""
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


async def run_nightly_store_visits_sync() -> None:
    """
    Ночная синхронизация данных счетчиков магазинов с FTP
    
    Требует настройки переменных окружения:
    - FTP_HOST: Хост FTP сервера
    - FTP_USERNAME: Имя пользователя FTP
    - FTP_PASSWORD: Пароль FTP
    - FTP_DIRECTORY: Директория на FTP сервере (по умолчанию /)
    """
    ftp_host = os.getenv("FTP_HOST")
    ftp_username = os.getenv("FTP_USERNAME")
    ftp_password = os.getenv("FTP_PASSWORD")
    
    if not all([ftp_host, ftp_username, ftp_password]):
        logger.warning("FTP credentials not set. Skipping nightly store visits sync.")
        logger.info("Для включения ночной синхронизации посещаемости установите переменные FTP_HOST, FTP_USERNAME, FTP_PASSWORD")
        return
    
    try:
        # Находим путь к скрипту sync_ftp_stores.py (он находится в корне проекта)
        project_root = Path(__file__).parent.parent.parent.parent
        script_path = project_root / "sync_ftp_stores.py"
        
        if not script_path.exists():
            logger.error(f"Script not found: {script_path}")
            return
        
        logger.info("Starting nightly store visits sync from FTP")
        
        # Запускаем скрипт синхронизации (UTF-8, чтобы не падать на cp1251 под Windows)
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600  # 10 минут таймаут
        )
        
        if result.returncode == 0:
            logger.info(f"Nightly store visits sync finished successfully")
            if result.stdout:
                logger.debug(f"Sync output: {result.stdout}")
        else:
            logger.error(f"Nightly store visits sync failed with code {result.returncode}")
            if result.stderr:
                logger.error(f"Error: {result.stderr}")
                
    except subprocess.TimeoutExpired:
        logger.error("Nightly store visits sync timed out after 10 minutes")
    except Exception as e:
        logger.error(f"Nightly store visits sync error: {e}", exc_info=True)


async def nightly_store_visits_sync_loop(stop_event: asyncio.Event) -> None:
    """Цикл ночной синхронизации посещаемости"""
    hour = int(os.getenv("STORE_VISITS_SYNC_NIGHTLY_HOUR", "3"))
    minute = int(os.getenv("STORE_VISITS_SYNC_NIGHTLY_MINUTE", "0"))
    
    while not stop_event.is_set():
        try:
            wait_seconds = max(60, _seconds_until(hour, minute))
            logger.info(f"Store visits sync scheduled for {hour:02d}:{minute:02d} (waiting {wait_seconds/3600:.1f} hours)")
            
            # Ждем до указанного времени или пока не будет остановки
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=wait_seconds)
                break  # Остановка запрошена
            except asyncio.TimeoutError:
                pass  # Время пришло
            
            # Выполняем синхронизацию
            await run_nightly_store_visits_sync()
            
            # Ждем до следующего дня (24 часа)
            await asyncio.sleep(86400)  # 24 часа
            
        except Exception as exc:
            logger.error("Nightly store visits sync failed: %s", exc, exc_info=True)
            # При ошибке ждем час перед повтором
            await asyncio.sleep(3600)


async def start_nightly_store_visits_sync_scheduler(app) -> None:
    """Запуск ночного планировщика синхронизации посещаемости"""
    if not _env_bool("STORE_VISITS_SYNC_NIGHTLY_ENABLED", "true"):
        logger.info("Nightly store visits sync scheduler disabled by env.")
        return
    
    stop_event = asyncio.Event()
    task = asyncio.create_task(nightly_store_visits_sync_loop(stop_event))
    
    app.state.nightly_store_visits_sync_stop_event = stop_event
    app.state.nightly_store_visits_sync_task = task
    
    logger.info(
        "Nightly store visits sync scheduler started (time=%s:%s).",
        os.getenv("STORE_VISITS_SYNC_NIGHTLY_HOUR", "3"),
        os.getenv("STORE_VISITS_SYNC_NIGHTLY_MINUTE", "0"),
    )


async def stop_nightly_store_visits_sync_scheduler(app) -> None:
    """Остановка ночного планировщика синхронизации посещаемости"""
    stop_event = getattr(app.state, "nightly_store_visits_sync_stop_event", None)
    task = getattr(app.state, "nightly_store_visits_sync_task", None)
    
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
    
    logger.info("Nightly store visits sync scheduler stopped")
