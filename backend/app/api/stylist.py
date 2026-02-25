from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from app.database.connection import get_db, AsyncSessionLocal
from app.agents.stylist_agent import StylistAgent
from app.models.session import Session as DBSession

import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    user_id: Optional[str] = None
    message: str
    city: Optional[str] = None
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    persona: str
    cjm_stage: str
    reply: str
    looks: list
    products: Optional[list] = []  # Отдельный список товаров для отображения карточек
    cta: str
    session_id: str


class RecommendationRequest(BaseModel):
    user_id: Optional[str] = None
    persona: Optional[str] = None
    style: Optional[str] = None
    mood: Optional[str] = None
    city: Optional[str] = None


@router.post("/chat", response_model=ChatResponse)
async def chat_with_stylist(request: ChatRequest):
    """Диалог с AI стилистом.

    Важно: на Windows/psycopg/DB могут быть проблемы на старте. Этот endpoint
    всегда старается вернуть fallback-ответ вместо 500, чтобы UI не ломался.
    """
    try:
        # Безопасно парсим UUID — при ошибке просто игнорируем и работаем без них
        user_id: Optional[UUID] = None
        session_id: Optional[UUID] = None
        if request.user_id:
            try:
                user_id = UUID(request.user_id)
            except ValueError:
                logger.warning(f"Invalid user_id UUID: {request.user_id!r}, ignoring")
        if request.session_id:
            try:
                session_id = UUID(request.session_id)
            except ValueError:
                logger.warning(f"Invalid session_id UUID: {request.session_id!r}, starting new session")

        # Открываем DB-сессию вручную внутри try, чтобы перехватывать ошибки подключения
        async with AsyncSessionLocal() as db:
            agent = StylistAgent(db)

            result = await agent.process(
                user_id=user_id,
                message=request.message,
                city=request.city,
                session_id=session_id,
            )
            return ChatResponse(**result)
    except Exception as e:
        logger.exception("Stylist chat failed; returning fallback response")
        # Фолбэк без БД/LLM — гарантируем ответ для фронта
        from uuid import uuid4
        fallback_session_id = request.session_id or str(uuid4())
        return ChatResponse(
            persona="fashion_girl",
            cjm_stage="inspiration",
            reply=(
                f"Привет! Я вижу твой запрос: '{request.message}'. "
                f"Для романтического свидания рекомендую элегантные украшения от GLAME. "
                f"Хочешь посмотреть наши образы?"
            ),
            looks=[],
            products=[],  # Пустой список товаров в fallback
            cta=f"Записаться в пространство GLAME{' в ' + request.city if request.city else ''}",
            session_id=fallback_session_id,
        )


@router.post("/recommend")
async def get_recommendations(request: RecommendationRequest, db: AsyncSession = Depends(get_db)):
    """Получить рекомендации без диалога"""
    from app.services.recommendation_service import RecommendationService
    
    service = RecommendationService(db)
    
    products = await service.recommend_products(
        persona=request.persona,
        limit=10
    )
    
    looks = await service.recommend_looks(
        style=request.style,
        mood=request.mood,
        persona=request.persona,
        limit=5
    )
    
    return {
        "products": [
            {
                "id": str(p.id),
                "name": p.name,
                "brand": p.brand,
                "price": p.price,
                "images": p.images,
                "tags": p.tags
            }
            for p in products
        ],
        "looks": [
            {
                "id": str(l.id),
                "name": l.name,
                "style": l.style,
                "mood": l.mood,
                "description": l.description
            }
            for l in looks
        ]
    }


@router.get("/history/{session_id}")
async def get_history(session_id: str, db: AsyncSession = Depends(get_db)):
    """Получить историю взаимодействий"""
    result = await db.execute(
        select(DBSession).where(DBSession.id == UUID(session_id))
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "session_id": str(session.id),
        "user_id": str(session.user_id) if session.user_id else None,
        "persona": session.persona_detected,
        "cjm_stage": session.cjm_stage,
        "interactions": session.interactions,
        "created_at": session.created_at.isoformat() if session.created_at else None
    }
