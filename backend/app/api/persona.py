from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any
from uuid import UUID
from app.database.connection import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.services.persona_service import PersonaService

router = APIRouter()


@router.get("/behavior")
async def get_user_behavior(
    days: int = 90,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Анализ поведения пользователя"""
    try:
        service = PersonaService(db)
        behavior = await service.analyze_user_behavior(current_user.id, days)
        return behavior
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing behavior: {str(e)}")


@router.get("/preferences")
async def get_user_preferences(
    days: int = 90,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Получение предпочтений пользователя"""
    try:
        service = PersonaService(db)
        preferences = await service.get_user_preferences(current_user.id, days)
        return preferences
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting preferences: {str(e)}")


@router.post("/update")
async def update_persona(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Обновление персоны пользователя на основе поведения"""
    try:
        service = PersonaService(db)
        behavior_data = await service.analyze_user_behavior(current_user.id)
        persona = await service.determine_persona(current_user.id, behavior_data)
        user = await service.update_user_persona(current_user.id, persona)
        
        return {
            "persona": persona,
            "user_id": str(user.id),
            "email": user.email
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating persona: {str(e)}")
