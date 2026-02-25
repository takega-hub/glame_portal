"""
API endpoints для синхронизации каталога товаров с 1С
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from pydantic import BaseModel
import os
import tempfile
import logging
from app.database.connection import get_db
from app.services.onec_sync_service import OneCSyncService

router = APIRouter(prefix="/api/1c", tags=["1C Sync"])
logger = logging.getLogger(__name__)


# УДАЛЕНО: SyncFromTildaRequest - работаем только с файлами выгрузки 1С

class SyncFromYmlRequest(BaseModel):
    """Запрос на синхронизацию из YML файла"""
    yml_url: str
    update_existing: bool = True
    deactivate_missing: bool = False


class SyncResponse(BaseModel):
    """Ответ с результатами синхронизации"""
    success: bool
    message: str
    stats: Optional[dict] = None


# УДАЛЕНО: Синхронизация товаров через REST API
# Товары теперь загружаются только через XML (CommerceML)
# REST API используется только для покупателей и продаж
# 
# @router.post("/sync/api", response_model=SyncResponse)
# async def sync_from_api(...):
#     ...


@router.post("/sync/file", response_model=SyncResponse)
async def sync_from_file(
    file: UploadFile = File(...),
    update_existing: bool = True,
    deactivate_missing: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """
    Синхронизация каталога товаров из файла
    
    Поддерживает следующие форматы:
    - JSON файлы с массивом товаров из 1С
    - XML файлы в формате CommerceML (стандартный формат 1С для интернет-магазинов)
    
    CommerceML файлы можно получить в 1С через:
    УНФ → CRM и маркетинг → Интернет-магазин → Настроить обмен → Выгрузка каталога
    """
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Имя файла не указано"
        )
    
    # Определяем расширение файла
    file_ext = file.filename.lower().split('.')[-1] if '.' in file.filename else ''
    
    if file_ext not in ['json', 'xml']:
        raise HTTPException(
            status_code=400,
            detail="Поддерживаются только JSON и XML файлы (включая CommerceML)"
        )
    
    # Сохраняем файл во временную директорию
    temp_file = None
    try:
        suffix = f'.{file_ext}'
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            temp_file = tmp.name
        
        sync_service = OneCSyncService(db)
        stats = await sync_service.sync_from_file(
            file_path=temp_file,
            update_existing=update_existing,
            deactivate_missing=deactivate_missing
        )
        
        file_type = "CommerceML XML" if file_ext == 'xml' else "JSON"
        return SyncResponse(
            success=True,
            message=f"Синхронизация из {file_type} файла успешно завершена",
            stats=stats
        )
    except Exception as e:
        logger.error(f"Ошибка синхронизации из файла: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка синхронизации: {str(e)}"
        )
    finally:
        # Удаляем временный файл
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except Exception as e:
                logger.warning(f"Не удалось удалить временный файл: {e}")


# УДАЛЕНО: @router.post("/sync/tilda") - работаем только с файлами выгрузки 1С


@router.post("/sync/yml", response_model=SyncResponse)
async def sync_from_yml(
    request: SyncFromYmlRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Синхронизация каталога товаров из YML (Yandex Market Language) файла
    
    YML - формат экспорта товаров для Яндекс.Маркет и других маркетплейсов.
    Поддерживает загрузку по URL или из файла.
    
    Пример URL: https://glamejewelry.ru/tstore/yml/b743eb13397ad6a83d95caf72d40b7b2.yml
    """
    try:
        sync_service = OneCSyncService(db)
        stats = await sync_service.sync_from_yml(
            yml_url=request.yml_url,
            update_existing=request.update_existing,
            deactivate_missing=request.deactivate_missing
        )
        
        return SyncResponse(
            success=True,
            message="Синхронизация из YML файла успешно завершена",
            stats=stats
        )
    except ValueError as e:
        error_msg = str(e)
        logger.error(f"Ошибка синхронизации из YML: {error_msg}")
        
        if "404" in error_msg or "не найден" in error_msg.lower() or "not found" in error_msg.lower():
            detail = (
                f"YML файл не найден или недоступен.\n\n"
                f"URL: {request.yml_url}\n\n"
                f"Возможные причины:\n"
                f"1. URL недоступен или неправильный\n"
                f"2. Файл был удален или перемещен\n"
                f"3. Проблемы с доступом к серверу\n\n"
                f"Проверьте URL в браузере: {request.yml_url}"
            )
            status_code = 404
        elif "не найден элемент" in error_msg.lower() or "товары не найдены" in error_msg.lower():
            detail = (
                f"Проблема с форматом YML файла:\n\n{error_msg}\n\n"
                f"Проверьте структуру YML файла. Должна быть следующая структура:\n"
                f"- yml_catalog\n"
                f"  - shop\n"
                f"    - offers\n"
                f"      - offer (множество товаров)"
            )
            status_code = 400
        else:
            detail = error_msg
            status_code = 400
            
        raise HTTPException(
            status_code=status_code,
            detail=detail
        )
    except Exception as e:
        logger.error(f"Ошибка синхронизации из YML: {e}", exc_info=True)
        error_msg = str(e)
        
        # Более понятные сообщения об ошибках
        if "404" in error_msg or "not found" in error_msg.lower():
            detail = (
                f"YML файл не найден (404): {request.yml_url}\n\n"
                f"Проверьте правильность URL и доступность файла."
            )
        elif "connection" in error_msg.lower() or "timeout" in error_msg.lower():
            detail = (
                f"Ошибка подключения к YML файлу: {error_msg}\n\n"
                f"Проверьте доступность сервера и правильность URL."
            )
        else:
            detail = f"Ошибка синхронизации из YML: {error_msg}"
        
        raise HTTPException(
            status_code=500,
            detail=detail
        )


@router.get("/sync/status")
async def get_sync_status(db: AsyncSession = Depends(get_db)):
    """
    Получение статуса синхронизации каталога
    
    Возвращает статистику по товарам:
    - Всего товаров
    - Активных товаров
    - Товаров с external_id (синхронизированных)
    - Последняя синхронизация
    """
    from app.models.product import Product

    total = (await db.execute(select(func.count()).select_from(Product))).scalar_one()
    active = (await db.execute(
        select(func.count()).select_from(Product).where(Product.is_active == True)
    )).scalar_one()
    synced = (await db.execute(
        select(func.count()).select_from(Product).where(Product.external_id.isnot(None))
    )).scalar_one()

    # Получаем последнюю дату синхронизации
    last_sync_product = (await db.execute(
        select(Product)
        .where(Product.sync_metadata.isnot(None))
        .order_by(Product.updated_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    
    last_sync = None
    if last_sync_product and last_sync_product.sync_metadata:
        last_sync = last_sync_product.sync_metadata.get("last_sync")
    
    return {
        "total_products": total,
        "active_products": active,
        "synced_products": synced,
        "last_sync": last_sync,
        "sync_coverage": round((synced / total * 100) if total > 0 else 0, 2)
    }
