from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import hash_password
from app.api.dependencies import require_admin
from app.database.connection import get_db
from app.models.admin_access import AdminRoleAccess
from app.models.user import User
from app.services.admin_access import (
    ADMIN_SECTIONS,
    ROLE_LABELS,
    STAFF_ROLES,
    clean_section_ids,
    default_sections_for_role,
    ensure_default_role_access,
    normalize_role,
)
from app.services.user_deletion_service import UserDeletionService


router = APIRouter()


class AdminSectionResponse(BaseModel):
    id: str
    name: str
    href: str
    group: str


class RoleAccessResponse(BaseModel):
    role_key: str
    role_label: str
    section_ids: list[str]
    is_system: bool = True


class RoleAccessUpdate(BaseModel):
    section_ids: list[str] = Field(default_factory=list)


class StaffUserResponse(BaseModel):
    id: str
    email: str | None
    full_name: str | None = None
    role: str | None
    role_label: str | None = None
    is_customer: bool = False


class StaffCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str | None = None
    role: str


class StaffUpdateRequest(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=6)
    full_name: str | None = None
    role: str | None = None


def _role_or_400(role: str | None) -> str:
    normalized = normalize_role(role)
    if normalized not in STAFF_ROLES:
        raise HTTPException(status_code=400, detail="Неизвестная роль")
    return normalized


def _staff_response(user: User) -> StaffUserResponse:
    role = normalize_role(getattr(user, "role", None))
    return StaffUserResponse(
        id=str(user.id),
        email=getattr(user, "email", None),
        full_name=getattr(user, "full_name", None),
        role=role,
        role_label=ROLE_LABELS.get(role or ""),
        is_customer=bool(getattr(user, "is_customer", False)),
    )


@router.get("/sections", response_model=list[AdminSectionResponse])
async def list_sections(_current_user: User = Depends(require_admin())):
    return [
        AdminSectionResponse(id=section.id, name=section.name, href=section.href, group=section.group)
        for section in ADMIN_SECTIONS
    ]


@router.get("/roles", response_model=list[RoleAccessResponse])
async def list_roles(
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    await ensure_default_role_access(db)
    result = await db.execute(select(AdminRoleAccess).order_by(AdminRoleAccess.role_key))
    rows = {row.role_key: row for row in result.scalars().all()}
    ordered_roles = ["admin", "marketer", "manager", "seller"]
    return [
        RoleAccessResponse(
            role_key=role_key,
            role_label=rows.get(role_key).role_label if rows.get(role_key) else ROLE_LABELS[role_key],
            section_ids=clean_section_ids(
                rows.get(role_key).section_ids if rows.get(role_key) else default_sections_for_role(role_key)
            ),
            is_system=bool(rows.get(role_key).is_system) if rows.get(role_key) else True,
        )
        for role_key in ordered_roles
    ]


@router.put("/roles/{role_key}", response_model=RoleAccessResponse)
async def update_role_access(
    role_key: str,
    payload: RoleAccessUpdate,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    normalized = _role_or_400(role_key)
    section_ids = clean_section_ids(payload.section_ids)
    if normalized == "admin":
        section_ids = default_sections_for_role("admin")

    result = await db.execute(select(AdminRoleAccess).where(AdminRoleAccess.role_key == normalized))
    access = result.scalar_one_or_none()
    if access is None:
        access = AdminRoleAccess(
            role_key=normalized,
            role_label=ROLE_LABELS[normalized],
            section_ids=section_ids,
            is_system=True,
        )
        db.add(access)
    else:
        access.section_ids = section_ids
    await db.commit()
    await db.refresh(access)
    return RoleAccessResponse(
        role_key=access.role_key,
        role_label=access.role_label,
        section_ids=clean_section_ids(access.section_ids),
        is_system=bool(access.is_system),
    )


@router.get("/staff", response_model=list[StaffUserResponse])
async def list_staff(
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    roles = set(STAFF_ROLES) | {"ai_marketer", "content_manager"}
    result = await db.execute(
        select(User)
        .where(User.is_customer.is_(False))
        .where(or_(User.role.in_(roles), User.email.is_not(None)))
        .order_by(User.email.asc().nullslast())
    )
    return [_staff_response(user) for user in result.scalars().all()]


@router.post("/staff", response_model=StaffUserResponse, status_code=status.HTTP_201_CREATED)
async def create_staff(
    payload: StaffCreateRequest,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    role = _role_or_400(payload.role)
    email = str(payload.email).strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Пользователь с таким email уже существует")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=(payload.full_name or "").strip() or None,
        role=role,
        is_customer=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _staff_response(user)


@router.put("/staff/{user_id}", response_model=StaffUserResponse)
async def update_staff(
    user_id: UUID,
    payload: StaffUpdateRequest,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or bool(getattr(user, "is_customer", False)):
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    if payload.email is not None:
        email = str(payload.email).strip().lower()
        existing = await db.execute(select(User).where(User.email == email, User.id != user.id))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Пользователь с таким email уже существует")
        user.email = email
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip() or None
    if payload.role is not None:
        user.role = _role_or_400(payload.role)
    if payload.password:
        user.password_hash = hash_password(payload.password)

    user.is_customer = False
    await db.commit()
    await db.refresh(user)
    return _staff_response(user)


@router.delete("/staff/{user_id}")
async def delete_staff(
    user_id: UUID,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    if getattr(current_user, "id", None) == user_id:
        raise HTTPException(status_code=400, detail="Нельзя удалить текущего пользователя")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or bool(getattr(user, "is_customer", False)):
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    if getattr(user, "email", None) == "portal@internal":
        raise HTTPException(status_code=400, detail="Системного пользователя нельзя удалить")

    role = normalize_role(getattr(user, "role", None))
    if role == "admin":
        other_admins = await db.execute(
            select(User.id)
            .where(User.is_customer.is_(False))
            .where(User.role == "admin")
            .where(User.id != user_id)
            .limit(1)
        )
        if other_admins.scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail="Нельзя удалить последнего администратора")

    await UserDeletionService(db).delete_user_by_id(user_id)
    return {"status": "success"}
