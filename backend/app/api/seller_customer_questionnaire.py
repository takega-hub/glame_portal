"""Kiosk questionnaire used by sales assistants to register a customer."""
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import normalize_phone
from app.api.dependencies import require_any_role
from app.database.connection import get_db
from app.models.user import User
from app.services.onec_outbound_service import OneCOutboundService
from app.services.onec_user_registration_payload import OneCUserRegistrationPayload
from app.services.onec_user_sync_service import OneCUserSyncService
from app.services.loyalty_service import LoyaltyService
from app.services.customer_questionnaire_service import (
    NO_MESSAGES,
    normalize_questionnaire,
    onec_questionnaire_fields,
    questionnaire_from_preferences,
)


router = APIRouter()


class BuyerQuestionnaire(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    birth_date: date | None = None
    phone: str
    city: str | None = Field(default=None, max_length=100)
    discovery_channels: list[str] = Field(default_factory=list)
    discovery_other: str | None = Field(default=None, max_length=255)
    purchase_for: list[str] = Field(default_factory=list)
    contact_channels: list[str] = Field(default_factory=list)
    glame_values: list[str] = Field(default_factory=list)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        normalized = normalize_phone(value)
        if len(normalized) != 11 or not normalized.startswith("7"):
            raise ValueError("Введите российский номер телефона")
        return normalized


class QuestionnaireSubmit(BuyerQuestionnaire):
    confirm_existing: bool = False


class QuestionnaireLookup(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        normalized = normalize_phone(value)
        if len(normalized) != 11 or not normalized.startswith("7"):
            raise ValueError("Введите российский номер телефона")
        return normalized


class QuestionnaireLastNameLookup(BaseModel):
    last_name: str = Field(max_length=100)

    @field_validator("last_name")
    @classmethod
    def validate_last_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("Введите не менее двух букв фамилии")
        return normalized


class QuestionnaireCustomerLookup(BaseModel):
    customer_id: UUID


def _customer_payload(form: BuyerQuestionnaire) -> OneCUserRegistrationPayload:
    return OneCUserRegistrationPayload(
        phone=form.phone,
        full_name=form.full_name.strip(),
        birth_date=form.birth_date,
        source="seller_questionnaire",
        # The questionnaire must not create a welcome bonus as a side effect.
        skip_welcome_bonus=True,
    )


def _one_c_update_payload(form: BuyerQuestionnaire, questionnaire: dict[str, Any]) -> dict[str, Any]:
    """Only use catalogue fields that are present in the standard GLAME 1C setup."""
    body: dict[str, Any] = {
        "Description": form.full_name.strip(),
        "НаименованиеПолное": form.full_name.strip(),
    }
    if form.birth_date:
        body["ДатаРождения"] = f"{form.birth_date.isoformat()}T00:00:00"
    # City is a GLAME platform field by default. A deployment that has a 1C city
    # requisition can opt in without changing the integration code.
    city_field = (os.getenv("ONEC_CUSTOMER_CITY_FIELD") or "").strip()
    if city_field and form.city:
        body[city_field] = form.city.strip()
    body.update(onec_questionnaire_fields(questionnaire))
    return body


async def _find_local_customer(db: AsyncSession, phone: str, customer_id_1c: str | None = None) -> User | None:
    result = await db.execute(select(User).where(User.phone == phone))
    user = result.scalar_one_or_none()
    if user or not customer_id_1c:
        return user
    result = await db.execute(select(User).where(User.customer_id_1c == customer_id_1c))
    return result.scalar_one_or_none()


async def _find_one_c_match(phone: str) -> tuple[dict[str, Any] | None, bool]:
    """Return the card and whether 1C was available for the lookup."""
    if not (os.getenv("ONEC_API_URL") or "").strip():
        return None, False
    async with OneCOutboundService() as onec:
        return await onec.find_discount_card_by_phone(phone), True


async def _refresh_loyalty_points_from_one_c(db: AsyncSession, user: User) -> bool:
    """Use 1C as the source of truth for bonus balance during questionnaire work."""
    previous_balance = int(user.loyalty_points or 0)
    sync_service = OneCUserSyncService(db)
    await sync_service._sync_loyalty_balance_from_1c(
        user,
        customer_id_1c=user.customer_id_1c,
        discount_card_id_1c=user.discount_card_id_1c,
    )
    if int(user.loyalty_points or 0) == previous_balance:
        return False
    user.synced_at = datetime.now(timezone.utc)
    return True


def _mask_phone(phone: str | None) -> str:
    """Keep enough digits to distinguish people with the same surname."""
    normalized = normalize_phone(phone or "")
    if len(normalized) != 11 or not normalized.startswith("7"):
        return "Номер не указан"
    return f"+7 {normalized[1:4]} *** **-{normalized[-2:]}"


async def _questionnaire_customer_response(db: AsyncSession, user: User) -> dict[str, Any]:
    if await _refresh_loyalty_points_from_one_c(db, user):
        await db.commit()
        await db.refresh(user)

    questionnaire = questionnaire_from_preferences(user.preferences) or {}
    level_progress = LoyaltyService(db).get_loyalty_level_progress(user.total_spent or 0)
    current_level = level_progress["current_level"]
    contact_channels = list(questionnaire.get("contact_channels") or [])
    if questionnaire.get("do_not_contact"):
        contact_channels.append(NO_MESSAGES)
    return {
        "found": True,
        "customer": {
            "full_name": user.full_name or questionnaire.get("full_name") or "",
            "birth_date": user.birth_date.isoformat() if user.birth_date else questionnaire.get("birth_date") or "",
            "phone": user.phone,
            "city": user.city or questionnaire.get("city") or "",
            "discovery_channels": questionnaire.get("discovery_channels") or [],
            "discovery_other": questionnaire.get("discovery_other") or "",
            "purchase_for": questionnaire.get("purchase_for") or [],
            "contact_channels": contact_channels,
            "glame_values": questionnaire.get("glame_values") or [],
        },
        "loyalty": {
            "level": current_level["name"],
            "bonus_percent": int(current_level["bonus_percent"]),
            "points": max(0, int(user.loyalty_points or 0)),
            "discount_card_number": user.discount_card_number,
        },
    }


@router.post("/lookup")
async def lookup_questionnaire_customer(
    request: QuestionnaireLookup,
    _current_user: User = Depends(require_any_role(["seller", "manager", "admin"])),
    db: AsyncSession = Depends(get_db),
):
    """Return the existing platform profile so a paper questionnaire can extend it."""
    user = await _find_local_customer(db, request.phone)
    if user is None:
        return {"found": False}

    return await _questionnaire_customer_response(db, user)


@router.post("/lookup-by-last-name")
async def lookup_questionnaire_customers_by_last_name(
    request: QuestionnaireLastNameLookup,
    _current_user: User = Depends(require_any_role(["seller", "manager", "admin"])),
    db: AsyncSession = Depends(get_db),
):
    """Find platform customer profiles by surname without guessing among namesakes."""
    escaped_last_name = (
        request.last_name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    statement = (
        select(User)
        .where(
            User.is_customer.is_(True),
            User.phone.is_not(None),
            User.full_name.ilike(f"{escaped_last_name}%", escape="\\"),
        )
        .order_by(User.full_name.asc(), User.updated_at.desc())
        .limit(15)
    )
    users = (await db.execute(statement)).scalars().all()
    return {
        "customers": [
            {
                "id": str(user.id),
                "full_name": user.full_name or "Без имени",
                "phone_masked": _mask_phone(user.phone),
                "city": user.city or "",
            }
            for user in users
        ]
    }


@router.post("/lookup-by-id")
async def lookup_questionnaire_customer_by_id(
    request: QuestionnaireCustomerLookup,
    _current_user: User = Depends(require_any_role(["seller", "manager", "admin"])),
    db: AsyncSession = Depends(get_db),
):
    """Load the selected customer profile from surname search."""
    result = await db.execute(
        select(User).where(User.id == request.customer_id, User.is_customer.is_(True))
    )
    user = result.scalar_one_or_none()
    if user is None:
        return {"found": False}
    return await _questionnaire_customer_response(db, user)


@router.post("/preview")
async def preview_questionnaire(
    form: BuyerQuestionnaire,
    _current_user: User = Depends(require_any_role(["seller", "manager", "admin"])),
    db: AsyncSession = Depends(get_db),
):
    """Check the phone before exposing the overwrite decision to the seller."""
    local_user = await _find_local_customer(db, form.phone)
    try:
        card, onec_checked = await _find_one_c_match(form.phone)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Не удалось проверить номер в 1С. Повторите попытку.") from exc

    existing = bool(local_user or card)
    return {
        "success": True,
        "requires_confirmation": existing,
        "existing_in": [
            *(["platform"] if local_user else []),
            *(["1c"] if card else []),
        ],
        "one_c_checked": onec_checked,
    }


@router.post("/submit")
async def submit_questionnaire(
    form: QuestionnaireSubmit,
    current_user: User = Depends(require_any_role(["seller", "manager", "admin"])),
    db: AsyncSession = Depends(get_db),
):
    """Create/update the platform customer and synchronously ensure their 1C card."""
    try:
        card, _onec_checked = await _find_one_c_match(form.phone)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Не удалось сохранить данные в 1С. Данные не изменены.") from exc

    customer_id_from_card = str((card or {}).get("ВладелецКарты_Key") or "") or None
    user = await _find_local_customer(db, form.phone, customer_id_from_card)
    exists = bool(user or card)
    if exists and not form.confirm_existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Номер уже есть в базе. Подтвердите сохранение новых данных.",
        )

    is_new = user is None
    if user is None:
        user = User(phone=form.phone, role="customer", is_customer=True)
        db.add(user)
        await db.flush()

    previous_questionnaire = questionnaire_from_preferences(user.preferences) or {}
    # An omitted date means "leave it untouched". This prevents an empty field
    # from becoming a system/default date during an edit of a paper questionnaire.
    birth_date_value = (
        form.birth_date.isoformat()
        if form.birth_date
        else previous_questionnaire.get("birth_date")
    )
    questionnaire_data = normalize_questionnaire({
        "full_name": form.full_name.strip(),
        "birth_date": birth_date_value,
        "city": form.city.strip() if form.city else None,
        "discovery_channels": form.discovery_channels,
        "discovery_other": form.discovery_other.strip() if form.discovery_other else None,
        "purchase_for": form.purchase_for,
        "contact_channels": form.contact_channels,
        "glame_values": form.glame_values,
        "personal_data_consent": True,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "submitted_by_user_id": str(current_user.id),
    })
    preferences = dict(user.preferences or {})
    preferences["buyer_questionnaire"] = questionnaire_data
    user.preferences = preferences
    user.phone = form.phone
    user.full_name = form.full_name.strip()
    if form.birth_date:
        user.birth_date = form.birth_date
    user.city = form.city.strip() if form.city else None
    user.is_customer = True
    user.role = user.role or "customer"

    # Do not commit the platform changes until 1C has accepted the customer/card.
    try:
        async with OneCOutboundService() as onec:
            sync_service = OneCUserSyncService(db)
            payload = _customer_payload(form)
            customer_id, card_id, _debug = await sync_service._ensure_customer_and_card(
                onec,
                payload,
                existing_card=card,
            )
            await onec.update_customer(customer_id, _one_c_update_payload(form, questionnaire_data))
            await sync_service._ensure_customer_phone_contact(
                onec, customer_id=customer_id, phone=form.phone, debug={"steps": []}
            )
            user.customer_id_1c = customer_id
            user.discount_card_id_1c = card_id
            user.discount_card_number = form.phone
            user.synced_at = datetime.now(timezone.utc)
            await _refresh_loyalty_points_from_one_c(db, user)
        await db.commit()
        await db.refresh(user)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Не удалось сохранить данные в 1С. Данные не изменены.") from exc

    return {
        "success": True,
        "customer_id": str(user.id),
        "created": is_new,
        "customer_id_1c": user.customer_id_1c,
        "discount_card_id_1c": user.discount_card_id_1c,
        "loyalty_points": user.loyalty_points,
        # These conditions are exactly those used by the customer cabinet,
        # CRM audience and the request picker immediately after this commit.
        "platform_ready": {
            "customer_profile": bool(user.is_customer),
            "request_picker": bool(user.is_customer and user.phone),
            "crm": bool(user.is_customer),
            "one_c": bool(user.customer_id_1c and user.discount_card_id_1c),
        },
    }
