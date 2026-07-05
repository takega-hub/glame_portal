from sqlalchemy import Column, String, DateTime, Boolean, Integer, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database.connection import Base


class AppHomeSlide(Base):
    __tablename__ = "app_home_slides"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    block_key = Column(String(64), nullable=False, default="style_inside")
    title = Column(String(255), nullable=True)
    subtitle = Column(Text, nullable=True)
    background_image_url = Column(String(500), nullable=True)
    image_url = Column(String(500), nullable=False)
    image_action_link = Column(String(500), nullable=True)
    image_action_type = Column(String(32), nullable=True)
    image_action_payload = Column(JSON, nullable=True)
    primary_button_text = Column(String(120), nullable=True)
    primary_button_link = Column(String(500), nullable=True)
    primary_button_action_type = Column(String(32), nullable=True)
    primary_button_action_payload = Column(JSON, nullable=True)
    secondary_button_text = Column(String(120), nullable=True)
    secondary_button_link = Column(String(500), nullable=True)
    secondary_button_action_type = Column(String(32), nullable=True)
    secondary_button_action_payload = Column(JSON, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    updated_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
