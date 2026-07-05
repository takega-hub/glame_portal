from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.glame_token import GlameTokenBridgeOperation
from app.models.referral import ReferralProgramMember
from app.models.user import User
from app.services.onec_customers_service import OneCCustomersService
from app.services.telegram_notification_service import TelegramNotificationService
from app.services.ton_glm_auto_transfer_service import TonGlmAutoTransferService
from app.services.ton_glm_treasury_balance_service import TonGlmTreasuryBalanceService


logger = logging.getLogger(__name__)


def _env_bool(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default) or default)
    except Exception:
        return int(default)


class GlmTelegramAlertService:
    """Bridge/readiness alert escalation to admin Telegram with cooldown state."""

    STATE_FILE = Path(__file__).resolve().parents[2] / "static" / "glm_policy" / "telegram-alert-state.json"

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def config_payload() -> dict[str, Any]:
        partner_url = os.getenv("TELEGRAM_PARTNER_PORTAL_URL", "https://partner.glamejewelry.ru/referral")
        admin_url = os.getenv("TELEGRAM_ADMIN_PORTAL_URL", "https://portal.glamejewelry.ru/admin/referrals")
        return {
            "enabled": _env_bool("GLM_TELEGRAM_ALERTS_ENABLED", "true"),
            "interval_minutes": int(os.getenv("GLM_TELEGRAM_ALERTS_INTERVAL_MINUTES", "15") or 15),
            "initial_delay_seconds": int(os.getenv("GLM_TELEGRAM_ALERTS_INITIAL_DELAY_SECONDS", "300") or 300),
            "cooldown_minutes": int(os.getenv("GLM_TELEGRAM_ALERTS_COOLDOWN_MINUTES", "60") or 60),
            "stale_minutes": int(os.getenv("GLM_TELEGRAM_ALERTS_STALE_MINUTES", os.getenv("TON_GLM_BRIDGE_DOMAIN_STALE_MINUTES", "60")) or 60),
            "refill_escalation_enabled": _env_bool("TON_GLM_HOT_WALLET_REFILL_ESCALATION_ENABLED", "true"),
            "refill_escalation_minutes": _env_int("TON_GLM_HOT_WALLET_REFILL_ESCALATION_MINUTES", "120"),
            "loyalty_reconciliation_enabled": _env_bool("GLM_LOYALTY_RECONCILIATION_ALERTS_ENABLED", "true"),
            "loyalty_lots_alerts_enabled": _env_bool("GLM_LOYALTY_LOTS_ALERTS_ENABLED", "false"),
            "loyalty_reconciliation_limit": _env_int("GLM_LOYALTY_RECONCILIATION_ALERTS_LIMIT", "50"),
            "state_file": str(GlmTelegramAlertService.STATE_FILE),
            "partner_portal_url": partner_url,
            "admin_portal_url": admin_url,
        }

    @staticmethod
    def _admin_url(anchor: str = "") -> str:
        base = os.getenv("TELEGRAM_ADMIN_PORTAL_URL", "https://portal.glamejewelry.ru/admin/referrals").strip()
        base = base or "https://portal.glamejewelry.ru/admin/referrals"
        return f"{base}{anchor}" if anchor else base

    @classmethod
    def _action_for_code(cls, code: str) -> dict[str, str]:
        if code in {
            "hot_wallet_refill_glm_low",
            "hot_wallet_refill_ton_low",
            "hot_wallet_refill_glm_overdue",
            "hot_wallet_refill_ton_overdue",
            "hot_wallet_glm_low",
            "hot_wallet_ton_low",
        }:
            return {
                "action_label": "Открыть TON readiness / refill plan",
                "action_url": cls._admin_url("#ton-readiness"),
            }
        if code.startswith("treasury_") or code.endswith("_balance_error"):
            return {
                "action_label": "Открыть TON treasury balances",
                "action_url": cls._admin_url("#ton-readiness"),
            }
        if code == "auto_transfer_paused" or code.startswith("points_to_glm"):
            return {
                "action_label": "Открыть очередь Баллы -> GLM",
                "action_url": cls._admin_url("#glm-claims"),
            }
        if code.startswith("glm_to_points"):
            return {
                "action_label": "Открыть очередь GLM -> баллы",
                "action_url": cls._admin_url("#glm-to-points"),
            }
        if code.startswith("bridge_domain"):
            return {
                "action_label": "Открыть bridge reconciliation",
                "action_url": cls._admin_url("#glm-bridge-reconciliation"),
            }
        if code.startswith("loyalty_reconciliation"):
            return {
                "action_label": "Открыть 1C bonus reconciliation",
                "action_url": cls._admin_url("#glm-bridge-reconciliation"),
            }
        return {
            "action_label": "Открыть CryptoGLAME admin",
            "action_url": cls._admin_url(),
        }

    @classmethod
    def _decorate_alert(cls, alert: dict[str, Any]) -> dict[str, Any]:
        decorated = dict(alert)
        code = str(decorated.get("code") or "")
        action = cls._action_for_code(code)
        decorated.setdefault("action_label", action["action_label"])
        decorated.setdefault("action_url", action["action_url"])
        return decorated

    @classmethod
    def _read_state(cls) -> dict[str, Any]:
        if not cls.STATE_FILE.exists():
            return {"alerts": {}}
        try:
            payload = json.loads(cls.STATE_FILE.read_text(encoding="utf-8"))
        except Exception as error:
            logger.warning("Failed to read GLM Telegram alert state: %s", error)
            return {"alerts": {}}
        return payload if isinstance(payload, dict) else {"alerts": {}}

    @classmethod
    def state_summary(cls, codes: list[str] | None = None) -> dict[str, Any]:
        state = cls._read_state()
        alerts = state.get("alerts") if isinstance(state.get("alerts"), dict) else {}
        selected_codes = set(codes or [])
        items: dict[str, Any] = {}
        for code, payload in alerts.items():
            if selected_codes and code not in selected_codes:
                continue
            if not isinstance(payload, dict):
                continue
            items[str(code)] = {
                "fingerprint": payload.get("fingerprint"),
                "last_sent_at": payload.get("last_sent_at"),
                "message": payload.get("message"),
            }
        return {
            "state_file_exists": cls.STATE_FILE.exists(),
            "alerts": items,
        }

    @classmethod
    def _write_state(cls, state: dict[str, Any]) -> None:
        cls.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        cls.STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    async def _collect_refill_overdue_alerts(
        self,
        *,
        treasury_service: TonGlmTreasuryBalanceService,
        treasury_payload: dict[str, Any],
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        config = self.config_payload()
        if not config.get("refill_escalation_enabled"):
            return []
        escalation_minutes = max(1, int(config.get("refill_escalation_minutes") or 120))
        state_alerts = state.get("alerts") if isinstance(state.get("alerts"), dict) else {}
        active_low_alerts = {
            str(item.get("code")): item
            for item in treasury_payload.get("alerts") or []
            if isinstance(item, dict)
        }
        mapping = {
            "hot_wallet_refill_glm_low": ("hot_wallet_refill_glm_overdue", "GLM"),
            "hot_wallet_refill_ton_low": ("hot_wallet_refill_ton_overdue", "TON gas"),
        }
        now = datetime.now(timezone.utc)
        result: list[dict[str, Any]] = []
        activity_cache: dict[str, Any] = {}

        for base_code, (overdue_code, metric_label) in mapping.items():
            base_alert = active_low_alerts.get(base_code)
            previous = state_alerts.get(base_code) if isinstance(state_alerts.get(base_code), dict) else {}
            first_warning_at = self._parse_datetime(previous.get("last_sent_at"))
            if not base_alert or not first_warning_at:
                continue
            elapsed = now - first_warning_at
            if elapsed < timedelta(minutes=escalation_minutes):
                continue
            if "activity" not in activity_cache:
                activity_cache["activity"] = await treasury_service.refill_activity_since(first_warning_at)
            activity = activity_cache["activity"]
            if activity.get("has_recovery_activity"):
                continue

            wallet = base_alert.get("wallet") if isinstance(base_alert.get("wallet"), dict) else {}
            balance = wallet.get("glm_balance") if metric_label == "GLM" else wallet.get("ton_balance")
            threshold = (
                wallet.get("refill_threshold_glm")
                if metric_label == "GLM"
                else wallet.get("refill_threshold_ton")
            )
            target = wallet.get("refill_target_glm") if metric_label == "GLM" else wallet.get("refill_target_ton")
            latest = activity.get("latest") if isinstance(activity.get("latest"), dict) else {}
            elapsed_minutes = int(elapsed.total_seconds() // 60)
            result.append(
                {
                    "code": overdue_code,
                    "severity": "critical",
                    "fingerprint": (
                        f"{overdue_code}:{first_warning_at.isoformat()}:{balance}:{threshold}:"
                        f"{target}:{latest.get('id') or 'none'}"
                    ),
                    "message": (
                        f"Hot-wallet все еще ниже refill-лимита по {metric_label}: "
                        f"баланс {balance}, лимит {threshold}, цель {target}. "
                        f"Первый warning был {elapsed_minutes} мин назад, но в журнале нет manual_refill "
                        f"или успешной проверки восстановления."
                    ),
                }
            )
        return result

    async def _collect_loyalty_reconciliation_alerts(self) -> list[dict[str, Any]]:
        config = self.config_payload()
        if not config.get("loyalty_reconciliation_enabled"):
            return []

        limit = max(1, int(config.get("loyalty_reconciliation_limit") or 50))
        rows = (
            await self.db.execute(
                select(ReferralProgramMember, User)
                .join(User, User.id == ReferralProgramMember.user_id)
                .where(User.discount_card_id_1c.is_not(None))
                .order_by(ReferralProgramMember.created_at.desc())
                .limit(limit)
            )
        ).all()
        if not rows:
            return []

        platform_working_issues: list[dict[str, Any]] = []
        working_lots_issues: list[dict[str, Any]] = []
        service_errors: list[str] = []

        async with OneCCustomersService() as onec:
            for member, user in rows:
                partner_label = user.full_name or user.phone or str(member.id)
                try:
                    working_payload = await onec.fetch_loyalty_balance(
                        getattr(user, "customer_id_1c", None),
                        getattr(user, "discount_card_id_1c", None),
                    )
                    lots_payload = await onec.fetch_loyalty_lots_balance(
                        getattr(user, "customer_id_1c", None),
                        getattr(user, "discount_card_id_1c", None),
                    )
                except Exception as error:
                    service_errors.append(f"{partner_label}: {str(error)[:160]}")
                    continue

                platform_points = int(getattr(user, "loyalty_points", 0) or 0)
                working_points = int((working_payload or {}).get("balance") or 0)
                lots_points = int((lots_payload or {}).get("balance") or 0)
                if platform_points != working_points:
                    platform_working_issues.append(
                        {
                            "member_id": str(member.id),
                            "partner": partner_label,
                            "platform": platform_points,
                            "working": working_points,
                            "delta": platform_points - working_points,
                        }
                    )
                if working_points != lots_points:
                    working_lots_issues.append(
                        {
                            "member_id": str(member.id),
                            "partner": partner_label,
                            "working": working_points,
                            "lots": lots_points,
                            "delta": working_points - lots_points,
                        }
                    )

        alerts: list[dict[str, Any]] = []
        if platform_working_issues:
            examples = platform_working_issues[:3]
            examples_text = "; ".join(
                f"{item['partner']}: платформа {item['platform']} / 1C {item['working']}"
                for item in examples
            )
            fingerprint = ":".join(
                f"{item['member_id']}:{item['platform']}:{item['working']}"
                for item in platform_working_issues[:10]
            )
            alerts.append(
                {
                    "code": "loyalty_reconciliation_platform_working_mismatch",
                    "severity": "critical",
                    "fingerprint": f"platform_working:{len(platform_working_issues)}:{fingerprint}",
                    "message": (
                        f"1C bonus reconciliation: {len(platform_working_issues)} партнеров имеют "
                        f"расхождение платформа vs 1C К списанию. Примеры: {examples_text}"
                    ),
                }
            )
        if working_lots_issues and config.get("loyalty_lots_alerts_enabled"):
            examples = working_lots_issues[:3]
            examples_text = "; ".join(
                f"{item['partner']}: К списанию {item['working']} / лоты {item['lots']}"
                for item in examples
            )
            fingerprint = ":".join(
                f"{item['member_id']}:{item['working']}:{item['lots']}"
                for item in working_lots_issues[:10]
            )
            alerts.append(
                {
                    "code": "loyalty_reconciliation_lots_mismatch",
                    "severity": "warning",
                    "fingerprint": f"working_lots:{len(working_lots_issues)}:{fingerprint}",
                    "message": (
                        f"1C bonus reconciliation: {len(working_lots_issues)} партнеров имеют "
                        f"расхождение 1C К списанию vs лоты формы карты. Примеры: {examples_text}"
                    ),
                }
            )
        if service_errors:
            fingerprint = ":".join(service_errors[:5])
            alerts.append(
                {
                    "code": "loyalty_reconciliation_check_error",
                    "severity": "warning",
                    "fingerprint": f"check_error:{len(service_errors)}:{fingerprint}",
                    "message": (
                        f"1C bonus reconciliation не смогла проверить {len(service_errors)} партнеров. "
                        f"Примеры: {'; '.join(service_errors[:3])}"
                    ),
                }
            )
        return alerts

    async def collect_alerts(self) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        stale_minutes = int(self.config_payload()["stale_minutes"])
        stale_before = now - timedelta(minutes=max(1, stale_minutes))
        alerts: list[dict[str, Any]] = []
        state = self._read_state()

        auto_transfer_config = TonGlmAutoTransferService.config_payload()
        if auto_transfer_config.get("override", {}).get("enabled") is False:
            alerts.append(
                {
                    "code": "auto_transfer_paused",
                    "severity": "critical",
                    "fingerprint": "auto_transfer_paused",
                    "message": "points_to_glm auto-transfer поставлен на паузу; новые заявки не уйдут в TON автоматически.",
                }
            )

        rows = (
            await self.db.execute(
                select(GlameTokenBridgeOperation)
                .where(GlameTokenBridgeOperation.status == "pending")
                .order_by(GlameTokenBridgeOperation.requested_at.asc().nulls_last())
                .limit(500)
            )
        ).scalars().all()

        stale_count = 0
        stale_amount = 0
        ton_waiting_count = 0
        ton_waiting_amount = 0
        onec_issue_count = 0
        onec_issue_amount = 0

        for operation in rows:
            amount = int(operation.glm_amount or operation.points_amount or 0)
            requested_at = operation.requested_at or operation.created_at
            if requested_at and requested_at.tzinfo is None:
                requested_at = requested_at.replace(tzinfo=timezone.utc)
            if requested_at and requested_at < stale_before:
                stale_count += 1
                stale_amount += amount
            ton_status = str(operation.ton_status or "").strip()
            if ton_status in {"waiting_for_deposit", "wallet_request_prepared", "sent", "sent_waiting_settlement"}:
                ton_waiting_count += 1
                ton_waiting_amount += amount
            onec_status = str(operation.onec_status or "").strip()
            if onec_status in {"failed", "ready_for_1c", "created_without_ref_key", "posted_without_balance_change"}:
                onec_issue_count += 1
                onec_issue_amount += amount

        if stale_count:
            alerts.append(
                {
                    "code": "bridge_domain_stale_pending",
                    "severity": "warning",
                    "fingerprint": f"bridge_domain_stale_pending:{stale_count}:{stale_amount}",
                    "message": f"{stale_count} bridge-операций pending дольше {stale_minutes} минут на {stale_amount} GLM.",
                }
            )
        if ton_waiting_count:
            alerts.append(
                {
                    "code": "bridge_domain_ton_waiting",
                    "severity": "warning",
                    "fingerprint": f"bridge_domain_ton_waiting:{ton_waiting_count}:{ton_waiting_amount}",
                    "message": f"{ton_waiting_count} bridge-операций ждут TON на {ton_waiting_amount} GLM.",
                }
            )
        if onec_issue_count:
            alerts.append(
                {
                    "code": "bridge_domain_onec_issues",
                    "severity": "warning",
                    "fingerprint": f"bridge_domain_onec_issues:{onec_issue_count}:{onec_issue_amount}",
                    "message": f"{onec_issue_count} bridge-операций имеют 1С issue на {onec_issue_amount} GLM.",
                }
            )
        if _env_bool("TON_GLM_TREASURY_BALANCE_ALERTS_ENABLED", "true"):
            treasury_service = TonGlmTreasuryBalanceService(self.db)
            treasury_payload = await treasury_service.payload()
            for item in treasury_payload.get("alerts") or []:
                alerts.append(
                    {
                        "code": item.get("code") or "treasury_balance_alert",
                        "severity": item.get("severity") or "warning",
                        "fingerprint": item.get("fingerprint") or item.get("message") or "treasury_balance_alert",
                        "message": item.get("message") or "TON treasury balance требует проверки.",
                    }
                )
            alerts.extend(
                await self._collect_refill_overdue_alerts(
                    treasury_service=treasury_service,
                    treasury_payload=treasury_payload,
                    state=state,
                )
            )
        alerts.extend(await self._collect_loyalty_reconciliation_alerts())
        return [self._decorate_alert(alert) for alert in alerts]

    async def run_once(self, *, force: bool = False) -> dict[str, Any]:
        config = self.config_payload()
        if not config["enabled"] and not force:
            return {"status": "skipped", "reason": "GLM_TELEGRAM_ALERTS_ENABLED=false"}

        alerts = await self.collect_alerts()
        if not alerts:
            return {"status": "ok", "alerts_count": 0, "sent": 0}

        now = datetime.now(timezone.utc)
        cooldown = timedelta(minutes=max(1, int(config["cooldown_minutes"])))
        state = self._read_state()
        state_alerts = state.setdefault("alerts", {})
        sendable: list[dict[str, Any]] = []

        for alert in alerts:
            code = str(alert["code"])
            previous = state_alerts.get(code) if isinstance(state_alerts.get(code), dict) else {}
            last_sent_raw = previous.get("last_sent_at")
            last_fingerprint = previous.get("fingerprint")
            last_sent_at: datetime | None = None
            if last_sent_raw:
                try:
                    last_sent_at = datetime.fromisoformat(str(last_sent_raw))
                except ValueError:
                    last_sent_at = None
            if last_sent_at and last_sent_at.tzinfo is None:
                last_sent_at = last_sent_at.replace(tzinfo=timezone.utc)
            fingerprint_changed = last_fingerprint != alert.get("fingerprint")
            cooldown_expired = last_sent_at is None or (now - last_sent_at) >= cooldown
            if force or fingerprint_changed or cooldown_expired:
                sendable.append(alert)

        if not sendable:
            return {"status": "cooldown", "alerts_count": len(alerts), "sent": 0}

        severity = "critical" if any(item.get("severity") == "critical" for item in sendable) else "warning"
        lines = []
        for item in sendable:
            lines.append(f"- [{item['severity']}] {item['message']}")
            if item.get("action_url"):
                lines.append(f"  → {item.get('action_label') or 'Открыть'}: {item['action_url']}")
        result = await TelegramNotificationService().notify_admin(
            title="CryptoGLAME bridge alerts",
            lines=[*lines, "", self.config_payload()["admin_portal_url"]],
            severity=severity,
        )

        if result.get("status") in {"success", "partial"}:
            for alert in sendable:
                state_alerts[str(alert["code"])] = {
                    "fingerprint": alert.get("fingerprint"),
                    "last_sent_at": now.isoformat(),
                    "severity": alert.get("severity"),
                    "message": alert.get("message"),
                }
            state["updated_at"] = now.isoformat()
            self._write_state(state)

        return {
            "status": result.get("status"),
            "alerts_count": len(alerts),
            "sendable_count": len(sendable),
            "sent": result.get("sent", 0),
            "errors": result.get("errors", []),
            "alerts": alerts,
        }
