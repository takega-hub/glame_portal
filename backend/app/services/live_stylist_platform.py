from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.live_stylist_conversation import LiveStylistConversation
from app.models.live_stylist_conversation_event import LiveStylistConversationEvent


CONVERSATION_STATUSES = {"requested", "in_progress", "completed"}
CONVERSATION_PRIORITIES = {"normal", "high"}
PURCHASE_OUTCOMES = {"unknown", "not_purchased", "purchased_recommended", "purchased_other"}


def normalize_conversation_status(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in CONVERSATION_STATUSES else "requested"


def normalize_conversation_priority(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in CONVERSATION_PRIORITIES else "normal"


def normalize_purchase_outcome(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in PURCHASE_OUTCOMES else "unknown"


def status_label(value: str | None) -> str:
    return {
        "requested": "Запрос",
        "in_progress": "В обработке",
        "completed": "Завершено",
    }.get(normalize_conversation_status(value), "Запрос")


def priority_label(value: str | None) -> str:
    return {
        "normal": "Обычный",
        "high": "Высокий",
    }.get(normalize_conversation_priority(value), "Обычный")


def purchase_outcome_label(value: str | None) -> str:
    return {
        "unknown": "Не отмечено",
        "not_purchased": "Не купил",
        "purchased_recommended": "Купил подобранные",
        "purchased_other": "Купил другие",
    }.get(normalize_purchase_outcome(value), "Не отмечено")


async def ensure_live_stylist_schema(db: AsyncSession) -> None:
    """Safety net if migrations were not applied yet."""
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS live_stylist_conversations (
                id UUID PRIMARY KEY,
                customer_user_id UUID NOT NULL REFERENCES users(id),
                assigned_stylist_user_id UUID NULL REFERENCES users(id),
                source VARCHAR(100) NULL,
                scenario VARCHAR(100) NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'requested',
                priority VARCHAR(16) NOT NULL DEFAULT 'normal',
                initial_working_hours_status VARCHAR(16) NULL,
                unread_for_stylist_count INTEGER NOT NULL DEFAULT 0,
                unread_for_customer_count INTEGER NOT NULL DEFAULT 0,
                recommended_product_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                internal_notes TEXT NULL,
                result_purchase_status VARCHAR(32) NOT NULL DEFAULT 'unknown',
                result_order_id UUID NULL,
                result_notes TEXT NULL,
                meta JSONB NOT NULL DEFAULT '{}'::jsonb,
                assigned_at TIMESTAMPTZ NULL,
                first_response_at TIMESTAMPTZ NULL,
                last_message_at TIMESTAMPTZ NULL,
                last_customer_message_at TIMESTAMPTZ NULL,
                last_stylist_message_at TIMESTAMPTZ NULL,
                closed_at TIMESTAMPTZ NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
    )
    await db.execute(
        text(
            """
            ALTER TABLE stylist_chat_messages
            ADD COLUMN IF NOT EXISTS conversation_id UUID NULL;
            """
        )
    )
    await db.execute(
        text(
            """
            ALTER TABLE stylist_chat_messages
            ADD COLUMN IF NOT EXISTS sender_user_id UUID NULL;
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS live_stylist_conversation_events (
                id UUID PRIMARY KEY,
                conversation_id UUID NOT NULL REFERENCES live_stylist_conversations(id),
                actor_user_id UUID NULL REFERENCES users(id),
                event_type VARCHAR(64) NOT NULL,
                payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
    )
    statements = [
        """
        CREATE INDEX IF NOT EXISTS ix_live_stylist_conversations_customer_user_id
        ON live_stylist_conversations (customer_user_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_live_stylist_conversations_assigned_stylist_user_id
        ON live_stylist_conversations (assigned_stylist_user_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_live_stylist_conversations_status
        ON live_stylist_conversations (status);
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_live_stylist_conversations_priority
        ON live_stylist_conversations (priority);
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_live_stylist_conversations_result_purchase_status
        ON live_stylist_conversations (result_purchase_status);
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_live_stylist_customer_status
        ON live_stylist_conversations (customer_user_id, status);
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_live_stylist_assigned_status
        ON live_stylist_conversations (assigned_stylist_user_id, status);
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_live_stylist_last_message
        ON live_stylist_conversations (last_message_at, created_at);
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_stylist_chat_messages_conversation_id
        ON stylist_chat_messages (conversation_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_stylist_chat_messages_sender_user_id
        ON stylist_chat_messages (sender_user_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_stylist_chat_conversation_created
        ON stylist_chat_messages (conversation_id, created_at);
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_live_stylist_conversation_events_conversation_id
        ON live_stylist_conversation_events (conversation_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_live_stylist_conversation_events_actor_user_id
        ON live_stylist_conversation_events (actor_user_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_live_stylist_conversation_events_event_type
        ON live_stylist_conversation_events (event_type);
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_live_stylist_conversation_events_created_at
        ON live_stylist_conversation_events (created_at);
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_live_stylist_event_conversation_created
        ON live_stylist_conversation_events (conversation_id, created_at);
        """,
    ]
    for statement in statements:
        await db.execute(text(statement))
    await db.commit()


def make_event_payload(**kwargs: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in kwargs.items():
        if value is None:
            continue
        if isinstance(value, UUID):
            payload[key] = str(value)
        elif isinstance(value, list):
            payload[key] = [str(item) if isinstance(item, UUID) else item for item in value]
        else:
            payload[key] = value
    return payload


async def log_live_stylist_event(
    db: AsyncSession,
    conversation_id: UUID,
    event_type: str,
    actor_user_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> LiveStylistConversationEvent:
    event = LiveStylistConversationEvent(
        conversation_id=conversation_id,
        actor_user_id=actor_user_id,
        event_type=str(event_type or "").strip() or "updated",
        payload=payload or {},
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(event)
    await db.flush()
    return event


async def get_or_create_open_conversation(
    db: AsyncSession,
    customer_user_id: UUID,
    source: str | None = None,
    scenario: str | None = None,
    working_hours_status: str | None = None,
    meta: dict[str, Any] | None = None,
) -> LiveStylistConversation:
    result = await db.execute(
        select(LiveStylistConversation)
        .where(
            LiveStylistConversation.customer_user_id == customer_user_id,
            LiveStylistConversation.status != "completed",
        )
        .order_by(
            LiveStylistConversation.last_message_at.desc().nullslast(),
            LiveStylistConversation.created_at.desc(),
        )
        .limit(1)
    )
    conversation = result.scalar_one_or_none()
    if conversation is not None:
        if source and not conversation.source:
            conversation.source = source
        if scenario and not conversation.scenario:
            conversation.scenario = scenario
        if working_hours_status and not conversation.initial_working_hours_status:
            conversation.initial_working_hours_status = working_hours_status
        if meta:
            current_meta = conversation.meta if isinstance(conversation.meta, dict) else {}
            conversation.meta = {**current_meta, **meta}
        return conversation

    now = datetime.now(timezone.utc)
    conversation = LiveStylistConversation(
        customer_user_id=customer_user_id,
        source=(source or "").strip() or None,
        scenario=(scenario or "").strip() or "live_stylist",
        status="requested",
        priority="normal",
        initial_working_hours_status=(working_hours_status or "").strip() or None,
        unread_for_stylist_count=0,
        unread_for_customer_count=0,
        meta=meta or {},
        created_at=now,
        updated_at=now,
    )
    db.add(conversation)
    await db.flush()
    await log_live_stylist_event(
        db=db,
        conversation_id=conversation.id,
        actor_user_id=customer_user_id,
        event_type="conversation_created",
        payload=make_event_payload(
            source=conversation.source,
            scenario=conversation.scenario,
            working_hours_status=conversation.initial_working_hours_status,
        ),
        created_at=now,
    )
    return conversation
