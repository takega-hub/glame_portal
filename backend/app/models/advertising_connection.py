import uuid
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database.connection import Base


class AdvertisingConnection(Base):
    __tablename__ = "advertising_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform = Column(String(64), nullable=False, index=True)  # yandex_direct / yandex_business / yandex_maps
    name = Column(String(255), nullable=False)
    account_login = Column(String(255), nullable=True)
    client_login = Column(String(255), nullable=True)
    organization_name = Column(String(255), nullable=True)
    status = Column(String(64), nullable=False, default="draft", index=True)
    auth_mode = Column(String(32), nullable=False, default="oauth")
    secret_ref = Column(String(255), nullable=True)  # reference only; never the token itself
    permissions = Column(JSON, nullable=False, default=dict)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_status = Column(String(64), nullable=True)
    last_sync_summary = Column(JSON, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
