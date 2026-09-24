from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.glame_token import GlameTokenBridgeOperation, GlameTokenTransaction
from app.models.loyalty_transaction import LoyaltyTransaction
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
            "loyalty_reconciliation_auto_sync_enabled": _env_bool("GLM_LOYALTY_RECONCILIATION_AUTO_SYNC_ENABLED", "true"),
            "loyalty_lots_alerts_enabled": _env_bool("GLM_LOYALTY_LOTS_ALERTS_ENABLED", "false"),
            "loyalty_reconciliation_limit": _env_int("GLM_LOYALTY_RECONCILIATION_ALERTS_LIMIT", "50"),
            "warning_digest_enabled": _env_bool("GLM_TELEGRAM_ALERTS_WARNING_DIGEST_ENABLED", "true"),
            "warning_digest_minutes": _env_int("GLM_TELEGRAM_ALERTS_WARNING_DIGEST_MINUTES", "240"),
            "warning_digest_max_items": _env_int("GLM_TELEGRAM_ALERTS_WARNING_DIGEST_MAX_ITEMS", "8"),
            "operations_attention_digest_enabled": _env_bool("GLM_OPERATIONS_ATTENTION_DIGEST_ENABLED", "true"),
            "operations_attention_digest_limit": _env_int("GLM_OPERATIONS_ATTENTION_DIGEST_LIMIT", "200"),
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
        if code == "glm_operations_attention_digest":
            return {
                "action_label": "Открыть очередь внимания GLM",
                "action_url": cls._admin_url("#glm-operations-attention"),
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
            first_warning_at = self._parse_datetime(previous.get("first_seen_at") or previous.get("last_sent_at"))
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
            target_label = "batch" if metric_label == "GLM" else "цель"
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
                        f"баланс {balance}, лимит {threshold}, {target_label} {target}. "
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
        auto_sync_enabled = bool(config.get("loyalty_reconciliation_auto_sync_enabled"))
        lots_alerts_enabled = bool(config.get("loyalty_lots_alerts_enabled"))
        now = datetime.now(timezone.utc)

        async with OneCCustomersService() as onec:
            for member, user in rows:
                partner_label = user.full_name or user.phone or str(member.id)
                try:
                    working_payload = await onec.fetch_loyalty_balance(
                        getattr(user, "customer_id_1c", None),
                        getattr(user, "discount_card_id_1c", None),
                    )
                except Exception as error:
                    service_errors.append(f"{partner_label}: {str(error)[:160]}")
                    continue

                lots_payload: dict[str, Any] | None = None
                if lots_alerts_enabled:
                    try:
                        lots_payload = await onec.fetch_loyalty_lots_balance(
                            getattr(user, "customer_id_1c", None),
                            getattr(user, "discount_card_id_1c", None),
                        )
                    except Exception as error:
                        service_errors.append(f"{partner_label}: lots balance check failed: {str(error)[:160]}")
                        continue

                platform_points = int(getattr(user, "loyalty_points", 0) or 0)
                working_balance_available = bool(working_payload and working_payload.get("balance") is not None)
                working_points = int((working_payload or {}).get("balance") or 0)
                lots_points = int((lots_payload or {}).get("balance") or 0) if lots_payload is not None else working_points
                if auto_sync_enabled and working_balance_available and platform_points != working_points:
                    delta = working_points - platform_points
                    user.loyalty_points = working_points
                    user.synced_at = now
                    self.db.add(
                        LoyaltyTransaction(
                            user_id=user.id,
                            transaction_type="sync_from_1c",
                            points=delta,
                            balance_after=working_points,
                            reason="partner_loyalty_reconciliation",
                            description=(
                                "Автосинхронизация баланса партнера из 1С: "
                                f"платформа {platform_points}, 1С {working_points}"
                            ),
                            source="1c",
                            source_id=str(
                                (working_payload or {}).get("source_id")
                                or getattr(user, "discount_card_id_1c", None)
                                or getattr(user, "customer_id_1c", None)
                                or ""
                            ),
                        )
                    )
                    platform_points = working_points

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

    async def _collect_operations_attention_digest_alerts(self) -> list[dict[str, Any]]:
        config = self.config_payload()
        if not config.get("operations_attention_digest_enabled"):
            return []

        now = datetime.now(timezone.utc)
        stale_minutes = int(config.get("stale_minutes") or 60)
        stale_before = now - timedelta(minutes=max(1, stale_minutes))
        limit = max(1, int(config.get("operations_attention_digest_limit") or 200))
        closed_statuses = {"processed", "canceled", "cancelled", "superseded", "failed_reviewed", "manual_reviewed"}
        ton_waiting_statuses = {
            "sent",
            "sent_waiting_settlement",
            "wallet_request_prepared",
            "waiting_for_deposit",
            "not_found",
        }
        onec_issue_statuses = {
            "failed",
            "missing_discount_card",
            "ready_for_1c",
            "ready_for_1c_spend",
            "posted_without_balance_change",
            "created_without_ref_key",
        }

        def normalize_dt(value: datetime | None) -> datetime | None:
            if value is None:
                return None
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value

        def age_minutes(value: datetime | None) -> int:
            normalized = normalize_dt(value)
            if normalized is None:
                return 0
            return max(0, int((now - normalized).total_seconds() // 60))

        items: list[dict[str, Any]] = []
        bridge_rows = (
            await self.db.execute(
                select(GlameTokenBridgeOperation, User)
                .outerjoin(User, User.id == GlameTokenBridgeOperation.user_id)
                .where(GlameTokenBridgeOperation.token_code == "GLM")
                .order_by(GlameTokenBridgeOperation.updated_at.desc().nulls_last(), GlameTokenBridgeOperation.created_at.desc())
                .limit(limit)
            )
        ).all()
        for operation, user in bridge_rows:
            op_status = str(operation.status or "")
            ton_status = str(operation.ton_status or "")
            onec_status = str(operation.onec_status or "")
            requested_at = normalize_dt(operation.requested_at or operation.created_at)
            is_open = op_status not in closed_statuses
            is_stale = op_status == "pending" and requested_at is not None and requested_at < stale_before
            is_ton_waiting = op_status == "pending" and ton_status in ton_waiting_statuses
            is_onec_issue = is_open and onec_status in onec_issue_statuses
            if not (is_stale or is_ton_waiting or is_onec_issue):
                continue

            kind = "stale"
            severity = "warning"
            if is_onec_issue:
                kind = "1C"
                severity = "critical"
            elif is_ton_waiting:
                kind = "TON"
                severity = "critical" if age_minutes(requested_at) >= stale_minutes else "warning"
            amount = int(operation.glm_amount or operation.points_amount or 0)
            items.append(
                {
                    "id": str(operation.id),
                    "kind": kind,
                    "severity": severity,
                    "partner": getattr(user, "full_name", None) or getattr(user, "phone", None) or "Партнер GLAME",
                    "amount": amount,
                    "age": age_minutes(requested_at),
                    "direction": operation.direction,
                    "status": op_status,
                }
            )

        refund_rows = (
            await self.db.execute(
                select(GlameTokenTransaction, User)
                .outerjoin(User, User.id == GlameTokenTransaction.user_id)
                .where(
                    GlameTokenTransaction.token_code == "GLM",
                    GlameTokenTransaction.transaction_type == "redemption",
                    GlameTokenTransaction.status.in_(("canceled", "cancelled", "failed", "refund_pending", "refund_required")),
                )
                .order_by(GlameTokenTransaction.created_at.desc())
                .limit(limit)
            )
        ).all()
        for tx, user in refund_rows:
            meta = tx.meta if isinstance(tx.meta, dict) else {}
            refund_required = bool(meta.get("ton_refund_required"))
            refund_status = str(meta.get("ton_refund_status") or "")
            if not refund_required and refund_status not in {"required", "submitted", "pending", "sent"}:
                continue
            items.append(
                {
                    "id": str(tx.id),
                    "kind": "refund",
                    "severity": "critical" if not meta.get("ton_refund_tx_hash") else "warning",
                    "partner": getattr(user, "full_name", None) or getattr(user, "phone", None) or "Партнер GLAME",
                    "amount": abs(int(tx.amount or 0)),
                    "age": age_minutes(tx.created_at),
                    "direction": "refund",
                    "status": str(tx.status or ""),
                }
            )

        if not items:
            return []

        items.sort(key=lambda item: (0 if item.get("severity") == "critical" else 1, -int(item.get("age") or 0)))
        total = len(items)
        critical = sum(1 for item in items if item.get("severity") == "critical")
        by_kind: dict[str, int] = {}
        amount_total = 0
        for item in items:
            by_kind[str(item.get("kind") or "unknown")] = by_kind.get(str(item.get("kind") or "unknown"), 0) + 1
            amount_total += int(item.get("amount") or 0)
        examples = "; ".join(
            f"{item['kind']} {item['amount']} GLM {item['partner']} ({item['age']} мин)"
            for item in items[:5]
        )
        fingerprint = ":".join(
            f"{item['id']}:{item['kind']}:{item['status']}:{item['amount']}:{item['age'] // 60}"
            for item in items[:20]
        )
        kind_text = ", ".join(f"{kind}: {count}" for kind, count in sorted(by_kind.items()))
        return [
            {
                "code": "glm_operations_attention_digest",
                "severity": "warning",
                "fingerprint": f"glm_operations_attention:{total}:{critical}:{amount_total}:{fingerprint}",
                "message": (
                    f"Очередь внимания GLM: {total} unresolved операций, critical {critical}, "
                    f"суммарно {amount_total} GLM. Типы: {kind_text}. Примеры: {examples}"
                ),
            }
        ]

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
        alerts.extend(await self._collect_operations_attention_digest_alerts())
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
        state_changed = False

        for alert in alerts:
            code = str(alert["code"])
            previous = state_alerts.get(code) if isinstance(state_alerts.get(code), dict) else {}
            if not previous.get("first_seen_at"):
                previous = {**previous, "first_seen_at": now.isoformat()}
                state_alerts[code] = previous
                state_changed = True
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
            if state_changed:
                state["updated_at"] = now.isoformat()
                self._write_state(state)
            return {"status": "cooldown", "alerts_count": len(alerts), "sent": 0}

        digest_enabled = bool(config.get("warning_digest_enabled")) and not force
        warning_digest_minutes = max(1, int(config.get("warning_digest_minutes") or 240))
        warning_digest_window = timedelta(minutes=warning_digest_minutes)
        warning_digest_state = state.setdefault("warning_digest", {})
        if not isinstance(warning_digest_state, dict):
            warning_digest_state = {}
            state["warning_digest"] = warning_digest_state

        immediate_alerts = [
            item
            for item in sendable
            if not digest_enabled or str(item.get("severity") or "warning") == "critical"
        ]
        digest_alerts = [
            item
            for item in sendable
            if digest_enabled and str(item.get("severity") or "warning") != "critical"
        ]

        digest_sendable: list[dict[str, Any]] = []
        if digest_alerts:
            digest_fingerprint = "|".join(
                f"{item.get('code')}:{item.get('fingerprint')}"
                for item in sorted(digest_alerts, key=lambda item: str(item.get("code") or ""))
            )
            last_digest_at = self._parse_datetime(warning_digest_state.get("last_sent_at"))
            digest_due = last_digest_at is None or (now - last_digest_at) >= warning_digest_window
            if digest_due:
                digest_sendable = digest_alerts
                warning_digest_state["fingerprint"] = digest_fingerprint
                warning_digest_state["last_sent_at"] = now.isoformat()
                warning_digest_state["alerts_count"] = len(digest_alerts)
                state_changed = True

        messages: list[dict[str, Any]] = []
        if immediate_alerts:
            severity = "critical" if any(item.get("severity") == "critical" for item in immediate_alerts) else "warning"
            lines = []
            for item in immediate_alerts:
                lines.append(f"- [{item['severity']}] {item['message']}")
                if item.get("action_url"):
                    lines.append(f"  → {item.get('action_label') or 'Открыть'}: {item['action_url']}")
            messages.append(
                {
                    "alerts": immediate_alerts,
                    "result": await TelegramNotificationService().notify_admin(
                        title="CryptoGLAME bridge alerts",
                        lines=[*lines, "", self.config_payload()["admin_portal_url"]],
                        severity=severity,
                    ),
                }
            )

        if digest_sendable:
            max_items = max(1, int(config.get("warning_digest_max_items") or 8))
            visible_alerts = digest_sendable[:max_items]
            hidden_count = max(0, len(digest_sendable) - len(visible_alerts))
            lines = [
                f"Warning digest за последние {warning_digest_minutes} мин: {len(digest_sendable)} активных событий.",
            ]
            for item in visible_alerts:
                lines.append(f"- [{item['severity']}] {item['message']}")
                if item.get("action_url"):
                    lines.append(f"  → {item.get('action_label') or 'Открыть'}: {item['action_url']}")
            if hidden_count:
                lines.append(f"... еще {hidden_count} warning-событий в админке.")
            messages.append(
                {
                    "alerts": digest_sendable,
                    "result": await TelegramNotificationService().notify_admin(
                        title="CryptoGLAME warning digest",
                        lines=[*lines, "", self.config_payload()["admin_portal_url"]],
                        severity="warning",
                    ),
                }
            )

        if not messages:
            if state_changed:
                state["updated_at"] = now.isoformat()
                self._write_state(state)
            return {
                "status": "digest_cooldown",
                "alerts_count": len(alerts),
                "sendable_count": len(sendable),
                "sent": 0,
                "digest": {
                    "enabled": digest_enabled,
                    "suppressed_count": len(digest_alerts),
                    "window_minutes": warning_digest_minutes,
                },
                "alerts": alerts,
            }

        sent = 0
        errors: list[str] = []
        statuses: list[str] = []
        delivered_alerts: list[dict[str, Any]] = []
        for message in messages:
            result = message["result"]
            statuses.append(str(result.get("status") or "unknown"))
            sent += int(result.get("sent") or 0)
            errors.extend(result.get("errors") or [])
            if result.get("status") in {"success", "partial"}:
                delivered_alerts.extend(message["alerts"])

        if delivered_alerts:
            for alert in delivered_alerts:
                previous = state_alerts.get(str(alert["code"]))
                first_seen_at = previous.get("first_seen_at") if isinstance(previous, dict) else None
                state_alerts[str(alert["code"])] = {
                    "fingerprint": alert.get("fingerprint"),
                    "first_seen_at": first_seen_at or now.isoformat(),
                    "last_sent_at": now.isoformat(),
                    "severity": alert.get("severity"),
                    "message": alert.get("message"),
                }
            state["updated_at"] = now.isoformat()
            self._write_state(state)
        elif state_changed:
            state["updated_at"] = now.isoformat()
            self._write_state(state)

        if not statuses:
            status = "skipped"
        elif all(item == "success" for item in statuses):
            status = "success"
        elif any(item in {"success", "partial"} for item in statuses):
            status = "partial"
        else:
            status = statuses[0]

        return {
            "status": status,
            "alerts_count": len(alerts),
            "sendable_count": len(sendable),
            "immediate_count": len(immediate_alerts),
            "digest_count": len(digest_sendable),
            "digest_suppressed_count": max(0, len(digest_alerts) - len(digest_sendable)),
            "sent": sent,
            "errors": errors,
            "alerts": alerts,
        }
