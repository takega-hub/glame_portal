"""Canonical questionnaire profile shared by CRM, analytics and AI contexts."""
from __future__ import annotations

import json
import os
from typing import Any, Iterable


CONTACT_CHANNELS = ("Telegram", "WhatsApp", "Instagram", "SMS", "Звонок")
NO_MESSAGES = "Не хочу получать сообщения"


def _unique_strings(values: Iterable[Any] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        item = str(value or "").strip()
        if item and item not in result:
            result.append(item)
    return result


def normalize_questionnaire(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Keep an immutable questionnaire snapshot and derive contact policy from it."""
    source = dict(raw or {})
    selected_channels = _unique_strings(source.get("contact_channels"))
    do_not_contact = NO_MESSAGES in selected_channels
    allowed_channels = [] if do_not_contact else [item for item in selected_channels if item in CONTACT_CHANNELS]
    # The form permits several convenient channels; use the first one selected by
    # the customer as the CRM starting point and show all alternatives to staff.
    recommended_channel = allowed_channels[0] if allowed_channels else None

    return {
        "version": 1,
        "full_name": str(source.get("full_name") or "").strip() or None,
        "birth_date": source.get("birth_date"),
        "city": str(source.get("city") or "").strip() or None,
        "discovery_channels": _unique_strings(source.get("discovery_channels")),
        "discovery_other": str(source.get("discovery_other") or "").strip() or None,
        "purchase_for": _unique_strings(source.get("purchase_for")),
        "contact_channels": allowed_channels,
        "do_not_contact": do_not_contact,
        "marketing_consent": bool(allowed_channels) and not do_not_contact,
        "recommended_contact_channel": recommended_channel,
        "glame_values": _unique_strings(source.get("glame_values")),
        "personal_data_consent": bool(source.get("personal_data_consent")),
        "submitted_at": source.get("submitted_at"),
        "submitted_by_user_id": source.get("submitted_by_user_id"),
    }


def questionnaire_from_preferences(preferences: dict[str, Any] | None) -> dict[str, Any] | None:
    raw = (preferences or {}).get("buyer_questionnaire")
    if not isinstance(raw, dict):
        return None
    return normalize_questionnaire(raw)


def crm_contact_instruction(profile: dict[str, Any] | None) -> str:
    if not profile:
        return "Канал связи не указан: уточните способ контакта у клиента."
    if profile.get("do_not_contact"):
        return "Клиент отказался от сообщений. Не писать и не звонить по маркетинговым поводам."
    channels = profile.get("contact_channels") or []
    if not channels:
        return "Согласие на канал связи не зафиксировано: не отправляйте маркетинговые сообщения."
    first = profile.get("recommended_contact_channel") or channels[0]
    alternatives = [channel for channel in channels if channel != first]
    suffix = f" Альтернатива: {', '.join(alternatives)}." if alternatives else ""
    return f"Начните с канала «{first}».{suffix}"


def onec_questionnaire_fields(profile: dict[str, Any]) -> dict[str, Any]:
    """Map questionnaire fields to confirmed 1C requisites configured per deployment.

    Example: ONEC_CUSTOMER_QUESTIONNAIRE_FIELDS_JSON={"preferred_contact_channel":"ПредпочтительныйКаналСвязи"}
    We intentionally do not guess custom 1C requisites: an unknown field makes
    the whole catalogue PATCH fail and would prevent issuing the loyalty card.
    """
    raw_mapping = (os.getenv("ONEC_CUSTOMER_QUESTIONNAIRE_FIELDS_JSON") or "").strip()
    if not raw_mapping:
        return {}
    try:
        mapping = json.loads(raw_mapping)
    except json.JSONDecodeError:
        return {}
    if not isinstance(mapping, dict):
        return {}
    result: dict[str, Any] = {}
    for profile_key, onec_field in mapping.items():
        field_name = str(onec_field or "").strip()
        if not field_name or profile_key not in profile:
            continue
        value = profile[profile_key]
        result[field_name] = ", ".join(value) if isinstance(value, list) else value
    return result
