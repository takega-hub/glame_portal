from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import date
from typing import Any, Dict, Optional

CRM_PLAN_STATUSES = {
    "draft",
    "needs_elena_approval",
    "approved",
    "ready_for_sellers",
    "launched",
    "measured",
}

CRM_GUARDRAILS = [
    "no_mass_send_without_approval",
    "no_comfort_budget_for_crimea",
    "no_passive_look_at_selection_wording",
    "no_pity_or_panic_discount_tone",
    "vip_needs_personal_script",
    "telegram_is_input_platform_is_source_of_truth",
]

DEFAULT_CRM_PLAN: Dict[str, Any] = {
    "status": "draft",
    "goal": "",
    "campaign_name": "",
    "segment": {
        "segment_id": None,
        "segment_name": "",
        "customer_count": 0,
        "rules_summary": "",
        "exclusions": [],
    },
    "scenario": {
        "channel": "combined",
        "seller_action": "",
        "timing": "",
        "priority": "normal",
    },
    "scripts": {
        "call_opener": "",
        "main_message": "",
        "vip_message": "",
        "follow_up": "",
        "objection_reply": "",
        "seller_note": "",
    },
    "approval": {
        "required_by": "elena",
        "approved_by": None,
        "approved_at": None,
        "approval_notes": "",
    },
    "risks": [],
    "next_action": "",
    "guardrails": CRM_GUARDRAILS,
}


def _merge_defaults(default: Any, value: Any) -> Any:
    if isinstance(default, dict):
        result = deepcopy(default)
        if isinstance(value, dict):
            for key, item in value.items():
                if key in result:
                    result[key] = _merge_defaults(result[key], item)
                else:
                    result[key] = item
        return result
    if isinstance(default, list):
        if isinstance(value, list):
            return value
        return deepcopy(default)
    return value if value is not None else default


def normalize_crm_plan(plan: Optional[Dict[str, Any]], *, fallback_text: str = "") -> Dict[str, Any]:
    """Normalize AI CRM output into the platform contract stored in task.output_data.crm_plan."""
    data = _merge_defaults(DEFAULT_CRM_PLAN, plan or {})
    status = str(data.get("status") or "draft").strip().lower()
    data["status"] = status if status in CRM_PLAN_STATUSES else "draft"
    data["guardrails"] = list(dict.fromkeys([*CRM_GUARDRAILS, *list(data.get("guardrails") or [])]))
    if not data.get("goal") and fallback_text:
        data["goal"] = fallback_text.strip()[:280]
    segment = data.setdefault("segment", {})
    try:
        segment["customer_count"] = int(segment.get("customer_count") or 0)
    except Exception:
        segment["customer_count"] = 0
    approval = data.setdefault("approval", {})
    approval["required_by"] = approval.get("required_by") or "elena"
    scripts = data.setdefault("scripts", {})
    main_message = str(scripts.get("main_message") or "")
    if "посмотреть подборку" in main_message.lower():
        scripts["main_message"] = re.sub(
            "посмотреть подборку",
            "подготовлю для вас видео-подборку",
            main_message,
            flags=re.IGNORECASE,
        )
    return data


def extract_crm_plan_from_text(text: str) -> Dict[str, Any]:
    """Extract a CRM plan JSON object from an AI CRM answer; fallback stores text as draft context."""
    raw = text or ""
    candidates = []
    for match in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.DOTALL | re.IGNORECASE):
        candidates.append(match.group(1))
    stripped = raw.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        candidates.append(stripped)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                if isinstance(parsed.get("crm_plan"), dict):
                    parsed = parsed["crm_plan"]
                return normalize_crm_plan(parsed, fallback_text=raw)
        except Exception:
            continue
    return normalize_crm_plan({"goal": raw[:280], "scripts": {"main_message": raw}}, fallback_text=raw)


def crm_plan_to_seller_task_defaults(plan: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_crm_plan(plan)
    campaign_name = normalized.get("campaign_name") or normalized.get("goal") or "AI CRM"
    segment = normalized.get("segment") or {}
    scenario = normalized.get("scenario") or {}
    scripts = normalized.get("scripts") or {}
    return {
        "work_date": date.today(),
        "priority": 2 if scenario.get("priority") in {"high", "vip"} else 3,
        "crm_group": "ai_crm_plan",
        "reason": normalized.get("goal") or campaign_name,
        "seller_action": scenario.get("seller_action") or normalized.get("next_action") or "Отработать CRM-сценарий",
        "script_key": "ai_crm_plan",
        "script_text": scripts.get("seller_note") or scripts.get("call_opener") or scripts.get("main_message") or "",
        "campaign_name": campaign_name,
        "campaign_id": str(segment.get("segment_id") or campaign_name),
        "source": "ai_crm_plan",
        "source_payload": normalized,
    }


GLAME_CRM_OPERATING_CONTEXT = """
=== GLAME CRM OPERATING CONTEXT ===
Ты — AI CRM GLAME внутри платформы. Работай как Hermes ранее работал с Еленой в Telegram, но source of truth — GLAME Platform.

Обязательный процесс:
1) уточни цель CRM-касания, если она не ясна;
2) предложи или используй сегмент, не придумывай фактические размеры без БД;
3) раздели сценарии: звонок, личное сообщение, видео-подборка, VIP/private offer, follow-up;
4) дай готовые скрипты продавцу;
5) зафиксируй риски и approval;
6) не запускай массовую коммуникацию без согласования Елены/админа;
7) результат должен быть пригоден для сохранения как crm_plan и последующего создания CRM-задач продавцам.

Guardrails:
- no_comfort_budget_for_crimea: для Крыма не использовать «комфортный бюджет»; продавать через ценность, срочность, конкретную выгоду, последние позиции, подарок/комплект.
- no_passive_look_at_selection_wording: не писать «посмотреть подборку», писать «подготовлю для вас видео-подборку».
- no_pity_or_panic_discount_tone: не давить жалостью и не звучать как дешёвая паническая распродажа.
- vip_needs_personal_script: VIP не получают общий массовый текст.
- telegram_is_input_platform_is_source_of_truth: Telegram может быть входом, но итог фиксируется в платформе.

Если пользователь просит финализировать результат, верни CRM-план в JSON contract: status, goal, campaign_name, segment, scenario, scripts, approval, risks, next_action.
""".strip()
