from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import logging
import asyncio
import time

from app.database.connection import get_db, AsyncSessionLocal
from app.models.look import Look
from app.agents.stylist_agent import StylistAgent

logger = logging.getLogger(__name__)

router = APIRouter()


class LookResponse(BaseModel):
    id: str
    name: str
    product_ids: List[str]
    style: str | None = None
    mood: str | None = None
    description: str | None = None
    image_url: str | None = None


class LookGenerateRequest(BaseModel):
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    style: Optional[str] = None
    mood: Optional[str] = None
    persona: Optional[str] = None
    user_request: Optional[str] = None
    generate_image: bool = True
    use_default_model: bool = False


class LookTryOnRequest(BaseModel):
    user_id: Optional[str] = None


class LookUpdateRequest(BaseModel):
    name: Optional[str] = None
    style: Optional[str] = None
    mood: Optional[str] = None
    description: Optional[str] = None
    product_ids: Optional[List[str]] = None
    regenerate_image: bool = False
    use_default_model: bool = False


@router.get("/", response_model=List[LookResponse])
async def get_looks(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    style: Optional[str] = None,
    mood: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(Look)
    
    if style:
        query = query.where(Look.style == style)
    if mood:
        query = query.where(Look.mood == mood)
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    looks = result.scalars().all()
    
    # Конвертируем UUID в строки для ответа
    looks_list = []
    for look in looks:
        # Определяем основное изображение из image_urls или используем image_url
        image_url = None
        if look.image_urls and len(look.image_urls) > 0:
            current_idx = look.current_image_index if look.current_image_index is not None else 0
            if current_idx < len(look.image_urls):
                image_data = look.image_urls[current_idx]
                if isinstance(image_data, dict):
                    image_url = image_data.get("url")
                else:
                    image_url = image_data
        elif look.image_url:
            image_url = look.image_url
        
        # Исправляем опечатку в image_url (lcimages -> look_images)
        if image_url and "/static/lcimages/" in image_url:
            image_url = image_url.replace("/static/lcimages/", "/static/look_images/")
        
        try_on_image_url = look.try_on_image_url
        if try_on_image_url and "/static/lcimages/" in try_on_image_url:
            try_on_image_url = try_on_image_url.replace("/static/lcimages/", "/static/look_images/")
        
        look_dict = {
            "id": str(look.id),
            "name": look.name,
            "product_ids": [str(pid) for pid in (look.product_ids or [])],
            "style": look.style,
            "mood": look.mood,
            "description": look.description,
            "image_url": image_url,
            "image_urls": look.image_urls or [],
            "current_image_index": look.current_image_index,
            "status": look.status,
            "approval_status": look.approval_status,
            "try_on_image_url": try_on_image_url,
        }
        looks_list.append(look_dict)
    
    return looks_list


@router.get("/{look_id}", response_model=dict)
async def get_look(look_id: UUID, db: AsyncSession = Depends(get_db)):
    """Получение образа с продуктами"""
    try:
        result = await db.execute(select(Look).where(Look.id == look_id))
        look = result.scalar_one_or_none()
        if not look:
            raise HTTPException(status_code=404, detail="Look not found")
        
        # Получаем продукты для образа
        from app.agents.stylist_agent import StylistAgent
        stylist_agent = StylistAgent(db)
        products = await stylist_agent.recommendation_service.get_look_products(look.id)
        
        # Определяем основное изображение из image_urls или используем image_url
        image_url = None
        if look.image_urls and len(look.image_urls) > 0:
            current_idx = look.current_image_index if look.current_image_index is not None else 0
            if current_idx < len(look.image_urls):
                image_data = look.image_urls[current_idx]
                if isinstance(image_data, dict):
                    image_url = image_data.get("url")
                else:
                    image_url = image_data
        elif look.image_url:
            image_url = look.image_url
        
        # Исправляем опечатку в image_url (lcimages -> look_images)
        if image_url and "/static/lcimages/" in image_url:
            image_url = image_url.replace("/static/lcimages/", "/static/look_images/")
        
        try_on_image_url = look.try_on_image_url
        if try_on_image_url and "/static/lcimages/" in try_on_image_url:
            try_on_image_url = try_on_image_url.replace("/static/lcimages/", "/static/look_images/")
        
        return {
            "id": str(look.id),
            "name": look.name,
            "product_ids": [str(pid) for pid in (look.product_ids or [])],
            "style": look.style,
            "mood": look.mood,
            "description": look.description,
            "image_url": image_url,
            "image_urls": look.image_urls or [],
            "current_image_index": look.current_image_index,
            "status": look.status,
            "approval_status": look.approval_status,
            "try_on_image_url": try_on_image_url,
            "products": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "brand": p.brand,
                    "price": p.price,
                    "images": p.images if p.images is not None else [],
                    "category": p.category,
                    "tags": p.tags if p.tags is not None else []
                }
                for p in products
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка при получении образа")
        raise HTTPException(status_code=500, detail=f"Ошибка при получении образа: {str(e)}")


@router.post("/generate", response_model=dict)
async def generate_look(request: LookGenerateRequest):
    """Генерация образа на основе запроса"""
    import time
    start_time = time.time()
    
    try:
        user_id = UUID(request.user_id) if request.user_id else None
        session_id = UUID(request.session_id) if request.session_id else None
        
        logger.info(f"Начало генерации образа для user_id={user_id}, generate_image={request.generate_image}")
        
        async with AsyncSessionLocal() as db:
            agent = StylistAgent(db)
            
            result = await agent.generate_look_for_user(
                user_id=user_id,
                session_id=session_id,
                style=request.style,
                mood=request.mood,
                persona=request.persona,
                user_request=request.user_request,
                generate_image=request.generate_image,
                use_default_model=request.use_default_model
            )
            
            elapsed_time = time.time() - start_time
            logger.info(f"Генерация образа завершена за {elapsed_time:.2f} секунд. Look ID: {result.get('id')}")
            
            return result
    except asyncio.TimeoutError:
        elapsed_time = time.time() - start_time
        logger.warning(f"Таймаут при генерации образа после {elapsed_time:.2f} секунд")
        raise HTTPException(
            status_code=504,
            detail="Генерация образа занимает больше времени, чем ожидалось. Образ может быть создан в фоновом режиме. Проверьте список образов через несколько минут."
        )
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.exception(f"Ошибка при генерации образа после {elapsed_time:.2f} секунд: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка при генерации образа: {str(e)}")


@router.post("/{look_id}/try-on", response_model=dict)
async def try_on_look(
    look_id: UUID,
    photo: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """Примерка образа на фото пользователя"""
    try:
        user_uuid = UUID(user_id) if user_id else None
        
        # Читаем фото как бинарные данные
        photo_data = await photo.read()
        
        # Используем StylistAgent для примерки
        agent = StylistAgent(db)
        
        try_on_result = await agent.try_on_look(
            look_id=look_id,
            user_photo_data=photo_data,
            user_id=user_uuid,
            filename=photo.filename
        )
        
        # Убеждаемся, что все данные сериализуемы в JSON
        from app.api.look_tryon import _make_serializable
        serializable_result = _make_serializable(try_on_result)
        
        return serializable_result
    except UnicodeDecodeError as e:
        logger.exception("Ошибка кодировки при примерке образа")
        raise HTTPException(
            status_code=400,
            detail=f"Ошибка обработки изображения: файл поврежден или имеет неверный формат"
        )
    except Exception as e:
        logger.exception("Ошибка при примерке образа")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при примерке образа: {str(e)}"
        )


@router.put("/{look_id}", response_model=dict)
async def update_look(
    look_id: UUID,
    request: LookUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Обновление образа"""
    try:
        result = await db.execute(select(Look).where(Look.id == look_id))
        look = result.scalar_one_or_none()
        
        if not look:
            raise HTTPException(status_code=404, detail="Look not found")
        
        # Обновляем поля, если они указаны
        if request.name is not None:
            look.name = request.name
        if request.style is not None:
            look.style = request.style
        if request.mood is not None:
            look.mood = request.mood
        if request.description is not None:
            look.description = request.description
        if request.product_ids is not None:
            look.product_ids = request.product_ids
        
        # Перегенерация изображения, если запрошена
        if request.regenerate_image:
            try:
                from app.services.image_generation_service import image_generation_service
                # Устанавливаем сессию БД для сервиса
                image_generation_service.set_db_session(db)
                
                image_url = await image_generation_service.generate_look_image_from_look(
                    look_id=look_id,
                    use_default_model=request.use_default_model
                )
                if image_url:
                    look.image_url = image_url
                else:
                    logger.warning(f"Image generation returned None for look {look_id}")
            except Exception as e:
                logger.exception(f"Error regenerating image for look {look_id}: {e}")
                # Не прерываем обновление образа, если генерация изображения не удалась
                # Просто логируем ошибку
        
        await db.commit()
        await db.refresh(look)
        
        # Получаем продукты для ответа
        try:
            stylist_agent = StylistAgent(db)
            products = await stylist_agent.recommendation_service.get_look_products(look.id)
        except Exception as e:
            logger.warning(f"Error loading products for look {look_id}: {e}")
            products = []
        
        # Исправляем возможную опечатку в URL
        image_url = look.image_url
        if image_url and "/static/lcimages/" in image_url:
            image_url = image_url.replace("/static/lcimages/", "/static/look_images/")
        
        try_on_image_url = look.try_on_image_url
        if try_on_image_url and "/static/lcimages/" in try_on_image_url:
            try_on_image_url = try_on_image_url.replace("/static/lcimages/", "/static/look_images/")
        
        return {
            "id": str(look.id),
            "name": look.name,
            "product_ids": [str(pid) for pid in (look.product_ids or [])],
            "style": look.style,
            "mood": look.mood,
            "description": look.description,
            "image_url": image_url,
            "status": look.status,
            "approval_status": look.approval_status,
            "try_on_image_url": try_on_image_url,
            "products": [
                {
                    "id": str(p.id),
                    "name": p.name or "",
                    "brand": p.brand or None,
                    "price": float(p.price) if p.price else 0.0,
                    "images": p.images if p.images is not None else [],
                    "category": p.category or None,
                    "tags": p.tags if p.tags is not None else []
                }
                for p in products
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка при обновлении образа")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при обновлении образа: {str(e)}")


@router.delete("/{look_id}", response_model=dict)
async def delete_look(look_id: UUID, db: AsyncSession = Depends(get_db)):
    """Удаление образа"""
    try:
        result = await db.execute(select(Look).where(Look.id == look_id))
        look = result.scalar_one_or_none()
        
        if not look:
            raise HTTPException(status_code=404, detail="Look not found")
        
        await db.delete(look)
        await db.commit()
        
        return {"success": True, "message": f"Look {look_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка при удалении образа")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении образа: {str(e)}")


@router.delete("/", response_model=dict)
async def delete_test_looks(
    confirm: bool = Query(False, description="Подтверждение удаления всех тестовых образов"),
    db: AsyncSession = Depends(get_db)
):
    """Удаление всех тестовых образов"""
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Для удаления всех тестовых образов необходимо установить confirm=true"
        )
    
    try:
        # Удаляем тестовые образы по именам
        test_look_names = [
            "Романтичный вечер",
            "Повседневный стиль"
        ]
        
        result = await db.execute(
            select(Look).where(Look.name.in_(test_look_names))
        )
        test_looks = result.scalars().all()
        
        deleted_count = 0
        for look in test_looks:
            await db.delete(look)
            deleted_count += 1
        
        await db.commit()
        
        return {
            "success": True,
            "message": f"Удалено тестовых образов: {deleted_count}",
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.exception("Ошибка при удалении тестовых образов")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении тестовых образов: {str(e)}")


@router.post("/{look_id}/generate-image", response_model=dict)
async def generate_look_image_endpoint(
    look_id: UUID,
    use_default_model: bool = Query(False),
    db: AsyncSession = Depends(get_db)
):
    """Генерация изображения для существующего образа"""
    from app.services.image_generation_service import image_generation_service
    
    try:
        image_url = await image_generation_service.generate_look_image_from_look(
            look_id=look_id,
            use_default_model=use_default_model
        )
        
        if not image_url:
            raise HTTPException(status_code=404, detail="Образ не найден или не удалось сгенерировать изображение")
        
        # Обновляем образ с URL изображения
        result = await db.execute(select(Look).where(Look.id == look_id))
        look = result.scalar_one_or_none()
        
        if look:
            # Добавляем новое изображение в массив image_urls
            if look.image_urls is None:
                look.image_urls = []
            
            # Создаем объект изображения с метаданными
            image_data = {
                "url": image_url,
                "generated_at": datetime.now().isoformat(),
                "use_default_model": use_default_model
            }
            
            look.image_urls.append(image_data)
            
            # Устанавливаем новое изображение как текущее
            look.current_image_index = len(look.image_urls) - 1
            
            # Обновляем image_url для обратной совместимости
            look.image_url = image_url
            
            await db.commit()
            await db.refresh(look)
        
        return {
            "look_id": str(look_id),
            "image_url": image_url,
            "image_urls": look.image_urls if look else [],
            "current_image_index": look.current_image_index if look else None,
            "use_default_model": use_default_model
        }
    except Exception as e:
        logger.exception("Ошибка при генерации изображения образа")
        raise HTTPException(status_code=500, detail=f"Ошибка при генерации изображения: {str(e)}")


@router.post("/{look_id}/approve", response_model=dict)
async def approve_look(
    look_id: UUID,
    user_id: Optional[str] = Query(None)
):
    """Одобрение сгенерированного образа"""
    try:
        user_uuid = UUID(user_id) if user_id else None
        
        async with AsyncSessionLocal() as db:
            agent = StylistAgent(db)
            
            result = await agent.approve_look(
                look_id=look_id,
                user_id=user_uuid
            )
            
            if not result:
                raise HTTPException(status_code=404, detail="Образ не найден")
            
            return {
                "look_id": str(look_id),
                "approval_status": result.approval_status,
                "status": result.status
            }
    except Exception as e:
        logger.exception("Ошибка при одобрении образа")
        raise HTTPException(status_code=500, detail=f"Ошибка при одобрении образа: {str(e)}")


@router.put("/{look_id}/set-main-image", response_model=dict)
async def set_main_image(
    look_id: UUID,
    image_index: int = Query(..., ge=0, description="Индекс изображения в массиве image_urls"),
    db: AsyncSession = Depends(get_db)
):
    """Установка основного изображения образа"""
    try:
        result = await db.execute(select(Look).where(Look.id == look_id))
        look = result.scalar_one_or_none()
        
        if not look:
            raise HTTPException(status_code=404, detail="Look not found")
        
        if not look.image_urls or len(look.image_urls) == 0:
            raise HTTPException(status_code=400, detail="У образа нет изображений")
        
        if image_index >= len(look.image_urls):
            raise HTTPException(status_code=400, detail=f"Индекс {image_index} выходит за пределы массива изображений")
        
        look.current_image_index = image_index
        
        # Обновляем image_url для обратной совместимости
        image_data = look.image_urls[image_index]
        if isinstance(image_data, dict):
            look.image_url = image_data.get("url")
        else:
            look.image_url = image_data
        
        await db.commit()
        await db.refresh(look)
        
        return {
            "success": True,
            "look_id": str(look_id),
            "current_image_index": look.current_image_index,
            "image_url": look.image_url
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка при установке основного изображения")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при установке основного изображения: {str(e)}")


@router.delete("/{look_id}/image/{image_index}", response_model=dict)
async def delete_look_image(
    look_id: UUID,
    image_index: int,
    db: AsyncSession = Depends(get_db)
):
    """Удаление изображения из образа"""
    try:
        result = await db.execute(select(Look).where(Look.id == look_id))
        look = result.scalar_one_or_none()
        
        if not look:
            raise HTTPException(status_code=404, detail="Look not found")
        
        if not look.image_urls or len(look.image_urls) == 0:
            raise HTTPException(status_code=400, detail="У образа нет изображений")
        
        if image_index >= len(look.image_urls):
            raise HTTPException(status_code=400, detail=f"Индекс {image_index} выходит за пределы массива изображений")
        
        # Удаляем изображение
        look.image_urls.pop(image_index)
        
        # Обновляем current_image_index
        if look.current_image_index is not None:
            if look.current_image_index >= len(look.image_urls):
                # Если удалили текущее или последующее, устанавливаем последнее
                look.current_image_index = len(look.image_urls) - 1 if len(look.image_urls) > 0 else None
            elif look.current_image_index > image_index:
                # Если удалили изображение до текущего, уменьшаем индекс
                look.current_image_index -= 1
        
        # Обновляем image_url для обратной совместимости
        if look.image_urls and len(look.image_urls) > 0 and look.current_image_index is not None:
            image_data = look.image_urls[look.current_image_index]
            if isinstance(image_data, dict):
                look.image_url = image_data.get("url")
            else:
                look.image_url = image_data
        else:
            look.image_url = None
            look.current_image_index = None
        
        await db.commit()
        await db.refresh(look)
        
        return {
            "success": True,
            "look_id": str(look_id),
            "remaining_images": len(look.image_urls),
            "current_image_index": look.current_image_index
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка при удалении изображения")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении изображения: {str(e)}")
