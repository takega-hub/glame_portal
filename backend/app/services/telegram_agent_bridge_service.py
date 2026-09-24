from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

CRM_KEYWORDS = {
    "crm",
    "црм",
    "клиент",
    "клиенты",
    "клиентам",
    "сегмент",
    "сегментация",
    "скрипт",
    "скрипты",
    "звонок",
    "обзвон",
    "сообщение",
    "рассылка",
    "ялта",
    "меганом",
    "центрум",
}

BOARD_AGENT_ROUTES: Dict[str, Dict[str, str]] = {
    "crm": {"board_id": "crm", "target_agent": "crm-agent", "task_type": "crm_telegram_dialog"},
    "analytics": {"board_id": "analytics", "target_agent": "analytics-agent", "task_type": "analytics_telegram_dialog"},
    "assortment": {"board_id": "assortment", "target_agent": "assortment-agent", "task_type": "assortment_telegram_dialog"},
    "brand-media": {"board_id": "brand-media", "target_agent": "brand-media-agent", "task_type": "brand_media_telegram_dialog"},
}


def normalize_topic_id(value: Optional[str]) -> str:
    text = str(value or "general").strip().lower()
    text = re.sub(r"[^a-zа-я0-9_-]+", "-", text, flags=re.IGNORECASE)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "general"


def resolve_telegram_agent_route(message: str, explicit_board_id: Optional[str] = None) -> Dict[str, str]:
    """Map a Telegram message to the platform agent board that must store the work."""
    board_id = normalize_topic_id(explicit_board_id) if explicit_board_id else ""
    if board_id in BOARD_AGENT_ROUTES:
        return dict(BOARD_AGENT_ROUTES[board_id])

    text = (message or "").lower()
    words = set(re.findall(r"[a-zа-я0-9_-]+", text, flags=re.IGNORECASE))
    if words & CRM_KEYWORDS:
        return dict(BOARD_AGENT_ROUTES["crm"])
    if any(word in words for word in {"аналитика", "отчет", "продажи", "выручка"}):
        return dict(BOARD_AGENT_ROUTES["analytics"])
    if any(word in words for word in {"ассортимент", "остатки", "товар", "бренд"}):
        return dict(BOARD_AGENT_ROUTES["assortment"])
    return dict(BOARD_AGENT_ROUTES["crm"])


def telegram_session_key(chat_id: str, topic_id: Optional[str], board_id: str) -> str:
    topic = normalize_topic_id(topic_id)
    return f"telegram:{chat_id}:{topic}:{board_id}"


def build_telegram_task_payload(
    *,
    board_id: str,
    target_agent: str,
    task_type: str,
    chat_id: str,
    from_user: Optional[str],
    message: str,
    topic_id: Optional[str] = None,
    telegram_message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build an idempotent platform task payload for Telegram-originated agent work."""
    topic = normalize_topic_id(topic_id or board_id)
    session_key = telegram_session_key(str(chat_id), topic, board_id)
    title_prefix = "Telegram CRM" if board_id == "crm" else f"Telegram {board_id}"
    speaker = (from_user or "Telegram user").strip()[:80]
    title = f"{title_prefix}: {speaker}"
    return {
        "source_agent": "telegram-bridge",
        "target_agent": target_agent,
        "task_type": task_type,
        "priority": 2 if board_id == "crm" else 3,
        "idempotency_key": session_key,
        "task_context": {
            "board": board_id,
            "agent_id": target_agent,
            "title": title,
            "idempotency_key": session_key,
            "platform_bridge": "telegram",
            "source_platform": "telegram",
            "source_of_truth": "glame_platform",
            "telegram_chat_id": str(chat_id),
            "telegram_topic_id": topic,
            "telegram_from_user": speaker,
            "last_telegram_message_id": str(telegram_message_id or ""),
            "created_from": "telegram_agent_bridge",
        },
        "input_data": {
            "source_board": board_id,
            "title": title,
            "description": message,
            "initial_admin_message": message,
            "expected_result": "Ответ AI-агента в Telegram и сохранённый результат на GLAME Platform.",
            "telegram_session_key": session_key,
        },
        "requirements": {
            "must_answer_telegram_message": True,
            "must_persist_platform_task": True,
            "telegram_is_input_platform_is_source_of_truth": True,
        },
    }


def build_telegram_prompt_context(
    *,
    board_id: str,
    from_user: Optional[str],
    message: str,
    recent_history: list[dict[str, Any]] | None = None,
) -> str:
    history_lines = []
    for item in (recent_history or [])[-12:]:
        role = item.get("role") or item.get("agent_name") or "log"
        content = str(item.get("content") or item.get("message") or "").strip()
        if content:
            history_lines.append(f"{role}: {content[:1200]}")
    history = "\n".join(history_lines) if history_lines else "Истории пока нет."
    crm_note = ""
    if board_id == "crm":
        crm_note = (
            "\nCRM режим: веди работу как с Еленой в Telegram, но фиксируй результат для платформы. "
            "Если сформирован итоговый CRM-план, верни его отдельным fenced JSON-блоком по crm_plan contract. "
            "Не запускай коммуникации без approval."
        )
    return (
        "=== TELEGRAM → GLAME PLATFORM AGENT BRIDGE ===\n"
        "Telegram остаётся удобным интерфейсом общения, но source of truth — GLAME Platform.\n"
        f"Доска: {board_id}\n"
        f"Пользователь Telegram: {from_user or 'unknown'}\n"
        f"Последняя история задачи:\n{history}\n\n"
        f"Новое сообщение из Telegram:\n{message}\n"
        f"{crm_note}\n"
    )


def stable_bridge_event_id(chat_id: str, message_id: Optional[str], message: str) -> str:
    seed = f"{chat_id}:{message_id or ''}:{message}".encode("utf-8", errors="ignore")
    return hashlib.sha256(seed).hexdigest()[:24]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
