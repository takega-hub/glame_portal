"""
Dependency functions для проверки ролей
"""
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.auth import get_current_user
from app.models.user import User
from app.database.connection import get_db


def require_role(role: str):
    """Dependency для проверки роли"""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Требуется роль {role}"
            )
        return current_user
    return role_checker


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
            user_role = getattr(current_user, 'role', None)
            
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
    async def marketer_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in ["admin", "ai_marketer"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Требуется роль администратора или AI маркетолога"
            )
        return current_user
    return marketer_checker
