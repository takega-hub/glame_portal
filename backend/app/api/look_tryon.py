from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Form
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Any
from pydantic import BaseModel
from app.database.connection import get_db, AsyncSessionLocal
from app.services.look_tryon_service import look_tryon_service
from app.agents.stylist_agent import StylistAgent
from uuid import UUID
import logging
import base64

logger = logging.getLogger(__name__)

router = APIRouter()


def _make_serializable(obj: Any) -> Any:
    """Рекурсивно преобразует объект в сериализуемый формат для JSON"""
    if isinstance(obj, bytes):
        # Конвертируем бинарные данные в base64 строку
        return base64.b64encode(obj).decode('utf-8')
    elif isinstance(obj, dict):
        return {key: _make_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_make_serializable(item) for item in obj]
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        # Для других типов пробуем преобразовать в строку
        return str(obj)


class PhotoAnalysisResponse(BaseModel):
    color_type: str
    style: str
    features: dict
    recommendations: dict


@router.post("/upload-photo", response_model=dict)
async def upload_user_photo(
    photo: UploadFile = File(...),
    user_id: Optional[str] = Query(None)
):
    """
    Загрузка фото пользователя
    
    Returns:
        dict: URL сохраненного фото и метаданные
    """
    try:
        user_uuid = UUID(user_id) if user_id else None
        
        if not user_uuid:
            raise HTTPException(
                status_code=400,
                detail="user_id обязателен для сохранения фото"
            )
        
        photo_data = await photo.read()
        
        photo_url = await look_tryon_service.save_user_photo(
            photo_data=photo_data,
            user_id=user_uuid,
            filename=photo.filename
        )
        
        return {
            "success": True,
            "photo_url": photo_url,
            "filename": photo.filename,
            "user_id": str(user_uuid)
        }
    except Exception as e:
        logger.exception("Ошибка при загрузке фото")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при загрузке фото: {str(e)}"
        )


@router.post("/analyze", response_model=PhotoAnalysisResponse)
async def analyze_user_photo(photo: UploadFile = File(...)):
    """
    Анализ фото пользователя (цветотип, стиль, тип внешности)
    
    Returns:
        PhotoAnalysisResponse: Результат анализа фото
    """
    try:
        photo_data = await photo.read()
        
        analysis = await look_tryon_service.analyze_photo(
            photo_data=photo_data,
            filename=photo.filename
        )
        
        return PhotoAnalysisResponse(**analysis)
    except UnicodeDecodeError as e:
        logger.exception("Ошибка кодировки при анализе фото")
        raise HTTPException(
            status_code=400,
            detail=f"Ошибка обработки изображения: файл поврежден или имеет неверный формат"
        )
    except Exception as e:
        logger.exception("Ошибка при анализе фото")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при анализе фото: {str(e)}"
        )


@router.post("/generate", response_model=dict)
async def generate_look_with_tryon(
    photo: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    look_id: Optional[str] = Form(None),
    user_request: Optional[str] = Form(None)
):
    """
    Генерация образа с примеркой на фото пользователя
    
    Args:
        photo: Фото пользователя
        user_id: ID пользователя (опционально)
        look_id: ID образа для примерки (опционально, если не указан - генерируется новый)
        user_request: Текстовый запрос для генерации (опционально)
    
    Returns:
        dict: Сгенерированный образ с результатом примерки
    """
    try:
        user_uuid = UUID(user_id) if user_id else None
        look_uuid = UUID(look_id) if look_id else None
        
        photo_data = await photo.read()
        
        async with AsyncSessionLocal() as db:
            agent = StylistAgent(db)
            
            # Если look_id указан, используем существующий образ
            if look_uuid:
                try_on_result = await agent.try_on_look(
                    look_id=look_uuid,
                    user_photo_data=photo_data,
                    user_id=user_uuid,
                    filename=photo.filename
                )
                # Убеждаемся, что все данные сериализуемы в JSON
                serializable_result = _make_serializable(try_on_result)
                
                return {
                    "success": True,
                    "look_id": str(look_uuid),
                    "try_on_result": serializable_result
                }
            else:
                # Генерируем новый образ
                # Сначала анализируем фото
                photo_analysis = await look_tryon_service.analyze_photo(
                    photo_data=photo_data,
                    filename=photo.filename
                )
                
                # Извлекаем параметры из анализа
                style = photo_analysis.get("style")
                recommendations = photo_analysis.get("recommendations", {})
                
                # Генерируем образ (с изображением на типовой модели, так как фото уже есть)
                generated_look = await agent.generate_look_for_user(
                    user_id=user_uuid,
                    session_id=None,
                    style=style,
                    mood=None,
                    persona=None,
                    user_request=user_request,
                    generate_image=True,
                    use_default_model=True  # Используем типовую модель для визуализации
                )
                
                # Примеряем сгенерированный образ
                if generated_look.get("id"):
                    look_id = UUID(generated_look["id"])
                    try_on_result = await agent.try_on_look(
                        look_id=look_id,
                        user_photo_data=photo_data,
                        user_id=user_uuid,
                        filename=photo.filename
                    )
                    
                    # Убеждаемся, что все данные сериализуемы в JSON
                    serializable_try_on = _make_serializable(try_on_result)
                    serializable_analysis = _make_serializable(photo_analysis)
                    serializable_look = _make_serializable(generated_look)
                    
                    return {
                        "success": True,
                        "generated_look": serializable_look,
                        "photo_analysis": serializable_analysis,
                        "try_on_result": serializable_try_on
                    }
                else:
                    # Убеждаемся, что все данные сериализуемы в JSON
                    serializable_analysis = _make_serializable(photo_analysis)
                    serializable_look = _make_serializable(generated_look)
                    
                    return {
                        "success": True,
                        "generated_look": serializable_look,
                        "photo_analysis": serializable_analysis,
                        "try_on_result": None
                    }
    except UnicodeDecodeError as e:
        logger.exception("Ошибка кодировки при генерации образа с примеркой")
        raise HTTPException(
            status_code=400,
            detail=f"Ошибка обработки изображения: файл поврежден или имеет неверный формат"
        )
    except Exception as e:
        logger.exception("Ошибка при генерации образа с примеркой")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при генерации образа с примеркой: {str(e)}"
        )
