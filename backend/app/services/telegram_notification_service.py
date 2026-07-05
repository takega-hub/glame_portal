from __future__ import annotations

import logging
import os
from typing import Any

from app.models.referral import ReferralProgramMember
from app.models.user import User
from app.services.telegram_service import TelegramService


logger = logging.getLogger(__name__)


def _env_bool(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _split_chat_ids(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]


def _partner_chat_id(user: User | None = None, member: ReferralProgramMember | None = None) -> str | None:
    member_meta = member.meta if member is not None and isinstance(member.meta, dict) else {}
    user_preferences = user.preferences if user is not None and isinstance(user.preferences, dict) else {}
    candidates = [
        member_meta.get("telegram_chat_id"),
        (member_meta.get("telegram") or {}).get("chat_id") if isinstance(member_meta.get("telegram"), dict) else None,
        user_preferences.get("telegram_chat_id"),
        (user_preferences.get("telegram") or {}).get("chat_id") if isinstance(user_preferences.get("telegram"), dict) else None,
    ]
    for item in candidates:
        if item:
            return str(item).strip()
    return None


class TelegramNotificationService:
    """Small best-effort Telegram notification layer for GLAME operations."""

    def __init__(self) -> None:
        self.enabled = _env_bool("TELEGRAM_NOTIFICATIONS_ENABLED", "false")
        self.admin_enabled = _env_bool("TELEGRAM_ADMIN_NOTIFICATIONS_ENABLED", "true")
        self.partner_enabled = _env_bool("TELEGRAM_PARTNER_NOTIFICATIONS_ENABLED", "true")
        self.admin_chat_ids = _split_chat_ids(os.getenv("TELEGRAM_ADMIN_CHAT_IDS"))
        self.partner_portal_url = os.getenv("TELEGRAM_PARTNER_PORTAL_URL", "https://partner.glamejewelry.ru/referral")

    @staticmethod
    def config_payload() -> dict[str, Any]:
        return {
            "enabled": _env_bool("TELEGRAM_NOTIFICATIONS_ENABLED", "false"),
            "bot_token_configured": bool((os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()),
            "admin_enabled": _env_bool("TELEGRAM_ADMIN_NOTIFICATIONS_ENABLED", "true"),
            "partner_enabled": _env_bool("TELEGRAM_PARTNER_NOTIFICATIONS_ENABLED", "true"),
            "admin_chat_ids_count": len(_split_chat_ids(os.getenv("TELEGRAM_ADMIN_CHAT_IDS"))),
            "partner_chat_source": "referral_program_members.meta.telegram_chat_id or users.preferences.telegram_chat_id",
        }

    def _configured(self) -> bool:
        return self.enabled and bool((os.getenv("TELEGRAM_BOT_TOKEN") or "").strip())

    async def _send_many(self, chat_ids: list[str], text: str) -> dict[str, Any]:
        if not self._configured():
            return {"status": "skipped", "reason": "telegram_notifications_disabled_or_token_missing"}
        if not chat_ids:
            return {"status": "skipped", "reason": "no_chat_ids"}
        sent = 0
        errors: list[str] = []
        try:
            async with TelegramService() as telegram:
                for chat_id in chat_ids:
                    try:
                        await telegram.send_message(chat_id=chat_id, text=text)
                        sent += 1
                    except Exception as error:  # noqa: BLE001 - notification must be best effort
                        errors.append(f"{chat_id}: {str(error)[:200]}")
                        logger.warning("Telegram notification failed for chat %s: %s", chat_id, error)
        except Exception as error:  # noqa: BLE001
            return {"status": "failed", "sent": sent, "errors": [str(error)[:500], *errors]}
        return {"status": "success" if not errors else "partial", "sent": sent, "errors": errors}

    async def notify_admin(self, *, title: str, lines: list[str] | None = None, severity: str = "info") -> dict[str, Any]:
        if not self.admin_enabled:
            return {"status": "skipped", "reason": "admin_notifications_disabled"}
        prefix = {
            "critical": "[CRITICAL]",
            "warning": "[WARNING]",
            "success": "[OK]",
            "info": "[INFO]",
        }.get(severity, "[INFO]")
        body = "\n".join([f"{prefix} {title}", *(lines or [])])
        return await self._send_many(self.admin_chat_ids, body[:3900])

    async def notify_partner(
        self,
        *,
        user: User | None,
        member: ReferralProgramMember | None,
        title: str,
        lines: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.partner_enabled:
            return {"status": "skipped", "reason": "partner_notifications_disabled"}
        chat_id = _partner_chat_id(user=user, member=member)
        if not chat_id:
            return {"status": "skipped", "reason": "partner_telegram_chat_id_missing"}
        body = "\n".join([title, *(lines or []), "", self.partner_portal_url])
        return await self._send_many([chat_id], body[:3900])

    async def notify_admin_and_partner(
        self,
        *,
        user: User | None,
        member: ReferralProgramMember | None,
        admin_title: str,
        partner_title: str,
        lines: list[str] | None = None,
        severity: str = "info",
    ) -> dict[str, Any]:
        admin_result = await self.notify_admin(title=admin_title, lines=lines, severity=severity)
        partner_result = await self.notify_partner(user=user, member=member, title=partner_title, lines=lines)
        return {"admin": admin_result, "partner": partner_result}
