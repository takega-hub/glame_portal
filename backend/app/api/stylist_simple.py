"""
Упрощенная версия stylist API без подключения к БД для тестирования
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

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
    cta: str
    session_id: str


@router.post("/chat", response_model=ChatResponse)
async def chat_with_stylist_simple(request: ChatRequest):
    """Упрощенный диалог с AI стилистом без БД"""
    print(f"Received request: {request.message}")
    try:
        from app.services.llm_service import llm_service
        print("LLM service imported")
    except Exception as e:
        print(f"Error importing LLM service: {e}")
        # Возвращаем fallback ответ без LLM
        return ChatResponse(
            persona="fashion_girl",
            cjm_stage="inspiration",
            reply=f"Привет! Я вижу твой запрос: '{request.message}'. Для романтического свидания рекомендую элегантные украшения от GLAME. Хочешь посмотреть наши образы?",
            looks=[],
            cta="Записаться в пространство GLAME",
            session_id="test-session-123"
        )
    
    # Простой ответ без использования БД
    try:
        prompt = f"""Пользователь написал: "{request.message}"

Ты - персональный стилист бренда GLAME, пространства авторских украшений и аксессуаров.

GLAME - это место, где стиль становится отражением характера. Мы предлагаем уникальные украшения от известных брендов: Antura, Uno de 50, и других.

Сформируй дружелюбный ответ стилиста:
1. Поприветствуй и покажи понимание запроса
2. Предложи образ для ситуации
3. Предложи действие: купить онлайн или записаться в пространство GLAME{' в ' + request.city if request.city else ''}

Будь вдохновляющим и профессиональным."""
        
        reply = await llm_service.generate(
            prompt=prompt,
            system_prompt="Ты - персональный стилист бренда GLAME. Отвечай дружелюбно и профессионально.",
            temperature=0.8
        )
        
        return ChatResponse(
            persona="fashion_girl",
            cjm_stage="inspiration",
            reply=reply,
            looks=[],
            cta=f"Записаться в пространство GLAME{' в ' + request.city if request.city else ''}",
            session_id="test-session-123"
        )
    except Exception as e:
        # Fallback ответ
        return ChatResponse(
            persona="fashion_girl",
            cjm_stage="inspiration",
            reply=f"Привет! Я вижу, что ты ищешь образ. Для начала работы с AI стилистом нужно настроить подключение к базе данных. Твой запрос: {request.message}",
            looks=[],
            cta="Записаться в пространство GLAME",
            session_id="test-session-123"
        )
