"""
API endpoints для работы с разделами каталога из 1С.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel
import logging

from app.database.connection import get_db
from app.models.catalog_section import CatalogSection

router = APIRouter()
logger = logging.getLogger(__name__)


class CatalogSectionResponse(BaseModel):
    id: str
    external_id: str
    external_code: str | None
    name: str
    parent_external_id: str | None
    description: str | None
    is_active: bool
    sync_status: str | None
    
    class Config:
        from_attributes = True


@router.get("/", response_model=List[CatalogSectionResponse])
async def get_catalog_sections(
    is_active: Optional[bool] = Query(None, description="Фильтр по активности"),
    include_inactive: bool = Query(False, description="Включить неактивные разделы"),
    db: AsyncSession = Depends(get_db),
):
    """
    Получить список разделов каталога.
    
    По умолчанию возвращает только активные разделы.
    Используйте include_inactive=true для получения всех разделов.
    """
    try:
        query = select(CatalogSection)
        
        if is_active is not None:
            query = query.where(CatalogSection.is_active == is_active)
        elif not include_inactive:
            # По умолчанию показываем только активные
            query = query.where(CatalogSection.is_active == True)
        
        query = query.order_by(CatalogSection.name)
        
        result = await db.execute(query)
        sections = result.scalars().all()
        
        return [
            CatalogSectionResponse(
                id=str(section.id),
                external_id=section.external_id,
                external_code=section.external_code,
                name=section.name,
                parent_external_id=section.parent_external_id,
                description=section.description,
                is_active=section.is_active,
                sync_status=section.sync_status,
            )
            for section in sections
        ]
    except Exception as e:
        logger.error(f"Ошибка при получении разделов каталога: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке разделов: {str(e)}")


@router.get("/{section_id}", response_model=CatalogSectionResponse)
async def get_catalog_section(
    section_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Получить раздел каталога по ID.
    """
    try:
        result = await db.execute(
            select(CatalogSection).where(CatalogSection.id == section_id)
        )
        section = result.scalar_one_or_none()
        
        if not section:
            raise HTTPException(status_code=404, detail="Раздел каталога не найден")
        
        return CatalogSectionResponse(
            id=str(section.id),
            external_id=section.external_id,
            external_code=section.external_code,
            name=section.name,
            parent_external_id=section.parent_external_id,
            description=section.description,
            is_active=section.is_active,
            sync_status=section.sync_status,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении раздела каталога {section_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке раздела: {str(e)}")
