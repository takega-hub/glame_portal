from sqlalchemy import Column, String, DateTime, Date, JSON, Integer, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=True, index=True)  # nullable для покупателей без email
    password_hash = Column(String(255), nullable=True)  # Хеш пароля (bcrypt)
    persona = Column(String(50), nullable=True)  # fashion_girl, status_woman, etc.
    # preferences структура:
    # {
    #   "color_type": str,  # цветотип (весна, лето, осень, зима)
    #   "preferred_styles": List[str],  # предпочитаемые стили
    #   "sizes": Dict[str, str],  # размеры (кольцо, браслет, etc.)
    #   "favorite_brands": List[str],  # любимые бренды
    #   "budget_range": Dict[str, int],  # {"min": int, "max": int} в копейках
    #   "forbidden_elements": List[str],  # запрещенные элементы (материалы, цвета, etc.)
    #   "occasion_preferences": Dict[str, List[str]]  # предпочтения по поводам
    # }
    preferences = Column(JSON, nullable=True, default=dict)
    
    # Поля для покупателей (синхронизация с 1С)
    phone = Column(String(20), unique=True, nullable=True, index=True)  # номер телефона = логин
    sms_otp_code = Column(String(4), nullable=True)
    sms_otp_expires_at = Column(DateTime(timezone=True), nullable=True)
    sms_otp_attempts = Column(Integer, default=0, nullable=False)
    sms_otp_last_sent_at = Column(DateTime(timezone=True), nullable=True)
    discount_card_number = Column(String(50), unique=True, nullable=True, index=True)  # номер дисконтной карты из 1С
    customer_id_1c = Column(String(255), nullable=True, index=True)  # ID контрагента в 1С
    discount_card_id_1c = Column(String(255), nullable=True)  # ID дисконтной карты в 1С
    full_name = Column(String(255), nullable=True)  # полное имя покупателя
    city = Column(String(100), nullable=True)  # город покупателя
    birth_date = Column(Date, nullable=True, index=True)  # дата рождения из 1С
    gender = Column(String(10), nullable=True)  # пол покупателя: "male", "female" или None
    role = Column(String(50), nullable=True, default="customer")  # customer, admin, ai_marketer, content_manager
    
    # Программа лояльности
    loyalty_points = Column(Integer, default=0, nullable=False)  # текущий баланс баллов
    
    # Метрики покупателя
    total_purchases = Column(Integer, default=0, nullable=False)  # количество покупок
    total_spent = Column(Integer, default=0, nullable=False)  # общая сумма покупок в копейках
    average_check = Column(Integer, nullable=True)  # средний чек в копейках
    last_purchase_date = Column(DateTime(timezone=True), nullable=True)  # дата последней покупки
    customer_segment = Column(String(50), nullable=True)  # сегмент покупателя (VIP, Active, Sleeping, New)
    rfm_score = Column(JSON, nullable=True)  # RFM оценки {recency, frequency, monetary, r_score, f_score, m_score}
    purchase_preferences = Column(JSON, nullable=True)  # предпочтения по категориям и брендам
    
    # Предпочитаемый магазин (вычисляется по истории продаж)
    preferred_store_external_id = Column(String(255), nullable=True)  # ID магазина из 1С
    preferred_store_name = Column(String(255), nullable=True)  # Название магазина
    preferred_store_share = Column(Integer, nullable=True)  # Доля покупок в этом магазине (0-100 или float 0-1)
    preferred_store_updated_at = Column(DateTime(timezone=True), nullable=True)
    
    # Второй предпочитаемый магазин
    secondary_store_name = Column(String(255), nullable=True)
    
    # Флаги
    is_customer = Column(Boolean, default=False, nullable=False)  # является ли покупателем (синхронизирован из 1С)
    synced_at = Column(DateTime(timezone=True), nullable=True)  # дата последней синхронизации с 1С
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Индексы
    __table_args__ = (
        Index('ix_users_phone', 'phone'),
        Index('ix_users_discount_card', 'discount_card_number'),
        Index('ix_users_customer_id_1c', 'customer_id_1c'),
        Index('ix_users_is_customer', 'is_customer'),
        Index('ix_users_role', 'role'),
        Index('ix_users_birth_date', 'birth_date'),
    )
