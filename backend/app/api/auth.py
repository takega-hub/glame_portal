from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from app.database.connection import get_db
from app.models.user import User
import os
from dotenv import load_dotenv
from uuid import UUID
from typing import Optional
import bcrypt
import logging

load_dotenv()

logger = logging.getLogger(__name__)

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))
JWT_REFRESH_EXPIRATION_DAYS = int(os.getenv("JWT_REFRESH_EXPIRATION_DAYS", "30"))


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str | None
    phone: str | None
    persona: str | None
    is_customer: bool = False
    loyalty_points: int | None = None
    role: str | None = None

    class Config:
        from_attributes = True


class CardLoginRequest(BaseModel):
    card_number: str  # номер дисконтной карты (телефон)
    code: str  # код подтверждения (последние 4 цифры карты или SMS код)


class VerifyCardRequest(BaseModel):
    card_number: str


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


PORTAL_BASIC_AUTH_ONLY = os.getenv("PORTAL_BASIC_AUTH_ONLY", "").lower() in ("1", "true", "yes")
PORTAL_INTERNAL_EMAIL = "portal@internal"

async def get_current_user(request: Request, token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Режим «только Basic Auth»: если nginx передал X-Remote-User после Basic Auth — считаем пользователя админом
    if PORTAL_BASIC_AUTH_ONLY:
        remote_user = request.headers.get("X-Remote-User")
        if remote_user:
            result = await db.execute(select(User).where(User.email == PORTAL_INTERNAL_EMAIL))
            user = result.scalar_one_or_none()
            if user is None:
                user = User(
                    email=PORTAL_INTERNAL_EMAIL,
                    role="admin",
                    is_customer=False,
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)
            return user

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


@router.post("/register", response_model=UserResponse)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    # Проверка существования пользователя
    result = await db.execute(select(User).where(User.email == user_data.email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Хеширование пароля
    password_hash = hash_password(user_data.password)
    
    # Создание пользователя
    new_user = User(
        email=user_data.email,
        password_hash=password_hash,
        persona=None
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    return UserResponse(id=str(new_user.id), email=new_user.email, persona=new_user.persona)


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    # Поиск пользователя
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Проверка пароля
    if not user.password_hash or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
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
        user_role = getattr(current_user, 'role', None)
        is_customer = getattr(current_user, 'is_customer', False)
        
        # Если роль не установлена, но пользователь имеет email (не покупатель), устанавливаем admin
        if not user_role and getattr(current_user, 'email', None) and not is_customer:
            try:
                user_role = 'admin'
                # Обновляем в базе
                current_user.role = 'admin'
                await db.commit()
                try:
                    await db.refresh(current_user)
                    user_role = getattr(current_user, 'role', 'admin')
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
        
        return UserResponse(
            id=user_id,
            email=user_email,
            phone=user_phone,
            persona=persona_value,
            is_customer=is_customer,
            loyalty_points=loyalty_points_value,
            role=user_role
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
