"""
Реакции покупателей на образы в Instagram-like ленте.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.database.connection import Base


class LookReaction(Base):
    __tablename__ = "look_reactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    look_id = Column(UUID(as_uuid=True), ForeignKey("looks.id"), nullable=False, index=True)
    reaction_type = Column(String(50), nullable=False, default="like")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
    look = relationship("Look")

    __table_args__ = (
        UniqueConstraint("user_id", "look_id", "reaction_type", name="uq_look_reactions_user_look_type"),
        Index("ix_look_reactions_look_type", "look_id", "reaction_type"),
    )
