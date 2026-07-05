import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.database.connection import Base


class StylistChatMessage(Base):
    __tablename__ = "stylist_chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("live_stylist_conversations.id"), nullable=True, index=True)
    sender_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    role = Column(String(24), nullable=False, index=True)  # user | assistant | system
    text = Column(Text, nullable=True)
    attachments = Column(JSONB, nullable=False, default=list)
    payload = Column(JSONB, nullable=True, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_stylist_chat_user_created", "user_id", "created_at"),
        Index("ix_stylist_chat_conversation_created", "conversation_id", "created_at"),
    )
