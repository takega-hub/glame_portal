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
    """Read a role from the database; authorization must never mutate it."""
    try:
        await db.refresh(current_user)
    except Exception:
        # get_current_user already fetched this record. A failed refresh must not
        # turn into a privilege grant.
        pass
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
        effective_role = await _ensure_staff_role(current_user, db)
        if effective_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Требуется роль администратора",
            )
        return current_user
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
