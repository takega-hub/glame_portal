from sqlalchemy import Boolean, Column, DateTime, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database.connection import Base


class AdminRoleAccess(Base):
    __tablename__ = "admin_role_access"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_key = Column(String(50), unique=True, nullable=False, index=True)
    role_label = Column(String(100), nullable=False)
    section_ids = Column(JSON, nullable=False, default=list)
    is_system = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
