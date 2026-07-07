from __future__ import annotations

import asyncio
import base64
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from tonsdk.boc import Cell
from tonsdk.utils import Address
from sqlalchemy import desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.glame_token import GlameTokenBridgeOperation, GlameTokenTransaction, GlameTreasuryRefillCheck
from app.services.glame_token_service import GlameTokenService, JETTON_TRANSFER_OP
from app.services.ton_glm_auto_transfer_service import TonGlmAutoTransferService


def _env_bool(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _decimal_env(name: str, default: str) -> Decimal:
    try:
        return Decimal(str(os.getenv(name, default) or default))
    except Exception:
        return Decimal(default)


def _float_decimal(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.000000001")).normalize())


def _nullable_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


class TonGlmTreasuryBalanceService:
    """On-chain balance health for GLM treasury and hot-wallets."""

    LIMITS_FILE = Path(__file__).resolve().parents[2] / "static" / "glm_policy" / "hot-wallet-limits.json"

    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_refill_check_table(self) -> None:
        await self.db.execute(text(
            """
            CREATE TABLE IF NOT EXISTS glame_treasury_refill_checks (
                id UUID PRIMARY KEY,
                event_type VARCHAR(32) NOT NULL DEFAULT 'balance_check',
                status VARCHAR(32) NOT NULL,
                reason VARCHAR(64),
                network VARCHAR(32),
                treasury_address VARCHAR(128),
                hot_wallet_address VARCHAR(128),
                ton_tx_hash VARCHAR(128),
                refill_glm_amount NUMERIC(20, 9),
                refill_ton_amount NUMERIC(20, 9),
                manual_glm_amount NUMERIC(20, 9),
                manual_ton_amount NUMERIC(20, 9),
                hot_wallet_glm_balance NUMERIC(20, 9),
                hot_wallet_ton_balance NUMERIC(20, 9),
                treasury_glm_balance NUMERIC(20, 9),
                treasury_ton_balance NUMERIC(20, 9),
                target_glm NUMERIC(20, 9),
                target_ton NUMERIC(20, 9),
                threshold_glm NUMERIC(20, 9),
                threshold_ton NUMERIC(20, 9),
                errors JSONB,
                payload JSONB,
                comment TEXT,
                created_by UUID REFERENCES users(id),
                created_at TIMESTAMPTZ DEFAULT now()
            )
            """
        ))
        for statement in (
            "CREATE INDEX IF NOT EXISTS ix_glame_treasury_refill_checks_event_type ON glame_treasury_refill_checks (event_type)",
            "CREATE INDEX IF NOT EXISTS ix_glame_treasury_refill_checks_status ON glame_treasury_refill_checks (status)",
            "CREATE INDEX IF NOT EXISTS ix_glame_treasury_refill_checks_reason ON glame_treasury_refill_checks (reason)",
            "CREATE INDEX IF NOT EXISTS ix_glame_treasury_refill_checks_network ON glame_treasury_refill_checks (network)",
            "CREATE INDEX IF NOT EXISTS ix_glame_treasury_refill_checks_treasury_address ON glame_treasury_refill_checks (treasury_address)",
            "CREATE INDEX IF NOT EXISTS ix_glame_treasury_refill_checks_hot_wallet_address ON glame_treasury_refill_checks (hot_wallet_address)",
            "CREATE INDEX IF NOT EXISTS ix_glame_treasury_refill_checks_ton_tx_hash ON glame_treasury_refill_checks (ton_tx_hash)",
            "CREATE INDEX IF NOT EXISTS ix_glame_treasury_refill_checks_created_by ON glame_treasury_refill_checks (created_by)",
            "CREATE INDEX IF NOT EXISTS ix_glame_treasury_refill_checks_created_at ON glame_treasury_refill_checks (created_at)",
            "CREATE INDEX IF NOT EXISTS ix_glame_treasury_refill_checks_event_created ON glame_treasury_refill_checks (event_type, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_glame_treasury_refill_checks_status_created ON glame_treasury_refill_checks (status, created_at)",
        ):
            await self.db.execute(text(statement))

    @classmethod
    def limits_override_payload(cls) -> dict[str, Any]:
        if not cls.LIMITS_FILE.exists():
            return {"exists": False}
        try:
            payload = json.loads(cls.LIMITS_FILE.read_text(encoding="utf-8"))
        except Exception as error:
            return {"exists": True, "error": str(error)}
        return payload if isinstance(payload, dict) else {"exists": True, "error": "limits payload must be an object"}

    @classmethod
    def write_limits_override(
        cls,
        *,
        hot_wallet_refill_glm_threshold: Decimal,
        hot_wallet_refill_ton_threshold: Decimal,
        hot_wallet_refill_glm_target: Decimal,
        hot_wallet_refill_ton_target: Decimal,
        admin_user_id: Any,
    ) -> dict[str, Any]:
        cls.LIMITS_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "exists": True,
            "hot_wallet_refill_glm_threshold": _float_decimal(hot_wallet_refill_glm_threshold),
            "hot_wallet_refill_ton_threshold": _float_decimal(hot_wallet_refill_ton_threshold),
            "hot_wallet_refill_glm_target": _float_decimal(hot_wallet_refill_glm_target),
            "hot_wallet_refill_ton_target": _float_decimal(hot_wallet_refill_ton_target),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": str(admin_user_id),
        }
        cls.LIMITS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return cls.limits_override_payload()

    @staticmethod
    def config_payload() -> dict[str, Any]:
        auto_transfer = TonGlmAutoTransferService.config_payload()
        limits_override = TonGlmTreasuryBalanceService.limits_override_payload()

        def limit_value(key: str, env_name: str, default: str) -> Decimal:
            value = limits_override.get(key) if isinstance(limits_override, dict) else None
            if value is None:
                return _decimal_env(env_name, default)
            try:
                return Decimal(str(value))
            except Exception:
                return _decimal_env(env_name, default)

        return {
            "enabled": _env_bool("TON_GLM_TREASURY_BALANCE_ALERTS_ENABLED", "true"),
            "critical_only": _env_bool("TON_GLM_TREASURY_BALANCE_CRITICAL_ONLY", "false"),
            "network": os.getenv("TON_NETWORK", "testnet").strip() or "testnet",
            "glm_buffer": _float_decimal(_decimal_env("TON_GLM_TREASURY_GLM_BUFFER", "100")),
            "ton_buffer": _float_decimal(_decimal_env("TON_GLM_TREASURY_TON_BUFFER", "0.2")),
            "hot_wallet_refill_glm_threshold": _float_decimal(
                limit_value(
                    "hot_wallet_refill_glm_threshold",
                    "TON_GLM_HOT_WALLET_REFILL_GLM_THRESHOLD",
                    "5000",
                )
            ),
            "hot_wallet_refill_ton_threshold": _float_decimal(
                limit_value(
                    "hot_wallet_refill_ton_threshold",
                    "TON_GLM_HOT_WALLET_REFILL_TON_THRESHOLD",
                    "0.5",
                )
            ),
            "hot_wallet_refill_glm_target": _float_decimal(
                limit_value(
                    "hot_wallet_refill_glm_target",
                    "TON_GLM_HOT_WALLET_REFILL_GLM_TARGET",
                    "5000",
                )
            ),
            "hot_wallet_refill_ton_target": _float_decimal(
                limit_value(
                    "hot_wallet_refill_ton_target",
                    "TON_GLM_HOT_WALLET_REFILL_TON_TARGET",
                    "2",
                )
            ),
            "limits_override": limits_override,
            "tx_value_nanoton": int(auto_transfer.get("tx_value_nanoton") or 0),
            "hot_wallet_address": auto_transfer.get("hot_wallet_address"),
            "treasury_address": (os.getenv("TON_GLM_TREASURY_ADDRESS") or "").strip() or None,
            "production_hot_wallet_address": auto_transfer.get("production_hot_wallet_address"),
        }

    @staticmethod
    def _toncenter_v2_base() -> str:
        network = os.getenv("TON_NETWORK", "testnet").strip() or "testnet"
        return (
            os.getenv("TONCENTER_API_BASE_URL")
            or ("https://testnet.toncenter.com/api/v2" if network == "testnet" else "https://toncenter.com/api/v2")
        ).rstrip("/")

    @staticmethod
    def _headers() -> dict[str, str]:
        api_key = (os.getenv("TONCENTER_API_KEY") or os.getenv("TON_API_KEY") or "").strip()
        return {"X-API-Key": api_key} if api_key else {}

    async def _ton_balance(self, address: str | None) -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc).isoformat()
        if not address:
            return {"status": "not_configured", "balance_ton": 0.0, "balance_nanoton": "0", "checked_at": checked_at}
        last_error: Exception | None = None
        headers_options = [self._headers()]
        if headers_options[0]:
            headers_options.append({})
        for attempt in range(3):
            for headers in headers_options:
                try:
                    async with httpx.AsyncClient(timeout=12.0) as client:
                        response = await client.get(
                            f"{self._toncenter_v2_base()}/getAddressBalance",
                            params={"address": address},
                            headers=headers,
                        )
                        response.raise_for_status()
                    payload = response.json()
                    raw = str(payload.get("result") or "0")
                    ton = Decimal(raw) / Decimal("1000000000")
                    return {
                        "status": "ok",
                        "source": "toncenter_v2",
                        "balance_nanoton": raw,
                        "balance_ton": _float_decimal(ton),
                        "checked_at": checked_at,
                    }
                except httpx.HTTPStatusError as error:
                    last_error = error
                    if error.response.status_code in {401, 403} and headers:
                        continue
                    if "429" not in str(error) or attempt == 2:
                        return {
                            "status": "error",
                            "source": "toncenter_v2",
                            "balance_nanoton": "0",
                            "balance_ton": 0.0,
                            "checked_at": checked_at,
                            "error": str(last_error) if last_error else "unknown_error",
                        }
                except Exception as error:
                    last_error = error
                    if "429" not in str(error) or attempt == 2:
                        return {
                            "status": "error",
                            "source": "toncenter_v2",
                            "balance_nanoton": "0",
                            "balance_ton": 0.0,
                            "checked_at": checked_at,
                            "error": str(last_error) if last_error else "unknown_error",
                        }
                await asyncio.sleep(1.2 * (attempt + 1))
        return {
            "status": "error",
            "source": "toncenter_v2",
            "balance_nanoton": "0",
            "balance_ton": 0.0,
            "checked_at": checked_at,
            "error": str(last_error) if last_error else "unknown_error",
        }

    async def _glm_balance(self, address: str) -> dict[str, Any]:
        last_payload: dict[str, Any] | None = None
        for attempt in range(3):
            payload = await GlameTokenService(self.db).ton_wallet_glm_balance(address)
            last_payload = payload
            error = str(payload.get("error") or "")
            if payload.get("status") != "error" or "429" not in error or attempt == 2:
                return payload
            await asyncio.sleep(1.2 * (attempt + 1))
        return last_payload or {"status": "error", "error": "unknown_error"}

    async def _pending_points_to_glm_requirement(self) -> dict[str, Any]:
        legacy_conditions = [
            GlameTokenTransaction.token_code == "GLM",
            GlameTokenTransaction.transaction_type == "claim",
            GlameTokenTransaction.status == "pending",
            GlameTokenTransaction.reason.in_(("points_to_ton_bridge", "points_to_glm_bridge")),
        ]
        legacy_total, legacy_count = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(GlameTokenTransaction.amount), 0),
                    func.count(GlameTokenTransaction.id),
                ).where(*legacy_conditions)
            )
        ).one()
        operation_total, operation_count = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(GlameTokenBridgeOperation.glm_amount), 0),
                    func.count(GlameTokenBridgeOperation.id),
                ).where(
                    GlameTokenBridgeOperation.token_code == "GLM",
                    GlameTokenBridgeOperation.direction.in_(("points_to_glm", "points_to_ton")),
                    GlameTokenBridgeOperation.status == "pending",
                    or_(
                        GlameTokenBridgeOperation.ton_status.is_(None),
                        GlameTokenBridgeOperation.ton_status.in_(
                            ("not_started", "sent", "sent_waiting_settlement", "blocked_hot_wallet_balance")
                        ),
                    ),
                )
            )
        ).one()

        pending_amount = max(int(legacy_total or 0), int(operation_total or 0))
        pending_count = max(int(legacy_count or 0), int(operation_count or 0))
        glm_buffer = _decimal_env("TON_GLM_TREASURY_GLM_BUFFER", "100")
        ton_buffer = _decimal_env("TON_GLM_TREASURY_TON_BUFFER", "0.2")
        tx_value_nanoton = Decimal(str(TonGlmAutoTransferService.config_payload().get("tx_value_nanoton") or 0))
        required_ton = (Decimal(pending_count) * tx_value_nanoton / Decimal("1000000000")) + ton_buffer
        return {
            "pending_points_to_glm_count": pending_count,
            "pending_points_to_glm_amount_glm": pending_amount,
            "legacy_pending_count": int(legacy_count or 0),
            "legacy_pending_amount_glm": int(legacy_total or 0),
            "domain_pending_count": int(operation_count or 0),
            "domain_pending_amount_glm": int(operation_total or 0),
            "required_glm": _float_decimal(Decimal(pending_amount) + glm_buffer),
            "required_ton": _float_decimal(required_ton),
            "glm_buffer": _float_decimal(glm_buffer),
            "ton_buffer": _float_decimal(ton_buffer),
        }

    @staticmethod
    def _role_requirement(
        role: str,
        requirements: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> tuple[Decimal, Decimal]:
        if role == "hot_wallet":
            config = config or {}
            return (
                max(
                    Decimal(str(requirements["required_glm"])),
                    Decimal(str(config.get("hot_wallet_refill_glm_threshold") or 0)),
                ),
                max(
                    Decimal(str(requirements["required_ton"])),
                    Decimal(str(config.get("hot_wallet_refill_ton_threshold") or 0)),
                ),
            )
        if role == "treasury":
            return _decimal_env("TON_GLM_TREASURY_GLM_BUFFER", "100"), _decimal_env("TON_GLM_TREASURY_TON_BUFFER", "0.2")
        return Decimal("0"), Decimal("0")

    async def _wallet_payload(
        self,
        *,
        role: str,
        address: str | None,
        requirements: dict[str, Any],
        config: dict[str, Any],
        onchain_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc).isoformat()
        if not address:
            return {
                "role": role,
                "address": None,
                "network": os.getenv("TON_NETWORK", "testnet"),
                "glm_balance": 0.0,
                "ton_balance": 0.0,
                "jetton_wallet_address": None,
                "status": "not_configured",
                "checked_at": checked_at,
                "errors": ["address_not_configured"],
            }

        if onchain_payload is None:
            onchain_payload = {
                "glm": await GlameTokenService(self.db).ton_wallet_glm_balance(address),
                "ton": await self._ton_balance(address),
            }
        glm_payload = onchain_payload.get("glm") or {}
        ton_payload = onchain_payload.get("ton") or {}
        errors: list[str] = []
        glm_balance = Decimal("0")
        ton_balance = Decimal("0")
        try:
            glm_balance = Decimal(str(glm_payload.get("balance_glm") or "0"))
        except Exception:
            errors.append("glm_balance_parse_error")
        try:
            ton_balance = Decimal(str(ton_payload.get("balance_ton") or "0"))
        except Exception:
            errors.append("ton_balance_parse_error")
        if glm_payload.get("status") not in {"ok", "no_wallet"}:
            errors.append(f"glm:{glm_payload.get('status')}")
        if ton_payload.get("status") != "ok":
            errors.append(f"ton:{ton_payload.get('status')}")

        required_glm, required_ton = self._role_requirement(role, requirements, config)
        glm_buffer = _decimal_env("TON_GLM_TREASURY_GLM_BUFFER", "100")
        ton_buffer = _decimal_env("TON_GLM_TREASURY_TON_BUFFER", "0.2")
        safe_transfer_capacity_glm = max(Decimal("0"), glm_balance - glm_buffer) if role == "hot_wallet" else Decimal("0")
        safe_transfer_capacity_ton = max(Decimal("0"), ton_balance - ton_buffer) if role == "hot_wallet" else Decimal("0")
        status = "ok"
        if errors:
            status = "error"
        elif role in {"hot_wallet", "treasury"}:
            if glm_balance < (Decimal(str(requirements["pending_points_to_glm_amount_glm"])) if role == "hot_wallet" else Decimal("0")):
                status = "critical"
            elif ton_balance < (required_ton - _decimal_env("TON_GLM_TREASURY_TON_BUFFER", "0.2")) and role == "hot_wallet":
                status = "critical"
            elif glm_balance < required_glm or ton_balance < required_ton:
                status = "warning"

        return {
            "role": role,
            "address": address,
            "network": os.getenv("TON_NETWORK", "testnet"),
            "glm_balance": _float_decimal(glm_balance),
            "ton_balance": _float_decimal(ton_balance),
            "jetton_wallet_address": glm_payload.get("jetton_wallet_address"),
            "required_glm": _float_decimal(required_glm),
            "required_ton": _float_decimal(required_ton),
            "safe_transfer_capacity_glm": _float_decimal(safe_transfer_capacity_glm),
            "safe_transfer_capacity_ton": _float_decimal(safe_transfer_capacity_ton),
            "refill_threshold_glm": config.get("hot_wallet_refill_glm_threshold") if role == "hot_wallet" else None,
            "refill_threshold_ton": config.get("hot_wallet_refill_ton_threshold") if role == "hot_wallet" else None,
            "refill_target_glm": config.get("hot_wallet_refill_glm_target") if role == "hot_wallet" else None,
            "refill_target_ton": config.get("hot_wallet_refill_ton_target") if role == "hot_wallet" else None,
            "status": status,
            "checked_at": checked_at,
            "errors": errors,
            "glm_balance_payload": {
                "status": glm_payload.get("status"),
                "source": glm_payload.get("source"),
                "balance_raw": glm_payload.get("balance_raw"),
                "error": glm_payload.get("error"),
            },
            "ton_balance_payload": {
                "status": ton_payload.get("status"),
                "source": ton_payload.get("source"),
                "balance_nanoton": ton_payload.get("balance_nanoton"),
                "error": ton_payload.get("error"),
            },
        }

    @staticmethod
    def _wallet_addresses(config: dict[str, Any]) -> list[tuple[str, str | None]]:
        wallets = [
            ("hot_wallet", config.get("hot_wallet_address")),
            ("treasury", config.get("treasury_address")),
        ]
        if config.get("production_hot_wallet_address") and config.get("network") == "mainnet":
            wallets.append(("production_candidate", config.get("production_hot_wallet_address")))
        return wallets

    @staticmethod
    def refill_plan_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
        """Manual top-up plan from treasury/deposit wallet to hot-wallet."""
        config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
        wallets = payload.get("wallets") if isinstance(payload.get("wallets"), list) else []
        wallet_by_role = {
            str(item.get("role")): item
            for item in wallets
            if isinstance(item, dict)
        }
        hot_wallet = wallet_by_role.get("hot_wallet") or {}
        treasury = wallet_by_role.get("treasury") or {}
        now = datetime.now(timezone.utc).isoformat()
        if not hot_wallet.get("address"):
            return {
                "status": "not_configured",
                "checked_at": now,
                "required": False,
                "reason": "hot_wallet_address_missing",
                "errors": ["hot_wallet_address_missing"],
            }
        if not treasury.get("address"):
            return {
                "status": "not_configured",
                "checked_at": now,
                "required": False,
                "reason": "treasury_address_missing",
                "errors": ["treasury_address_missing"],
            }

        hot_glm = Decimal(str(hot_wallet.get("glm_balance") or 0))
        hot_ton = Decimal(str(hot_wallet.get("ton_balance") or 0))
        treasury_glm = Decimal(str(treasury.get("glm_balance") or 0))
        treasury_ton = Decimal(str(treasury.get("ton_balance") or 0))
        glm_threshold = Decimal(str(config.get("hot_wallet_refill_glm_threshold") or 0))
        ton_threshold = Decimal(str(config.get("hot_wallet_refill_ton_threshold") or 0))
        glm_refill_batch = Decimal(str(config.get("hot_wallet_refill_glm_target") or glm_threshold))
        ton_refill_target = Decimal(str(config.get("hot_wallet_refill_ton_target") or ton_threshold))
        treasury_glm_buffer = Decimal(str(config.get("glm_buffer") or 0))
        treasury_ton_buffer = Decimal(str(config.get("ton_buffer") or 0))

        # GLM refill is a fixed batch: when hot-wallet drops below the threshold,
        # we send a full batch instead of topping up only the exact shortage.
        refill_glm = max(Decimal("0"), glm_refill_batch) if hot_glm < glm_threshold else Decimal("0")
        refill_ton = max(Decimal("0"), ton_refill_target - hot_ton) if hot_ton < ton_threshold else Decimal("0")
        required = refill_glm > 0 or refill_ton > 0
        errors: list[str] = []
        if refill_glm > 0 and treasury_glm < refill_glm + treasury_glm_buffer:
            errors.append("treasury_glm_insufficient")
        if refill_ton > 0 and treasury_ton < refill_ton + treasury_ton_buffer:
            errors.append("treasury_ton_insufficient")

        status = "ok"
        if required and errors:
            status = "blocked"
        elif required:
            status = "ready"
        approval_policy = TonGlmTreasuryBalanceService.two_step_refill_policy()
        approval_required = bool(
            required
            and approval_policy.get("enabled")
            and (
                not approval_policy.get("mainnet_only")
                or str(config.get("network") or "").strip() == "mainnet"
            )
            and (
                refill_glm >= Decimal(str(approval_policy.get("glm_threshold") or 0))
                or refill_ton >= Decimal(str(approval_policy.get("ton_threshold") or 0))
            )
        )
        return {
            "status": status,
            "checked_at": now,
            "required": required,
            "reason": "below_refill_threshold" if required else "hot_wallet_above_threshold",
            "approval_required": approval_required,
            "approval_reason": "two_step_required" if approval_required else None,
            "approval_policy": approval_policy,
            "network": config.get("network"),
            "source_role": "treasury",
            "source_address": treasury.get("address"),
            "destination_role": "hot_wallet",
            "destination_address": hot_wallet.get("address"),
            "refill_glm_amount": _float_decimal(refill_glm),
            "refill_ton_amount": _float_decimal(refill_ton),
            "hot_wallet_glm_balance": _float_decimal(hot_glm),
            "hot_wallet_ton_balance": _float_decimal(hot_ton),
            "treasury_glm_balance": _float_decimal(treasury_glm),
            "treasury_ton_balance": _float_decimal(treasury_ton),
            "target_glm": _float_decimal(glm_refill_batch),
            "target_ton": _float_decimal(ton_refill_target),
            "target_mode_glm": "fixed_refill_batch",
            "target_mode_ton": "top_up_to_target",
            "threshold_glm": _float_decimal(glm_threshold),
            "threshold_ton": _float_decimal(ton_threshold),
            "errors": errors,
            "instructions": [
                "Send refill_glm_amount GLM from treasury to hot-wallet Jetton address/wallet.",
                "Send refill_ton_amount TON from treasury or faucet to hot-wallet if TON gas is below threshold.",
                "After transfer confirmation, run treasury balance check again.",
            ],
        }

    async def payload(self) -> dict[str, Any]:
        config = self.config_payload()
        requirements = await self._pending_points_to_glm_requirement()
        onchain_cache: dict[str, dict[str, Any]] = {}
        wallets = []
        for role, address in self._wallet_addresses(config):
            cached = None
            if address:
                cached = onchain_cache.get(address)
                if cached is None:
                    cached = {
                        "glm": await self._glm_balance(address),
                        "ton": await self._ton_balance(address),
                    }
                    onchain_cache[address] = cached
            wallets.append(
                await self._wallet_payload(
                    role=role,
                    address=address,
                    requirements=requirements,
                    config=config,
                    onchain_payload=cached,
                )
            )
        partial_payload = {"wallets": wallets, "requirements": requirements, "config": config}
        refill_plan = self.refill_plan_from_payload(partial_payload)
        alerts = self.alerts_from_payload(partial_payload)
        return {
            "status": "critical" if any(item["severity"] == "critical" for item in alerts) else ("warning" if alerts else "ok"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "config": config,
            "requirements": requirements,
            "wallets": wallets,
            "refill_plan": refill_plan,
            "alerts": alerts,
        }

    async def prepare_refill_ton_connect_transaction(self, *, approval_id: Any | None = None) -> dict[str, Any]:
        payload = await self.payload()
        plan = payload.get("refill_plan") if isinstance(payload.get("refill_plan"), dict) else {}
        config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
        if plan.get("status") not in {"ready", "ok"}:
            raise ValueError("Refill plan не готов к отправке")
        if plan.get("status") == "ok" or not plan.get("required"):
            raise ValueError("Пополнение hot-wallet сейчас не требуется")
        source_address = str(plan.get("source_address") or "").strip()
        destination_address = str(plan.get("destination_address") or "").strip()
        if not source_address or not destination_address:
            raise ValueError("Treasury или hot-wallet address не настроен")

        network = str(config.get("network") or os.getenv("TON_NETWORK", "testnet") or "testnet").strip()
        if network == "mainnet" and not _env_bool("TON_GLM_MAINNET_REFILL_TON_CONNECT_ENABLED", "false"):
            raise ValueError("Mainnet TON Connect refill выключен: задайте TON_GLM_MAINNET_REFILL_TON_CONNECT_ENABLED=true")
        if network not in {"testnet", "mainnet"}:
            raise ValueError("TON Connect refill поддерживает только testnet/mainnet")

        refill_glm = Decimal(str(plan.get("refill_glm_amount") or 0))
        refill_ton = Decimal(str(plan.get("refill_ton_amount") or 0))
        if refill_glm <= 0 and refill_ton <= 0:
            raise ValueError("В refill plan нет суммы для отправки")
        approval_payload = await self.validate_refill_approval(approval_id, plan=plan, config=config)

        messages: list[dict[str, str]] = []
        decimals = int(os.getenv("TON_GLM_DECIMALS", "9") or 9)
        query_id = int(datetime.now(timezone.utc).timestamp())
        glm_tx_value = int(os.getenv("TON_GLM_REFILL_TRANSFER_TX_VALUE_NANOTON", os.getenv("TON_GLM_TRANSFER_TX_VALUE_NANOTON", "30000000")) or 30_000_000)
        forward_ton_amount = int(os.getenv("TON_GLM_TRANSFER_FORWARD_NANOTON", "1") or 1)

        if refill_glm > 0:
            wallets = payload.get("wallets") if isinstance(payload.get("wallets"), list) else []
            wallet_by_role = {
                str(item.get("role")): item
                for item in wallets
                if isinstance(item, dict)
            }
            treasury_wallet_payload = wallet_by_role.get("treasury") or {}
            source_jetton_wallet = str(treasury_wallet_payload.get("jetton_wallet_address") or "").strip()
            treasury_glm_balance = treasury_wallet_payload.get("glm_balance_payload") or {}
            if not source_jetton_wallet:
                treasury_glm_balance = await self._glm_balance(source_address)
                source_jetton_wallet = str(treasury_glm_balance.get("jetton_wallet_address") or "").strip()
            if not source_jetton_wallet:
                status = treasury_glm_balance.get("status") if isinstance(treasury_glm_balance, dict) else None
                error = treasury_glm_balance.get("error") if isinstance(treasury_glm_balance, dict) else None
                detail = f": {status or 'unknown'}"
                if error:
                    detail = f"{detail} ({error})"
                raise ValueError(f"Не удалось найти GLM Jetton Wallet для treasury{detail}")
            amount_base_units = int(refill_glm * Decimal(10 ** decimals))

            forward_payload = Cell()
            forward_payload.bits.write_uint(0, 32)
            forward_payload.bits.write_string("GLAME hot-wallet refill")

            body = Cell()
            body.bits.write_uint(JETTON_TRANSFER_OP, 32)
            body.bits.write_uint(query_id, 64)
            body.bits.write_coins(amount_base_units)
            body.bits.write_address(Address(destination_address))
            body.bits.write_address(Address(source_address))
            body.bits.write_bit(0)
            body.bits.write_coins(forward_ton_amount)
            body.bits.write_bit(1)
            body.refs.append(forward_payload)
            messages.append(
                {
                    "address": source_jetton_wallet,
                    "amount": str(glm_tx_value),
                    "payload": base64.b64encode(body.to_boc(False)).decode("ascii"),
                }
            )

        if refill_ton > 0:
            amount_nanoton = int(refill_ton * Decimal("1000000000"))
            messages.append(
                {
                    "address": destination_address,
                    "amount": str(amount_nanoton),
                }
            )

        valid_until = int(datetime.now(timezone.utc).timestamp()) + int(os.getenv("TON_GLM_CONNECT_TX_TTL_SECONDS", "600") or 600)
        return {
            "status": "ready",
            "network": network,
            "source_address": source_address,
            "destination_address": destination_address,
            "refill_glm_amount": _float_decimal(refill_glm),
            "refill_ton_amount": _float_decimal(refill_ton),
            "query_id": str(query_id),
            "transaction": {
                "validUntil": valid_until,
                "network": "-239" if network == "mainnet" else "-3",
                "messages": messages,
            },
            "refill_plan": plan,
            "approval": approval_payload,
            "treasury_balances": payload,
            "note": "Проверьте в кошельке, что отправитель - treasury GLAME, а получатель refill - hot-wallet GLAME.",
        }

    async def record_refill_check(
        self,
        payload: dict[str, Any],
        *,
        admin_user_id: Any | None = None,
        event_type: str = "balance_check",
        manual_glm_amount: Decimal | int | float | str | None = None,
        manual_ton_amount: Decimal | int | float | str | None = None,
        ton_tx_hash: str | None = None,
        comment: str | None = None,
    ) -> GlameTreasuryRefillCheck:
        await self.ensure_refill_check_table()
        plan = payload.get("refill_plan") if isinstance(payload.get("refill_plan"), dict) else {}
        item = GlameTreasuryRefillCheck(
            event_type=event_type,
            status=str(plan.get("status") or payload.get("status") or "unknown"),
            reason=plan.get("reason"),
            network=plan.get("network") or (payload.get("config") or {}).get("network"),
            treasury_address=plan.get("source_address"),
            hot_wallet_address=plan.get("destination_address"),
            ton_tx_hash=(ton_tx_hash or "").strip() or None,
            refill_glm_amount=_nullable_decimal(plan.get("refill_glm_amount")),
            refill_ton_amount=_nullable_decimal(plan.get("refill_ton_amount")),
            manual_glm_amount=_nullable_decimal(manual_glm_amount),
            manual_ton_amount=_nullable_decimal(manual_ton_amount),
            hot_wallet_glm_balance=_nullable_decimal(plan.get("hot_wallet_glm_balance")),
            hot_wallet_ton_balance=_nullable_decimal(plan.get("hot_wallet_ton_balance")),
            treasury_glm_balance=_nullable_decimal(plan.get("treasury_glm_balance")),
            treasury_ton_balance=_nullable_decimal(plan.get("treasury_ton_balance")),
            target_glm=_nullable_decimal(plan.get("target_glm")),
            target_ton=_nullable_decimal(plan.get("target_ton")),
            threshold_glm=_nullable_decimal(plan.get("threshold_glm")),
            threshold_ton=_nullable_decimal(plan.get("threshold_ton")),
            errors=plan.get("errors") or [],
            payload=payload,
            comment=(comment or "").strip() or None,
            created_by=admin_user_id,
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    @staticmethod
    def refill_check_payload(item: GlameTreasuryRefillCheck) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "event_type": item.event_type,
            "status": item.status,
            "reason": item.reason,
            "network": item.network,
            "treasury_address": item.treasury_address,
            "hot_wallet_address": item.hot_wallet_address,
            "ton_tx_hash": item.ton_tx_hash,
            "refill_glm_amount": _float_decimal(item.refill_glm_amount) if item.refill_glm_amount is not None else None,
            "refill_ton_amount": _float_decimal(item.refill_ton_amount) if item.refill_ton_amount is not None else None,
            "manual_glm_amount": _float_decimal(item.manual_glm_amount) if item.manual_glm_amount is not None else None,
            "manual_ton_amount": _float_decimal(item.manual_ton_amount) if item.manual_ton_amount is not None else None,
            "hot_wallet_glm_balance": _float_decimal(item.hot_wallet_glm_balance) if item.hot_wallet_glm_balance is not None else None,
            "hot_wallet_ton_balance": _float_decimal(item.hot_wallet_ton_balance) if item.hot_wallet_ton_balance is not None else None,
            "treasury_glm_balance": _float_decimal(item.treasury_glm_balance) if item.treasury_glm_balance is not None else None,
            "treasury_ton_balance": _float_decimal(item.treasury_ton_balance) if item.treasury_ton_balance is not None else None,
            "target_glm": _float_decimal(item.target_glm) if item.target_glm is not None else None,
            "target_ton": _float_decimal(item.target_ton) if item.target_ton is not None else None,
            "threshold_glm": _float_decimal(item.threshold_glm) if item.threshold_glm is not None else None,
            "threshold_ton": _float_decimal(item.threshold_ton) if item.threshold_ton is not None else None,
            "errors": item.errors or [],
            "comment": item.comment,
            "created_by": str(item.created_by) if item.created_by else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "payload": item.payload or {},
        }

    async def refill_check_history(self, *, limit: int = 50) -> dict[str, Any]:
        await self.ensure_refill_check_table()
        rows = (
            await self.db.execute(
                select(GlameTreasuryRefillCheck)
                .order_by(desc(GlameTreasuryRefillCheck.created_at))
                .limit(max(1, min(int(limit or 50), 200)))
            )
        ).scalars().all()
        return {
            "count": len(rows),
            "items": [self.refill_check_payload(item) for item in rows],
        }

    async def refill_activity_since(self, since: datetime) -> dict[str, Any]:
        await self.ensure_refill_check_table()
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        rows = (
            await self.db.execute(
                select(GlameTreasuryRefillCheck)
                .where(GlameTreasuryRefillCheck.created_at >= since)
                .order_by(desc(GlameTreasuryRefillCheck.created_at))
                .limit(50)
            )
        ).scalars().all()
        manual_refill = next((item for item in rows if item.event_type == "manual_refill"), None)
        recovered_check = next(
            (
                item
                for item in rows
                if item.event_type == "balance_check"
                and item.status == "ok"
                and item.reason == "hot_wallet_above_threshold"
            ),
            None,
        )
        latest = rows[0] if rows else None
        return {
            "since": since.isoformat(),
            "count": len(rows),
            "has_manual_refill": manual_refill is not None,
            "has_recovered_check": recovered_check is not None,
            "has_recovery_activity": manual_refill is not None or recovered_check is not None,
            "manual_refill": self.refill_check_payload(manual_refill) if manual_refill else None,
            "recovered_check": self.refill_check_payload(recovered_check) if recovered_check else None,
            "latest": self.refill_check_payload(latest) if latest else None,
        }

    @staticmethod
    def two_step_refill_policy() -> dict[str, Any]:
        return {
            "enabled": _env_bool("TON_GLM_REFILL_TWO_STEP_ENABLED", "true"),
            "mainnet_only": _env_bool("TON_GLM_REFILL_TWO_STEP_MAINNET_ONLY", "true"),
            "glm_threshold": _float_decimal(_decimal_env("TON_GLM_REFILL_TWO_STEP_GLM_THRESHOLD", "5000")),
            "ton_threshold": _float_decimal(_decimal_env("TON_GLM_REFILL_TWO_STEP_TON_THRESHOLD", "2")),
        }

    @classmethod
    def refill_requires_two_step(cls, plan: dict[str, Any], config: dict[str, Any]) -> bool:
        policy = cls.two_step_refill_policy()
        if not policy.get("enabled"):
            return False
        network = str(plan.get("network") or config.get("network") or "").strip()
        if policy.get("mainnet_only") and network != "mainnet":
            return False
        refill_glm = Decimal(str(plan.get("refill_glm_amount") or 0))
        refill_ton = Decimal(str(plan.get("refill_ton_amount") or 0))
        return (
            refill_glm >= Decimal(str(policy.get("glm_threshold") or 0))
            or refill_ton >= Decimal(str(policy.get("ton_threshold") or 0))
        )

    async def create_refill_approval(
        self,
        *,
        admin_user_id: Any,
        comment: str | None = None,
    ) -> GlameTreasuryRefillCheck:
        payload = await self.payload()
        plan = payload.get("refill_plan") if isinstance(payload.get("refill_plan"), dict) else {}
        config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
        if plan.get("status") not in {"ready", "ok"} or not plan.get("required"):
            raise ValueError("Refill plan не требует пополнения")
        if not self.refill_requires_two_step(plan, config):
            raise ValueError("Для текущего refill plan two-step approval не требуется")
        item = await self.record_refill_check(
            payload,
            admin_user_id=admin_user_id,
            event_type="refill_approval",
            comment=(comment or "").strip() or "Refill approval requested.",
        )
        item.status = "pending"
        item.reason = "two_step_required"
        next_payload = dict(item.payload or {})
        next_payload["approval"] = {
            "status": "pending",
            "requested_by": str(admin_user_id),
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "policy": self.two_step_refill_policy(),
        }
        item.payload = next_payload
        flag_modified(item, "payload")
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def decide_refill_approval(
        self,
        approval_id: Any,
        *,
        admin_user_id: Any,
        approved: bool,
        comment: str | None = None,
    ) -> GlameTreasuryRefillCheck:
        await self.ensure_refill_check_table()
        item = (
            await self.db.execute(
                select(GlameTreasuryRefillCheck)
                .where(GlameTreasuryRefillCheck.id == approval_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if item is None or item.event_type != "refill_approval":
            raise ValueError("Refill approval не найден")
        if item.status != "pending":
            raise ValueError("Refill approval уже обработан")
        if (
            not _env_bool("TON_GLM_REFILL_TWO_STEP_ALLOW_SAME_ADMIN", "false")
            and item.created_by
            and str(item.created_by) == str(admin_user_id)
        ):
            raise ValueError("Two-step approval должен подтвердить другой администратор")
        item.status = "approved" if approved else "rejected"
        next_payload = dict(item.payload or {})
        approval_payload = dict(next_payload.get("approval") or {})
        approval_payload.update({
            "status": item.status,
            "decided_by": str(admin_user_id),
            "decided_at": datetime.now(timezone.utc).isoformat(),
            "decision_comment": (comment or "").strip() or None,
        })
        next_payload["approval"] = approval_payload
        item.payload = next_payload
        item.comment = (comment or item.comment or "").strip() or item.comment
        flag_modified(item, "payload")
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def validate_refill_approval(
        self,
        approval_id: Any | None,
        *,
        plan: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self.refill_requires_two_step(plan, config):
            return None
        if not approval_id:
            raise ValueError("Для крупного refill нужен two-step approval")
        await self.ensure_refill_check_table()
        item = (
            await self.db.execute(
                select(GlameTreasuryRefillCheck)
                .where(GlameTreasuryRefillCheck.id == approval_id)
            )
        ).scalar_one_or_none()
        if item is None or item.event_type != "refill_approval":
            raise ValueError("Refill approval не найден")
        if item.status != "approved":
            raise ValueError("Refill approval еще не подтвержден")
        if str(item.network or "") != str(plan.get("network") or ""):
            raise ValueError("Refill approval устарел: network отличается")
        if str(item.treasury_address or "") != str(plan.get("source_address") or ""):
            raise ValueError("Refill approval устарел: treasury address отличается")
        if str(item.hot_wallet_address or "") != str(plan.get("destination_address") or ""):
            raise ValueError("Refill approval устарел: hot-wallet address отличается")
        if Decimal(str(item.refill_glm_amount or 0)) != Decimal(str(plan.get("refill_glm_amount") or 0)):
            raise ValueError("Refill approval устарел: GLM сумма отличается")
        if Decimal(str(item.refill_ton_amount or 0)) != Decimal(str(plan.get("refill_ton_amount") or 0)):
            raise ValueError("Refill approval устарел: TON сумма отличается")
        return self.refill_check_payload(item)

    @staticmethod
    def alerts_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        critical_only = bool((payload.get("config") or {}).get("critical_only"))
        for wallet in payload.get("wallets") or []:
            role = wallet.get("role")
            if role not in {"hot_wallet", "treasury"}:
                continue
            status = wallet.get("status")
            if status not in {"warning", "critical", "error", "not_configured"}:
                continue
            severity = "critical" if status in {"critical", "error"} else "warning"
            if critical_only and severity != "critical":
                continue
            glm_balance = wallet.get("glm_balance", 0)
            ton_balance = wallet.get("ton_balance", 0)
            required_glm = wallet.get("required_glm", 0)
            required_ton = wallet.get("required_ton", 0)
            code = f"{role}_{'glm_low' if Decimal(str(glm_balance)) < Decimal(str(required_glm or 0)) else 'ton_low'}"
            reason = "balance_low"
            if role == "hot_wallet":
                refill_glm = wallet.get("refill_threshold_glm")
                refill_ton = wallet.get("refill_threshold_ton")
                if refill_glm is not None and Decimal(str(glm_balance)) < Decimal(str(refill_glm or 0)):
                    code = "hot_wallet_refill_glm_low"
                    reason = "refill_threshold"
                elif refill_ton is not None and Decimal(str(ton_balance)) < Decimal(str(refill_ton or 0)):
                    code = "hot_wallet_refill_ton_low"
                    reason = "refill_threshold"
            if status == "error":
                code = f"{role}_balance_error"
                reason = "balance_error"
            if status == "not_configured":
                code = f"{role}_not_configured"
                reason = "not_configured"
            alerts.append(
                {
                    "code": code,
                    "severity": severity,
                    "fingerprint": f"{code}:{glm_balance}:{ton_balance}:{required_glm}:{required_ton}:{status}",
                    "message": (
                        f"{role}: GLM {glm_balance} / need {required_glm}; "
                        f"TON {ton_balance} / need {required_ton}; "
                        f"safe GLM capacity={wallet.get('safe_transfer_capacity_glm')}; "
                        f"GLM refill batch={wallet.get('refill_target_glm')}; reason={reason}; status={status}."
                    ),
                    "wallet": wallet,
                }
            )
        return alerts
