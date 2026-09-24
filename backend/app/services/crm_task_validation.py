from __future__ import annotations

from datetime import date
from typing import Optional

CONTACT_OUTCOMES = {
    "sent_no_reply",
    "replied",
    "requested_photo_video",
    "photo_video_sent",
    "sale",
    "no_answer",
    "service_requested",
    "in_dialogue",
    "waiting_in_store",
    "purchased",
    "service",
    "interested",
    "not_interested",
    "out_of_town",
    "online_selection",
    "asked_for_video",
    "asked_for_more_photos",
    "plans_visit",
    "no_response",
    "follow_up_later",
}
TERMINAL_OUTCOME_STATUS = {
    "not_relevant": "not_relevant",
    "do_not_disturb": "do_not_disturb",
    "quality_complaint": "quality_complaint",
}
POSTPONE_OUTCOME = "postpone"


def validate_crm_task_result(seller_outcome: str, seller_comment: str, next_action_date: str | date | None) -> str:
    """Return next CRM task status or raise ValueError for invalid seller input."""
    outcome = (seller_outcome or "").strip()
    comment = (seller_comment or "").strip()
    if not outcome:
        raise ValueError("Не выбран итог CRM-касания")
    if not comment:
        raise ValueError("Комментарий продавца обязателен")
    if outcome == POSTPONE_OUTCOME:
        if not next_action_date:
            raise ValueError("Для переноса нужна следующая дата действия")
        return "postponed"
    if outcome == "follow_up_later" and not next_action_date:
        raise ValueError("Для follow-up нужна следующая дата действия")
    if outcome in TERMINAL_OUTCOME_STATUS:
        return TERMINAL_OUTCOME_STATUS[outcome]
    return "worked"


def _value_to_iso(value: object) -> object:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def build_crm_customer_message_payload(
    *,
    task_id: str,
    status: str,
    seller_outcome: str,
    seller_comment: str,
    next_action_date: object = None,
    crm_group: object = None,
    reason: object = None,
    seller_action: object = None,
    script_key: object = None,
    store_name: object = None,
    seller_name: object = None,
    work_date: object = None,
    campaign_id: object = None,
    campaign_name: object = None,
) -> dict[str, object]:
    """Build payload expected by the customer card Messages tab for CRM interactions."""
    return {
        "source": "seller_crm_task",
        "message_kind": "crm_call",
        "crm_task_id": task_id,
        "work_status": status,
        "seller_outcome": seller_outcome,
        "seller_comment": seller_comment,
        "comment": seller_comment,
        "next_action_date": _value_to_iso(next_action_date),
        "crm_group": crm_group,
        "interaction_reason": reason,
        "segment_reason": reason,
        "seller_task": seller_action,
        "script_key": script_key,
        "preferred_store": store_name,
        "interacted_by": seller_name,
        "responsible": seller_name,
        "interaction_date": _value_to_iso(work_date),
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
    }
