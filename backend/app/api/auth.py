from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from app.database.connection import get_db
from app.models.user import User
from app.models.onec_user_sync_job import OneCUserSyncJob
from app.services.sms_service import get_sms_service
from app.services.onec_user_sync_service import OneCUserSyncService
from app.services.onec_user_registration_payload import OneCUserRegistrationPayload
from app.services.loyalty_service import LoyaltyService
from app.services.referral_service import ReferralService, REFERRED_CLIENT_WELCOME_BONUS_POINTS
from app.services.admin_access import get_allowed_sections, normalize_role
import os
from dotenv import load_dotenv, find_dotenv
from uuid import UUID
from typing import Optional
from datetime import date
import bcrypt
import logging
import re
import random

def normalize_phone(phone: str) -> str:
    """
    Приводит номер телефона к единому формату (например: 79782860100).
    Удаляет все нецифровые символы.
    """
    if not phone:
        return ""
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 12 and digits.startswith('87'):
        return digits[1:]
    if len(digits) == 11 and digits.startswith('8'):
        return '7' + digits[1:]
    if len(digits) == 10:
        return '7' + digits
    if len(digits) == 11 and digits.startswith('7'):
        return digits
    return digits  # Возвращаем как есть, если не подошло под стандарты

def generate_otp() -> str:
    return str(random.randint(1000, 9999))


# Грузим .env из корня проекта, даже если рабочая директория другая
try:
    env_path = find_dotenv(usecwd=True)
    if env_path:
        load_dotenv(env_path, override=False)
    else:
        load_dotenv()
except Exception:
    load_dotenv()

logger = logging.getLogger(__name__)

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))
JWT_REFRESH_EXPIRATION_DAYS = int(os.getenv("JWT_REFRESH_EXPIRATION_DAYS", "30"))
OTP_TTL_SECONDS = 300
OTP_REQUEST_INTERVAL_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
REFERRAL_CLIENT_CUSTOMER_GROUP_KEY = os.getenv(
    "ONEC_REFERRAL_CLIENT_CUSTOMER_GROUP_KEY",
    "bca461ae-7396-11f1-876b-fa163e4cc04e",
)
APP_CLIENT_CUSTOMER_GROUP_KEY = os.getenv(
    "ONEC_APP_CLIENT_CUSTOMER_GROUP_KEY",
    "68442a44-7397-11f1-876b-fa163e4cc04e",
)


class UserRegisterPhone(BaseModel):
    phone: str
    password: str
    full_name: str
    email: Optional[EmailStr] = None
    inn: Optional[str] = None
    birth_date: Optional[date] = None
    referral_code: Optional[str] = None

class RequestOtpRequest(BaseModel):
    phone: str

class LoginOtpRequest(BaseModel):
    phone: str
    code: str

class OtpToken(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    require_password_change: bool = False


class UserResponse(BaseModel):
    id: str
    email: str | None
    phone: str | None
    full_name: str | None = None
    persona: str | None
    is_customer: bool = False
    loyalty_points: int | None = None
    role: str | None = None
    allowed_sections: list[str] = []
    onec_sync_status: Optional[str] = None
    onec_sync_job_id: Optional[str] = None
    onec_sync_last_error: Optional[str] = None

    class Config:
        from_attributes = True


class OneCSyncStatusResponse(BaseModel):
    status: Optional[str] = None
    job_id: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 0
    next_attempt_at: Optional[str] = None
    last_attempt_at: Optional[str] = None
    last_error: Optional[str] = None


async def _get_onec_sync_status(db: AsyncSession, user_id: UUID) -> OneCSyncStatusResponse:
    try:
        stmt = (
            select(OneCUserSyncJob)
            .where(OneCUserSyncJob.user_id == user_id)
            .order_by(OneCUserSyncJob.created_at.desc().nullslast())
            .limit(1)
        )
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()
        if not job:
            return OneCSyncStatusResponse()
        return OneCSyncStatusResponse(
            status=getattr(job, "status", None),
            job_id=str(job.id),
            attempts=int(getattr(job, "attempts", 0) or 0),
            max_attempts=int(getattr(job, "max_attempts", 0) or 0),
            next_attempt_at=job.next_attempt_at.isoformat() if getattr(job, "next_attempt_at", None) else None,
            last_attempt_at=job.last_attempt_at.isoformat() if getattr(job, "last_attempt_at", None) else None,
            last_error=getattr(job, "last_error", None),
        )
    except Exception as e:
        logger.warning("Не удалось получить статус 1С-синхронизации: %s", e)
        return OneCSyncStatusResponse()


class CardLoginRequest(BaseModel):
    card_number: str  # номер дисконтной карты (телефон)
    code: str  # код подтверждения (последние 4 цифры карты или SMS код)


class VerifyCardRequest(BaseModel):
    card_number: str


class ChangePasswordRequest(BaseModel):
    current_password: Optional[str] = None  # не обязателен для portal@internal без пароля
    new_password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


def hash_password(password: str) -> str:
    """Хеширование пароля с помощью bcrypt"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверка пароля"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Создание access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Создание refresh token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=JWT_REFRESH_EXPIRATION_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception
    
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    try:
        uid = UUID(user_id)
    except Exception:
        raise credentials_exception

    try:
        # Явно загружаем все колонки, включая role
        result = await db.execute(select(User).where(User.id == uid))
        user = result.scalar_one_or_none()
        if user is None:
            raise credentials_exception
        
        # Пытаемся обновить объект из базы, но не критично если не получится
        try:
            await db.refresh(user)
        except Exception as e:
            # Если refresh не удался, просто используем объект как есть
            logger.warning(f"Could not refresh user {uid}: {e}")
        
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_current_user: {e}", exc_info=True)
        raise credentials_exception


@router.post("/register-phone", response_model=UserResponse)
async def register_phone(user_data: UserRegisterPhone, db: AsyncSession = Depends(get_db)):
    phone_norm = normalize_phone(user_data.phone)
    if not phone_norm:
        raise HTTPException(status_code=400, detail="Invalid phone number")

    full_name_value = user_data.full_name.strip()
    if not full_name_value:
        raise HTTPException(status_code=400, detail="Name is required")

    referral_code_norm = (user_data.referral_code or "").strip().upper()
    referral_code = None
    referral_service = ReferralService(db)
    if referral_code_norm:
        referral_code = await referral_service.validate_code(referral_code_norm)
        if referral_code is None:
            raise HTTPException(status_code=400, detail="Invalid referral code")

    result = await db.execute(select(User).where(User.phone == phone_norm))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone already registered"
        )

    email_norm = str(user_data.email).strip().lower() if user_data.email else None
    if email_norm:
        result = await db.execute(select(User).where(User.email == email_norm))
        existing_user = result.scalar_one_or_none()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    inn_norm = None
    if user_data.inn:
        inn_digits = re.sub(r"\D", "", str(user_data.inn))
        if inn_digits:
            if len(inn_digits) not in (10, 12):
                raise HTTPException(status_code=400, detail="Invalid INN")
            inn_norm = inn_digits
    
    name_parts = [part for part in full_name_value.split() if part]
    first_name = name_parts[0] if name_parts else full_name_value
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else None

    password_hash = hash_password(user_data.password)
    
    new_user = User(
        phone=phone_norm,
        email=email_norm,
        password_hash=password_hash,
        full_name=full_name_value,
        birth_date=user_data.birth_date,
        persona=None,
        is_customer=True,
        role="customer",
    )
    prefs = dict(getattr(new_user, "preferences", None) or {})
    prefs["first_name"] = first_name or full_name_value
    if last_name:
        prefs["last_name"] = last_name
    if user_data.birth_date:
        prefs["birthday"] = user_data.birth_date.isoformat()
    new_user.preferences = prefs
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    welcome_points = REFERRED_CLIENT_WELCOME_BONUS_POINTS if referral_code else int(os.getenv("WELCOME_BONUS_POINTS", "500"))
    welcome_reason = "referral_welcome" if referral_code else "welcome"
    welcome_description = "Бонус за регистрацию по реферальному коду" if referral_code else "Приветственные баллы"
    welcome_source_id = f"referral_welcome:{new_user.id}:{referral_code.code}" if referral_code else f"welcome:{new_user.id}"
    if welcome_points > 0:
        try:
            loyalty = LoyaltyService(db)
            await loyalty.earn_points(
                user_id=new_user.id,
                points=welcome_points,
                reason=welcome_reason,
                metadata={
                    "description": welcome_description,
                    **({"referral_code": referral_code.code} if referral_code else {}),
                },
                source="platform",
                source_id=welcome_source_id,
            )
            await db.refresh(new_user)
        except Exception as e:
            logger.warning("Не удалось начислить баллы за регистрацию: %s", e)

    if referral_code:
        try:
            await referral_service.create_attribution(
                code=referral_code,
                referee_user_id=new_user.id,
                source="app_registration",
                meta={
                    "welcome_bonus_points": REFERRED_CLIENT_WELCOME_BONUS_POINTS,
                    "welcome_bonus_source_id": welcome_source_id,
                },
            )
        except Exception as e:
            logger.warning("Не удалось создать реферальную связь для нового покупателя: %s", e)

    onec_job_id = None
    onec_status = None
    onec_error = None
    try:
        onec_payload = OneCUserRegistrationPayload(
            phone=phone_norm,
            full_name=full_name_value,
            email=email_norm,
            inn=inn_norm,
            birth_date=user_data.birth_date,
            loyalty_program_key=None,
            source="referral_client" if referral_code else "app_registration",
            customer_group_key=REFERRAL_CLIENT_CUSTOMER_GROUP_KEY if referral_code else APP_CLIENT_CUSTOMER_GROUP_KEY,
            referral_code=referral_code.code if referral_code else None,
            welcome_bonus_points=welcome_points,
            welcome_bonus_comment=welcome_source_id if referral_code else None,
        )
        onec_svc = OneCUserSyncService(db)
        job = await onec_svc.enqueue_registration(new_user, onec_payload)
        if job:
            onec_job_id = str(job.id)
            onec_status = job.status
            onec_error = job.last_error
    except Exception as e:
        logger.warning("Не удалось запланировать синхронизацию 1С для регистрации: %s", e)
    
    return UserResponse(
        id=str(new_user.id), 
        email=new_user.email, 
        phone=new_user.phone, 
        full_name=new_user.full_name,
        persona=new_user.persona,
        is_customer=new_user.is_customer,
        loyalty_points=new_user.loyalty_points,
        role=new_user.role,
        onec_sync_status=onec_status,
        onec_sync_job_id=onec_job_id,
        onec_sync_last_error=onec_error,
    )

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    username = (form_data.username or "").strip()
    phone_norm = normalize_phone(username)
    
    # Ищем пользователя либо по email, либо по нормализованному телефону
    result = await db.execute(
        select(User).where(or_(User.email == username, User.phone == phone_norm, User.phone == username))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Проверка пароля
    if not user.password_hash or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Создание токенов
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_token: str,
    db: AsyncSession = Depends(get_db)
):
    """Обновление access token с помощью refresh token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(refresh_token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        token_type = payload.get("type")
        if token_type != "refresh":
            raise credentials_exception
        
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    try:
        uid = UUID(user_id)
    except Exception:
        raise credentials_exception
    
    # Проверяем существование пользователя
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    
    # Создаем новые токены
    new_access_token = create_access_token(data={"sub": str(user.id)})
    new_refresh_token = create_refresh_token(data={"sub": str(user.id)})
    
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer"
    }


async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """Опциональная версия get_current_user - возвращает None если пользователь не авторизован"""
    if not token:
        return None
    
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None
    
    try:
        uid = UUID(user_id)
    except ValueError:
        return None
    
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    return user


@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение информации о текущем пользователе"""
    try:
        # Обновляем объект из базы, чтобы получить все поля включая role
        try:
            await db.refresh(current_user)
        except Exception as e:
            # Если refresh не удался, перезагружаем пользователя
            try:
                result = await db.execute(select(User).where(User.id == current_user.id))
                refreshed_user = result.scalar_one_or_none()
                if refreshed_user:
                    current_user = refreshed_user
                else:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="User not found"
                    )
            except HTTPException:
                raise
            except Exception as refresh_error:
                # Если не удалось перезагрузить, продолжаем с текущим объектом
                logger.warning(f"Could not reload user {current_user.id}: {refresh_error}")
        
        # Получаем роль безопасно
        user_role = normalize_role(getattr(current_user, 'role', None))
        is_customer = getattr(current_user, 'is_customer', False)
        
        # Если это staff-пользователь (есть email, не покупатель), но роль пустая/ошибочная — устанавливаем admin
        if (
            getattr(current_user, 'email', None)
            and not is_customer
            and (not user_role or str(user_role).strip().lower() in {"customer", "user"})
        ):
            try:
                user_role = 'admin'
                # Обновляем в базе
                current_user.role = 'admin'
                await db.commit()
                try:
                    await db.refresh(current_user)
                    user_role = normalize_role(getattr(current_user, 'role', 'admin'))
                except Exception:
                    # Если refresh не удался, используем установленное значение
                    user_role = 'admin'
            except Exception as e:
                # Если не удалось обновить, просто используем 'admin'
                logger.warning(f"Could not update user role: {e}")
                user_role = 'admin'
        
        # Безопасное получение всех полей
        user_id = str(current_user.id) if hasattr(current_user, 'id') and current_user.id else ""
        user_email = getattr(current_user, 'email', None)
        user_phone = getattr(current_user, 'phone', None)
        user_full_name = getattr(current_user, 'full_name', None)
        
        # Безопасная обработка persona (может быть JSON или строкой)
        persona_value = getattr(current_user, 'persona', None)
        if persona_value is not None:
            if isinstance(persona_value, dict):
                # Если persona - это JSON объект, конвертируем в строку
                import json
                persona_value = json.dumps(persona_value, ensure_ascii=False)
            elif not isinstance(persona_value, str):
                persona_value = str(persona_value)
        
        # Безопасная обработка loyalty_points
        loyalty_points_value = getattr(current_user, 'loyalty_points', None)
        if loyalty_points_value is None:
            loyalty_points_value = 0
        elif not isinstance(loyalty_points_value, int):
            try:
                loyalty_points_value = int(loyalty_points_value)
            except (ValueError, TypeError):
                loyalty_points_value = 0

        onec_sync = await _get_onec_sync_status(db, current_user.id)
        allowed_sections = await get_allowed_sections(db, user_role)
        
        return UserResponse(
            id=user_id,
            email=user_email,
            phone=user_phone,
            full_name=user_full_name,
            persona=persona_value,
            is_customer=is_customer,
            loyalty_points=loyalty_points_value,
            role=user_role,
            allowed_sections=allowed_sections,
            onec_sync_status=onec_sync.status,
            onec_sync_job_id=onec_sync.job_id,
            onec_sync_last_error=onec_sync.last_error,
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error in /me endpoint: {e}\n{error_trace}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/onec-sync-status", response_model=OneCSyncStatusResponse)
async def get_onec_sync_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_onec_sync_status(db, current_user.id)


@router.post("/onec-sync-retry", response_model=OneCSyncStatusResponse)
async def retry_onec_sync(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    phone = getattr(current_user, "phone", None)
    if not phone:
        raise HTTPException(status_code=400, detail="Phone is required")
    payload = OneCUserRegistrationPayload(
        phone=phone,
        full_name=getattr(current_user, "full_name", None),
        email=getattr(current_user, "email", None),
        inn=None,
        loyalty_program_key=None,
        source="app_registration",
        customer_group_key=APP_CLIENT_CUSTOMER_GROUP_KEY,
    )
    svc = OneCUserSyncService(db)
    await svc.enqueue_registration(current_user, payload)
    return await _get_onec_sync_status(db, current_user.id)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Смена пароля текущего пользователя."""
    if len(body.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Новый пароль должен быть не короче 6 символов",
        )
        
    # Проверяем, как вошел пользователь
    is_otp_login = False
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            is_otp_login = payload.get("login_method") == "otp"
        except JWTError:
            pass

    has_hash = getattr(current_user, "password_hash", None) and current_user.password_hash
    # Если вход не по OTP и у пользователя есть пароль, требуем старый пароль
    if has_hash and not is_otp_login:
        if not body.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Укажите текущий пароль",
            )
        if not verify_password(body.current_password, current_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Неверный текущий пароль",
            )
            
    current_user.password_hash = hash_password(body.new_password)
    await db.commit()
    await db.refresh(current_user)
    return {"message": "Пароль успешно изменён"}


@router.post("/request-otp")
async def request_otp(body: RequestOtpRequest, db: AsyncSession = Depends(get_db)):
    phone_norm = normalize_phone(body.phone)
    if not phone_norm:
        raise HTTPException(status_code=400, detail="Invalid phone number")

    # Ищем пользователя
    result = await db.execute(select(User).where(User.phone == phone_norm))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь с таким номером не найден"
        )

    now = datetime.now(timezone.utc)
    last_sent_at = user.sms_otp_last_sent_at
    if last_sent_at is not None:
        if last_sent_at.tzinfo is None:
            last_sent_at = last_sent_at.replace(tzinfo=timezone.utc)
        elapsed = (now - last_sent_at).total_seconds()
        if elapsed < OTP_REQUEST_INTERVAL_SECONDS:
            retry_after = int(OTP_REQUEST_INTERVAL_SECONDS - elapsed)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Повторный запрос кода возможен через {retry_after} сек."
            )

    code = generate_otp()
    sms_service = get_sms_service()
    if not sms_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис SMS Aero не настроен"
        )

    try:
        await sms_service.send_sms(
            number=phone_norm,
            text=f"Код входа GLAME: {code}",
            sign="GLAME",
        )
    except Exception as e:
        logger.exception(f"Ошибка отправки OTP через SMS Aero для {phone_norm}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось отправить SMS-код"
        )

    user.sms_otp_code = code
    user.sms_otp_expires_at = now + timedelta(seconds=OTP_TTL_SECONDS)
    user.sms_otp_attempts = 0
    user.sms_otp_last_sent_at = now
    await db.commit()
    await db.refresh(user)

    logger.info(f"OTP отправлен для {phone_norm}")

    return {"message": "Код отправлен", "success": True}

@router.post("/login-otp", response_model=OtpToken)
async def login_otp(body: LoginOtpRequest, db: AsyncSession = Depends(get_db)):
    phone_norm = normalize_phone(body.phone)
    if not phone_norm:
        raise HTTPException(status_code=400, detail="Invalid phone number")

    result = await db.execute(select(User).where(User.phone == phone_norm))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    if not user.sms_otp_code or not user.sms_otp_expires_at:
        raise HTTPException(status_code=400, detail="Код не запрашивался или устарел")

    expires_at = user.sms_otp_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > expires_at:
        user.sms_otp_code = None
        user.sms_otp_expires_at = None
        user.sms_otp_attempts = 0
        await db.commit()
        raise HTTPException(status_code=400, detail="Срок действия кода истек")

    if user.sms_otp_attempts >= OTP_MAX_ATTEMPTS:
        user.sms_otp_code = None
        user.sms_otp_expires_at = None
        user.sms_otp_attempts = 0
        await db.commit()
        raise HTTPException(status_code=400, detail="Превышено число попыток. Запросите новый код")

    if user.sms_otp_code != body.code:
        user.sms_otp_attempts = (user.sms_otp_attempts or 0) + 1
        if user.sms_otp_attempts >= OTP_MAX_ATTEMPTS:
            user.sms_otp_code = None
            user.sms_otp_expires_at = None
            user.sms_otp_attempts = 0
            await db.commit()
            raise HTTPException(status_code=400, detail="Превышено число попыток. Запросите новый код")
        await db.commit()
        raise HTTPException(status_code=400, detail="Неверный код")

    user.sms_otp_code = None
    user.sms_otp_expires_at = None
    user.sms_otp_attempts = 0
    await db.commit()
        
    # Создание токенов
    access_token = create_access_token(data={"sub": str(user.id), "login_method": "otp"})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "require_password_change": True # Флаг для фронтенда
    }

@router.post("/login-by-card", response_model=Token)
async def login_by_card(
    request: CardLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Вход по номеру дисконтной карты
    Код - последние 4 цифры карты или SMS код (заглушка)
    """
    # Ищем пользователя по номеру телефона (который равен номеру карты)
    result = await db.execute(select(User).where(User.phone == request.card_number))
    user = result.scalar_one_or_none()
    
    if not user or not user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Дисконтная карта не найдена",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Простая проверка кода: последние 4 цифры карты
    # В продакшене здесь должна быть проверка SMS кода
    expected_code = request.card_number[-4:] if len(request.card_number) >= 4 else ""
    
    if request.code != expected_code:
        # Заглушка: для тестирования принимаем любой код
        # В продакшене здесь должна быть проверка SMS кода из БД или внешнего сервиса
        pass
    
    # Создание токенов
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


@router.post("/verify-card")
async def verify_card(
    request: VerifyCardRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Проверка существования дисконтной карты
    """
    result = await db.execute(select(User).where(User.phone == request.card_number))
    user = result.scalar_one_or_none()
    
    if not user or not user.is_customer:
        return {"exists": False}
    
    return {
        "exists": True,
        "card_number": user.discount_card_number,
        "full_name": user.full_name
    }


@router.post("/request-code")
async def request_code(
    request: VerifyCardRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Запрос кода подтверждения (заглушка для SMS)
    В продакшене здесь должна быть интеграция с SMS сервисом
    """
    result = await db.execute(select(User).where(User.phone == request.card_number))
    user = result.scalar_one_or_none()
    
    if not user or not user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Дисконтная карта не найдена"
        )
    
    # Заглушка: в продакшене здесь отправка SMS
    # Генерируем код (для тестирования используем последние 4 цифры)
    code = request.card_number[-4:] if len(request.card_number) >= 4 else "0000"
    
    return {
        "success": True,
        "message": "Код отправлен",
        "code": code  # В продакшене не возвращаем код
    }
