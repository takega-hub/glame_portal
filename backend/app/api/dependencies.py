"""
Dependency functions для проверки ролей
"""
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.auth import get_current_user
from app.models.user import User
from app.database.connection import get_db
from app.services.admin_access import normalize_role


async def _ensure_staff_role(current_user: User, db: AsyncSession) -> str | None:
    try:
        try:
            await db.refresh(current_user)
        except Exception:
            pass

        user_role = normalize_role(getattr(current_user, "role", None))
        is_customer = bool(getattr(current_user, "is_customer", False))
        email = getattr(current_user, "email", None)

        if is_customer:
            return user_role

        if email and (not user_role or str(user_role).strip().lower() in {"customer", "user"}):
            current_user.role = "admin"
            try:
                await db.commit()
                await db.refresh(current_user)
            except Exception:
                pass
            return "admin"

        return user_role
    except Exception:
        return normalize_role(getattr(current_user, "role", None))


def require_role(role: str):
    """Dependency для проверки роли"""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if normalize_role(current_user.role) != normalize_role(role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Требуется роль {role}"
            )
        return current_user
    return role_checker


def require_any_role(roles: list[str]):
    async def roles_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        effective_role = await _ensure_staff_role(current_user, db)
        normalized_roles = [normalize_role(role) for role in roles]
        if effective_role not in normalized_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Требуется одна из ролей: {', '.join(roles)}",
            )
        return current_user

    return roles_checker


def require_customer():
    """Dependency для проверки, что пользователь - покупатель"""
    async def customer_checker(current_user: User = Depends(get_current_user)) -> User:
        if not current_user.is_customer:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Доступно только для покупателей"
            )
        return current_user
    return customer_checker


def require_admin():
    """Dependency для проверки, что пользователь - администратор"""
    async def admin_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        try:
            # Обновляем объект из базы, чтобы получить все поля
            try:
                await db.refresh(current_user)
            except Exception as refresh_error:
                # Если не удалось обновить, продолжаем с текущими данными
                pass
            
            # Безопасный доступ к роли
            user_role = normalize_role(getattr(current_user, 'role', None))
            
            # Если роль не установлена, но пользователь имеет email (не покупатель), устанавливаем admin
            if not user_role and current_user.email and not getattr(current_user, 'is_customer', False):
                try:
                    user_role = 'admin'
                    current_user.role = 'admin'
                    await db.commit()
                    await db.refresh(current_user)
                    user_role = 'admin'
                except Exception as commit_error:
                    # Если не удалось сохранить роль, продолжаем с текущей
                    pass
            
            if user_role != "admin":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Требуется роль администратора"
                )
            return current_user
        except HTTPException:
            # Пробрасываем HTTP исключения
            raise
        except Exception as e:
            # Логируем другие ошибки и пробрасываем как HTTP 500
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка в require_admin: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ошибка проверки прав доступа"
            )
    return admin_checker


def require_marketer():
    """Dependency для проверки, что пользователь - администратор или маркетолог"""
    async def marketer_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        effective_role = await _ensure_staff_role(current_user, db)
        if effective_role not in ["admin", "marketer"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Требуется роль администратора или маркетолога"
            )
        return current_user
    return marketer_checker


def require_content_manager():
    async def content_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        effective_role = await _ensure_staff_role(current_user, db)
        if effective_role not in ["admin", "manager"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Требуется роль администратора или управляющего",
            )
        return current_user

    return content_checker
