from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.models.agent_interaction import AgentInteractionLog, AgentInteractionTask, InteractionStatus
from app.services.ai_core_runtime import generate_agent_text
from app.services.ai_crm_plan_service import GLAME_CRM_OPERATING_CONTEXT, extract_crm_plan_from_text
from app.services.telegram_agent_bridge_service import (
    build_telegram_prompt_context,
    build_telegram_task_payload,
    resolve_telegram_agent_route,
    stable_bridge_event_id,
)
from app.services.telegram_service import TelegramService

router = APIRouter(tags=["telegram-agent-bridge"])


class TelegramAgentMessageRequest(BaseModel):
    chat_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=12000)
    from_user: Optional[str] = Field(default=None, max_length=160)
    message_id: Optional[str] = Field(default=None, max_length=128)
    topic_id: Optional[str] = Field(default=None, max_length=128)
    board_id: Optional[str] = Field(default=None, max_length=64)
    model: Optional[str] = Field(default=None, max_length=160)
    send_reply: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    bridge_secret: Optional[str] = Field(default=None, max_length=512)


class TelegramAgentMessageResponse(BaseModel):
    ok: bool
    board_id: str
    target_agent: str
    task_id: str
    reply: str
    created_task: bool
    user_log_id: Optional[str] = None
    assistant_log_id: Optional[str] = None
    crm_plan_saved: bool = False
    telegram_send_result: Optional[Dict[str, Any]] = None


def _check_bridge_secret(body_secret: Optional[str], header_secret: Optional[str]) -> None:
    expected = (os.getenv("TELEGRAM_AGENT_BRIDGE_SECRET") or "").strip()
    if not expected:
        # Development mode: endpoint is still non-destructive and only stores agent dialog.
        return
    provided = (header_secret or body_secret or "").strip()
    if not provided or provided != expected:
        raise HTTPException(status_code=401, detail="Invalid Telegram agent bridge secret")


async def _ensure_telegram_task(db: AsyncSession, payload: Dict[str, Any]) -> tuple[AgentInteractionTask, bool]:
    context = dict(payload.get("task_context") or {})
    input_data = dict(payload.get("input_data") or {})
    key = context.get("idempotency_key") or input_data.get("idempotency_key")
    if key:
        existing_result = await db.execute(
            select(AgentInteractionTask)
            .where(
                AgentInteractionTask.status != InteractionStatus.DELETED.value,
                AgentInteractionTask.target_agent == payload["target_agent"],
                AgentInteractionTask.task_type == payload["task_type"],
            )
            .order_by(desc(AgentInteractionTask.created_at))
            .limit(100)
        )
        for task in existing_result.scalars().all():
            ctx = task.task_context or {}
            inp = task.input_data or {}
            if ctx.get("idempotency_key") == key or inp.get("idempotency_key") == key:
                return task, False

    task = AgentInteractionTask(
        source_agent=payload["source_agent"],
        target_agent=payload["target_agent"],
        task_type=payload["task_type"],
        task_context=context,
        input_data=input_data,
        requirements=payload.get("requirements") or {},
        priority=payload.get("priority") or 3,
        status=InteractionStatus.PENDING.value,
    )
    db.add(task)
    await db.flush()
    db.add(
        AgentInteractionLog(
            task_id=task.id,
            agent_name="telegram-bridge",
            event_type="board_task_ensured",
            event_data={"source": "telegram_agent_bridge", "idempotency_key": key, "created": True},
            message="Telegram bridge created platform task",
        )
    )
    await db.commit()
    await db.refresh(task)
    return task, True


async def _recent_dialog_history(db: AsyncSession, task_id: UUID, limit: int = 12) -> list[dict[str, Any]]:
    result = await db.execute(
        select(AgentInteractionLog)
        .where(AgentInteractionLog.task_id == task_id)
        .order_by(desc(AgentInteractionLog.created_at))
        .limit(limit)
    )
    logs = list(reversed(result.scalars().all()))
    history: list[dict[str, Any]] = []
    for log in logs:
        event_data = log.event_data if isinstance(log.event_data, dict) else {}
        role = event_data.get("role") or ("assistant" if log.agent_name != "telegram-bridge" else "user")
        history.append({"role": role, "message": log.message or ""})
    return history


@router.post("/telegram/agent/message", response_model=TelegramAgentMessageResponse)
async def telegram_agent_message(
    body: TelegramAgentMessageRequest,
    db: AsyncSession = Depends(get_db),
    x_glame_bridge_secret: Optional[str] = Header(default=None, alias="X-GLAME-Bridge-Secret"),
):
    """Telegram → platform agent bridge. Stores all work in agent_interaction_tasks / agent_interaction_logs."""
    _check_bridge_secret(body.bridge_secret, x_glame_bridge_secret)
    route = resolve_telegram_agent_route(body.message, body.board_id)
    payload = build_telegram_task_payload(
        board_id=route["board_id"],
        target_agent=route["target_agent"],
        task_type=route["task_type"],
        chat_id=body.chat_id,
        from_user=body.from_user,
        message=body.message,
        topic_id=body.topic_id,
        telegram_message_id=body.message_id,
    )
    task, created_task = await _ensure_telegram_task(db, payload)

    bridge_event_id = stable_bridge_event_id(body.chat_id, body.message_id, body.message)
    existing_log = await db.execute(
        select(AgentInteractionLog)
        .where(
            AgentInteractionLog.task_id == task.id,
            AgentInteractionLog.event_type == "dialog_message",
        )
        .order_by(desc(AgentInteractionLog.created_at))
        .limit(50)
    )
    duplicate = None
    for log in existing_log.scalars().all():
        event_data = log.event_data if isinstance(log.event_data, dict) else {}
        if event_data.get("bridge_event_id") == bridge_event_id:
            duplicate = log
            break
    if duplicate:
        return TelegramAgentMessageResponse(
            ok=True,
            board_id=route["board_id"],
            target_agent=route["target_agent"],
            task_id=str(task.id),
            reply="Сообщение уже сохранено на платформе; дубль не обрабатывал.",
            created_task=created_task,
            user_log_id=str(duplicate.id),
        )

    user_log = AgentInteractionLog(
        task_id=task.id,
        agent_name="telegram-bridge",
        event_type="dialog_message",
        event_data={
            "role": "user",
            "source": "telegram",
            "platform_bridge": "telegram",
            "bridge_event_id": bridge_event_id,
            "telegram_chat_id": body.chat_id,
            "telegram_message_id": body.message_id,
            "telegram_from_user": body.from_user,
            "metadata": body.metadata,
        },
        message=body.message,
    )
    db.add(user_log)
    await db.flush()

    history = await _recent_dialog_history(db, task.id, 16)
    prompt = build_telegram_prompt_context(
        board_id=route["board_id"],
        from_user=body.from_user,
        message=body.message,
        recent_history=history,
    )
    system_prompt = GLAME_CRM_OPERATING_CONTEXT if route["board_id"] == "crm" else None
    try:
        reply = await generate_agent_text(
            agent_id=route["target_agent"],
            prompt=prompt,
            system_prompt=system_prompt,
            model=body.model if body.model and "/" in body.model else None,
            temperature=0.6,
            max_tokens=4200,
        )
    except Exception as e:
        reply = (
            "Сообщение сохранено на GLAME Platform, но AI-ядро сейчас не ответило. "
            "Задача осталась в AI CRM/agent board, можно продолжить позже.\n\n"
            f"Техническая причина: {str(e)[:500]}"
        )

    if not isinstance(reply, str) or not reply.strip():
        reply = "Сообщение сохранено на GLAME Platform, но агент вернул пустой ответ. Задача не закрыта."

    output_data = dict(task.output_data or {})
    crm_plan_saved = False
    if route["board_id"] == "crm":
        try:
            crm_plan = extract_crm_plan_from_text(reply)
            if crm_plan.get("goal") or crm_plan.get("campaign_name") or crm_plan.get("scripts", {}).get("main_message"):
                output_data["crm_plan"] = crm_plan
                output_data["crm_plan_updated_from"] = "telegram_agent_bridge"
                output_data["crm_plan_updated_at"] = datetime.utcnow().isoformat()
                task.output_data = output_data
                crm_plan_saved = True
        except Exception:
            crm_plan_saved = False

    assistant_log = AgentInteractionLog(
        task_id=task.id,
        agent_name=route["target_agent"],
        event_type="dialog_message",
        event_data={
            "role": "assistant",
            "source": "telegram_agent_bridge",
            "platform_bridge": "telegram",
            "reply_to_bridge_event_id": bridge_event_id,
            "crm_plan_saved": crm_plan_saved,
        },
        message=reply,
    )
    db.add(assistant_log)
    await db.commit()
    await db.refresh(user_log)
    await db.refresh(assistant_log)

    telegram_send_result = None
    if body.send_reply:
        try:
            async with TelegramService() as telegram:
                telegram_send_result = await telegram.send_message(chat_id=body.chat_id, text=reply[:3900])
        except Exception as e:
            telegram_send_result = {"status": "failed", "error": str(e)[:500]}

    return TelegramAgentMessageResponse(
        ok=True,
        board_id=route["board_id"],
        target_agent=route["target_agent"],
        task_id=str(task.id),
        reply=reply,
        created_task=created_task,
        user_log_id=str(user_log.id),
        assistant_log_id=str(assistant_log.id),
        crm_plan_saved=crm_plan_saved,
        telegram_send_result=telegram_send_result,
    )
