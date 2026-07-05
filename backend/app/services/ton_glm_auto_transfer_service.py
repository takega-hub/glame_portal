from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from tonsdk.boc import Cell
from tonsdk.contract.wallet import Wallets, WalletVersionEnum
from tonsdk.utils import Address

from app.models.glame_token import GlameTokenTransaction
from app.services.glame_token_service import JETTON_TRANSFER_OP, GlameTokenService
from app.services.ton_glm_settlement_service import TonGlmSettlementService


def _env_bool(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


PRODUCTION_SIGNER_MODES = {"kms", "vault", "external_signer"}


class TonGlmAutoTransferService:
    """Send pending points->GLM claims from a limited hot wallet."""

    OVERRIDE_FILE = Path(__file__).resolve().parents[2] / "static" / "glm_policy" / "ton-auto-transfer-override.json"

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def override_payload() -> dict[str, Any]:
        path = TonGlmAutoTransferService.OVERRIDE_FILE
        if not path.exists():
            return {"exists": False, "enabled": None}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as error:
            return {"exists": True, "enabled": None, "error": str(error)}
        if not isinstance(payload, dict):
            return {"exists": True, "enabled": None, "error": "override payload must be an object"}
        return {
            "exists": True,
            "enabled": payload.get("enabled"),
            "reason": payload.get("reason"),
            "updated_at": payload.get("updated_at"),
            "updated_by": payload.get("updated_by"),
        }

    @staticmethod
    def write_override(*, enabled: bool, reason: str | None, admin_user_id: UUID) -> dict[str, Any]:
        path = TonGlmAutoTransferService.OVERRIDE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "enabled": bool(enabled),
            "reason": (reason or "").strip() or None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": str(admin_user_id),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return TonGlmAutoTransferService.override_payload()

    @staticmethod
    def config_payload() -> dict[str, Any]:
        network = os.getenv("TON_NETWORK", "testnet").strip() or "testnet"
        mnemonic_present = bool((os.getenv("TON_GLM_AUTO_TRANSFER_HOT_WALLET_MNEMONIC") or "").strip())
        signer_mode = (os.getenv("TON_GLM_AUTO_TRANSFER_SIGNER_MODE") or ("env_mnemonic" if mnemonic_present else "none")).strip().lower()
        production_signer_mode = (os.getenv("TON_GLM_PRODUCTION_SIGNER_MODE") or "not_configured").strip().lower()
        production_hot_wallet_address = (os.getenv("TON_GLM_PRODUCTION_HOT_WALLET_ADDRESS") or "").strip() or None
        production_hot_wallet_bounceable = (os.getenv("TON_GLM_PRODUCTION_HOT_WALLET_BOUNCEABLE") or "").strip() or None
        production_hot_wallet_raw = (os.getenv("TON_GLM_PRODUCTION_HOT_WALLET_RAW") or "").strip() or None
        production_signer_endpoint = (os.getenv("TON_GLM_PRODUCTION_SIGNER_ENDPOINT") or "").strip() or None
        production_safe_signer = production_signer_mode in PRODUCTION_SIGNER_MODES and not mnemonic_present
        production_candidate_ready = bool(production_hot_wallet_address and production_hot_wallet_bounceable and production_hot_wallet_raw)
        production_legal_approved = _env_bool("TON_GLM_PRODUCTION_LEGAL_APPROVED", "false")
        production_security_approved = _env_bool("TON_GLM_PRODUCTION_SECURITY_APPROVED", "false")
        production_treasury_approved = _env_bool("TON_GLM_PRODUCTION_TREASURY_APPROVED", "false")
        production_approvals_ready = bool(production_legal_approved and production_security_approved and production_treasury_approved)
        production_ready = bool(production_candidate_ready and production_safe_signer and production_approvals_ready)
        override = TonGlmAutoTransferService.override_payload()
        env_enabled = _env_bool("TON_GLM_AUTO_TRANSFER_ENABLED", "false")
        override_enabled = override.get("enabled")
        effective_enabled = bool(env_enabled if override_enabled is None else override_enabled)
        return {
            "enabled": effective_enabled,
            "env_enabled": env_enabled,
            "override": override,
            "network": network,
            "has_hot_wallet_mnemonic": mnemonic_present,
            "signer_mode": signer_mode,
            "secret_source": "env_mnemonic" if mnemonic_present else signer_mode,
            "production_safe_signer": production_safe_signer,
            "production_signer_mode": production_signer_mode,
            "production_signer_endpoint_configured": bool(production_signer_endpoint),
            "production_hot_wallet_address": production_hot_wallet_address,
            "production_hot_wallet_bounceable": production_hot_wallet_bounceable,
            "production_hot_wallet_raw": production_hot_wallet_raw,
            "production_candidate_ready": production_candidate_ready,
            "production_legal_approved": production_legal_approved,
            "production_security_approved": production_security_approved,
            "production_treasury_approved": production_treasury_approved,
            "production_approvals_ready": production_approvals_ready,
            "production_ready": production_ready,
            "requires_secret_rotation": mnemonic_present,
            "hot_wallet_address": (os.getenv("TON_GLM_AUTO_TRANSFER_HOT_WALLET_ADDRESS") or "").strip() or None,
            "wallet_version": (os.getenv("TON_GLM_AUTO_TRANSFER_WALLET_VERSION") or "v4r2").strip().lower(),
            "admin_user_id": (os.getenv("TON_GLM_AUTO_TRANSFER_ADMIN_USER_ID") or os.getenv("TON_GLM_SETTLEMENT_ADMIN_USER_ID") or "").strip() or None,
            "max_amount_glm": int(os.getenv("TON_GLM_AUTO_TRANSFER_MAX_AMOUNT_GLM", "1000") or 1000),
            "daily_limit_glm": int(os.getenv("TON_GLM_AUTO_TRANSFER_DAILY_LIMIT_GLM", "5000") or 5000),
            "tx_value_nanoton": int(os.getenv("TON_GLM_AUTO_TRANSFER_TX_VALUE_NANOTON", os.getenv("TON_GLM_TRANSFER_TX_VALUE_NANOTON", "50000000")) or 50_000_000),
            "forward_nanoton": int(os.getenv("TON_GLM_AUTO_TRANSFER_FORWARD_NANOTON", os.getenv("TON_GLM_TRANSFER_FORWARD_NANOTON", "1")) or 1),
            "settlement_attempts": int(os.getenv("TON_GLM_AUTO_TRANSFER_SETTLEMENT_ATTEMPTS", "5") or 5),
            "settlement_delay_seconds": float(os.getenv("TON_GLM_AUTO_TRANSFER_SETTLEMENT_DELAY_SECONDS", "4") or 4),
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

    @staticmethod
    def _api_key() -> str:
        return (os.getenv("TONCENTER_API_KEY") or os.getenv("TON_API_KEY") or "").strip()

    @staticmethod
    def _hot_wallet_mnemonic_words() -> list[str]:
        mnemonic_raw = (os.getenv("TON_GLM_AUTO_TRANSFER_HOT_WALLET_MNEMONIC") or "").strip()
        if not mnemonic_raw:
            raise ValueError("TON_GLM_AUTO_TRANSFER_HOT_WALLET_MNEMONIC is not set")
        words = [item.strip() for item in mnemonic_raw.replace(",", " ").split() if item.strip()]
        if len(words) != 24:
            raise ValueError("TON_GLM_AUTO_TRANSFER_HOT_WALLET_MNEMONIC must contain 24 words")
        return words

    @staticmethod
    def _wallet_from_env() -> tuple[list[str], Any]:
        words = TonGlmAutoTransferService._hot_wallet_mnemonic_words()
        mnemonics, _pub, _priv, wallet = Wallets.from_mnemonics(words, WalletVersionEnum.v4r2, workchain=0)
        expected = (os.getenv("TON_GLM_AUTO_TRANSFER_HOT_WALLET_ADDRESS") or "").strip()
        if expected:
            actual_raw = Address(wallet.address.to_string(False)).to_string(False)
            expected_raw = Address(expected).to_string(False)
            if actual_raw != expected_raw:
                raise ValueError("Hot wallet mnemonic does not match TON_GLM_AUTO_TRANSFER_HOT_WALLET_ADDRESS")
        return mnemonics, wallet

    @staticmethod
    def _expected_hot_wallet_address() -> str:
        expected = (os.getenv("TON_GLM_AUTO_TRANSFER_HOT_WALLET_ADDRESS") or "").strip()
        if not expected:
            raise ValueError("TON_GLM_AUTO_TRANSFER_HOT_WALLET_ADDRESS is not set")
        return expected

    async def _send_w5_jetton_transfer(
        self,
        *,
        amount_base_units: int,
        destination: str,
        query_id: int,
        comment: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        script_path = Path(__file__).resolve().parents[2] / "scripts" / "ton_w5_jetton_transfer.mjs"
        if not script_path.exists():
            raise ValueError(f"W5 transfer helper not found: {script_path}")
        request = {
            "network": config.get("network") or "testnet",
            "toncenterBaseUrl": self._toncenter_v2_base(),
            "apiKey": self._api_key(),
            "mnemonic": " ".join(self._hot_wallet_mnemonic_words()),
            "expectedWalletAddress": self._expected_hot_wallet_address(),
            "jettonMasterAddress": os.getenv("TON_GLM_JETTON_MASTER_ADDRESS"),
            "destinationWalletAddress": destination,
            "amountBaseUnits": str(amount_base_units),
            "txValueNanoton": str(config["tx_value_nanoton"]),
            "forwardNanoton": str(config["forward_nanoton"]),
            "queryId": str(query_id),
            "comment": comment,
        }

        def run() -> dict[str, Any]:
            completed = subprocess.run(
                ["node", str(script_path)],
                input=json.dumps(request),
                text=True,
                capture_output=True,
                timeout=45,
                check=False,
            )
            stdout = (completed.stdout or "").strip()
            stderr = (completed.stderr or "").strip()
            if completed.returncode != 0:
                error_payload: dict[str, Any] = {}
                if stderr:
                    try:
                        error_payload = json.loads(stderr.splitlines()[-1])
                    except json.JSONDecodeError:
                        error_payload = {"error": stderr}
                raise ValueError(error_payload.get("error") or f"W5 transfer helper failed with code {completed.returncode}")
            try:
                return json.loads(stdout.splitlines()[-1])
            except (IndexError, json.JSONDecodeError) as error:
                raise ValueError(f"W5 transfer helper returned invalid response: {stdout}") from error

        return await asyncio.to_thread(run)

    async def _wallet_seqno(self, wallet_address: str) -> int:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self._toncenter_v2_base()}/getWalletInformation",
                params={"address": wallet_address},
                headers=self._headers(),
            )
            response.raise_for_status()
            payload = response.json()
        result = payload.get("result") if isinstance(payload, dict) else {}
        if not isinstance(result, dict):
            return 0
        return int(result.get("seqno") or 0)

    async def _send_boc(self, boc_base64: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{self._toncenter_v2_base()}/sendBoc",
                json={"boc": boc_base64},
                headers=self._headers(),
            )
            if response.status_code >= 400:
                response = await client.post(
                    f"{self._toncenter_v2_base()}/sendBoc",
                    data={"boc": boc_base64},
                    headers=self._headers(),
                )
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _claim_wallet(meta: dict[str, Any]) -> str:
        wallet = (meta.get("wallet_address") or "").strip() if isinstance(meta.get("wallet_address"), str) else ""
        if not wallet:
            raise ValueError("Claim wallet_address is missing")
        return wallet

    async def _daily_auto_total(self) -> int:
        now = datetime.now(timezone.utc)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        rows = (
            await self.db.execute(
                select(GlameTokenTransaction)
                .where(
                    GlameTokenTransaction.transaction_type == "claim",
                    GlameTokenTransaction.status == "processed",
                    GlameTokenTransaction.created_at >= day_start,
                )
                .order_by(desc(GlameTokenTransaction.created_at))
                .limit(2000)
            )
        ).scalars().all()
        total = 0
        for row in rows:
            meta = row.meta if isinstance(row.meta, dict) else {}
            auto = meta.get("ton_auto_transfer") if isinstance(meta.get("ton_auto_transfer"), dict) else {}
            if auto.get("status") in {"settled", "sent"}:
                total += int(row.amount or 0)
        return total

    async def _find_matching_tx_hash(
        self,
        *,
        claim: GlameTokenTransaction,
        lookup_addresses: list[str],
    ) -> str | None:
        config = TonGlmSettlementService.config_payload()
        async with httpx.AsyncClient(timeout=config["timeout_seconds"]) as client:
            for address in lookup_addresses:
                payload = None
                last_error: Exception | None = None
                for attempt in range(1, 4):
                    try:
                        response = await client.get(
                            f"{config['toncenter_base_url']}/getTransactions",
                            params={"address": address, "limit": config["lookup_limit"], "archival": "true"},
                            headers=self._headers(),
                        )
                        response.raise_for_status()
                        payload = response.json()
                        break
                    except httpx.HTTPStatusError as error:
                        last_error = error
                        if error.response.status_code != 429 or attempt == 3:
                            raise
                        await asyncio.sleep(float(attempt) * 1.5)
                    except httpx.HTTPError as error:
                        last_error = error
                        if attempt == 3:
                            raise
                        await asyncio.sleep(float(attempt) * 1.5)
                if payload is None:
                    if last_error:
                        raise last_error
                    continue
                transactions = payload.get("result") if isinstance(payload, dict) else []
                if not isinstance(transactions, list):
                    continue
                for tx in transactions:
                    if not isinstance(tx, dict):
                        continue
                    validation = TonGlmSettlementService._visible_transaction_validation(
                        tx=tx,
                        claim=claim,
                        config=config,
                    )
                    if validation.get("ok"):
                        tx_hash = tx.get("hash") or ((tx.get("transaction_id") or {}).get("hash") if isinstance(tx.get("transaction_id"), dict) else None)
                        return str(tx_hash) if tx_hash else None
        return None

    async def _settle_existing_transfer(
        self,
        *,
        claim: GlameTokenTransaction,
        meta: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any] | None:
        auto = meta.get("ton_auto_transfer") if isinstance(meta.get("ton_auto_transfer"), dict) else {}
        if auto.get("status") not in {"sent", "sent_waiting_settlement"}:
            return None

        admin_user_id = config.get("admin_user_id")
        if not admin_user_id:
            return {
                "status": "blocked_no_admin_user",
                "claim_id": str(claim.id),
            }

        tx_hash = str(auto.get("tx_hash") or "").strip() or None
        lookup_addresses = [
            item
            for item in [
                str(auto.get("hot_wallet_address") or "").strip(),
                str(auto.get("hot_jetton_wallet_address") or "").strip(),
                str(auto.get("destination_wallet_address") or "").strip(),
            ]
            if item
        ]
        if not tx_hash and lookup_addresses:
            tx_hash = await self._find_matching_tx_hash(claim=claim, lookup_addresses=lookup_addresses)
        if not tx_hash:
            return {
                "status": "sent_waiting_settlement",
                "claim_id": str(claim.id),
                "message": "TON transfer was sent earlier; tx hash is not visible yet.",
            }

        result = await TonGlmSettlementService(self.db).settle_claim_by_tx_hash(
            claim_id=claim.id,
            tx_hash=tx_hash,
            admin_user_id=UUID(str(admin_user_id)),
            comment="Auto treasury transfer settled by watcher.",
            require_verified=True,
        )
        if result.get("status") != "processed":
            now_iso = datetime.now(timezone.utc).isoformat()
            next_meta = dict(meta)
            next_meta["ton_auto_transfer"] = {
                **auto,
                "status": "sent_waiting_settlement",
                "updated_at": now_iso,
                "tx_hash": tx_hash,
                "settlement": result.get("verification"),
            }
            claim.meta = next_meta
            flag_modified(claim, "meta")
            await self.db.flush()
            await GlameTokenService(self.db).sync_bridge_operation(claim)
            return {
                "status": "sent_waiting_settlement",
                "claim_id": str(claim.id),
                "tx_hash": tx_hash,
                "settlement": result.get("verification"),
            }

        processed_claim = result.get("claim")
        if isinstance(processed_claim, GlameTokenTransaction):
            processed_meta = processed_claim.meta if isinstance(processed_claim.meta, dict) else {}
            processed_meta["ton_auto_transfer"] = {
                **(processed_meta.get("ton_auto_transfer") if isinstance(processed_meta.get("ton_auto_transfer"), dict) else {}),
                "status": "settled",
                "settled_at": datetime.now(timezone.utc).isoformat(),
                "tx_hash": tx_hash,
            }
            processed_claim.meta = processed_meta
            flag_modified(processed_claim, "meta")
            await self.db.flush()
            await GlameTokenService(self.db).sync_bridge_operation(processed_claim)
        return {
            "status": "settled",
            "claim_id": str(claim.id),
            "tx_hash": tx_hash,
            "settlement": result.get("verification"),
        }

    async def process_claim(self, *, claim: GlameTokenTransaction) -> dict[str, Any]:
        config = self.config_payload()
        claim = (
            await self.db.execute(
                select(GlameTokenTransaction)
                .where(GlameTokenTransaction.id == claim.id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if claim is None:
            raise ValueError("GLM claim не найден")
        meta = claim.meta if isinstance(claim.meta, dict) else {}
        now_iso = datetime.now(timezone.utc).isoformat()

        async def mark(status: str, **extra: Any) -> dict[str, Any]:
            current_meta = claim.meta if isinstance(claim.meta, dict) else meta
            next_meta = dict(current_meta)
            next_meta["ton_auto_transfer"] = {
                **(next_meta.get("ton_auto_transfer") if isinstance(next_meta.get("ton_auto_transfer"), dict) else {}),
                "status": status,
                "updated_at": now_iso,
                **extra,
            }
            claim.meta = next_meta
            flag_modified(claim, "meta")
            await self.db.flush()
            await GlameTokenService(self.db).sync_bridge_operation(claim)
            return {"status": status, "claim_id": str(claim.id), **extra}

        if not config["enabled"]:
            return await mark("disabled")
        if claim.status != "pending" or claim.transaction_type != "claim" or claim.reason != "points_to_ton_bridge":
            return await mark("skipped_not_points_to_ton")
        existing_transfer = await self._settle_existing_transfer(claim=claim, meta=meta, config=config)
        if existing_transfer is not None:
            return existing_transfer
        if str(meta.get("onec_spend_sync_status") or "") not in {"success", "manual_spend_document_recorded"}:
            return await mark("blocked_1c_not_ready", onec_spend_sync_status=meta.get("onec_spend_sync_status"))
        amount = int(claim.amount or 0)
        if amount <= 0 or amount > int(config["max_amount_glm"]):
            return await mark("blocked_amount_limit", amount_glm=amount, max_amount_glm=config["max_amount_glm"])
        daily_total = await self._daily_auto_total()
        if daily_total + amount > int(config["daily_limit_glm"]):
            return await mark("blocked_daily_limit", amount_glm=amount, daily_total_glm=daily_total, daily_limit_glm=config["daily_limit_glm"])
        admin_user_id = config.get("admin_user_id")
        if not admin_user_id:
            return await mark("blocked_no_admin_user")

        wallet_version = str(config.get("wallet_version") or "v4r2").lower()
        try:
            if wallet_version in {"w5", "w5r1", "v5", "v5r1"}:
                self._hot_wallet_mnemonic_words()
                hot_wallet_address = self._expected_hot_wallet_address()
                wallet = None
            else:
                _mnemonics, wallet = self._wallet_from_env()
                hot_wallet_address = wallet.address.to_string(True, True, True)
        except Exception as error:
            return await mark("blocked_no_hot_wallet_signer", error=str(error))

        balance_payload = await GlameTokenService(self.db).ton_wallet_glm_balance(hot_wallet_address)
        try:
            hot_balance = float(balance_payload.get("balance_glm") or 0)
        except (TypeError, ValueError):
            hot_balance = 0.0
        if hot_balance < amount:
            return await mark("blocked_hot_wallet_balance", amount_glm=amount, hot_wallet_balance=balance_payload)

        hot_jetton_wallet = (balance_payload.get("jetton_wallet_address") or "").strip()
        if not hot_jetton_wallet:
            return await mark("blocked_no_hot_jetton_wallet", hot_wallet_balance=balance_payload)

        decimals = int(os.getenv("TON_GLM_DECIMALS", "9") or 9)
        amount_base_units = amount * (10 ** decimals)
        query_id = int(datetime.now(timezone.utc).timestamp())
        destination = self._claim_wallet(meta)
        forward_payload = Cell()
        forward_payload.bits.write_uint(0, 32)
        forward_payload.bits.write_string(f"GLAME points_to_glm {claim.id}")

        body = Cell()
        body.bits.write_uint(JETTON_TRANSFER_OP, 32)
        body.bits.write_uint(query_id, 64)
        body.bits.write_coins(amount_base_units)
        body.bits.write_address(Address(destination))
        body.bits.write_address(Address(hot_wallet_address))
        body.bits.write_bit(0)
        body.bits.write_coins(int(config["forward_nanoton"]))
        body.bits.write_bit(1)
        body.refs.append(forward_payload)

        if wallet_version in {"w5", "w5r1", "v5", "v5r1"}:
            send_payload = await self._send_w5_jetton_transfer(
                amount_base_units=amount_base_units,
                destination=destination,
                query_id=query_id,
                comment=f"GLAME points_to_glm {claim.id}",
                config=config,
            )
            seqno = int(send_payload.get("seqno") or 0)
            hot_jetton_wallet = str(send_payload.get("hot_jetton_wallet_address") or hot_jetton_wallet)
            external_message_hash = None
        else:
            seqno = await self._wallet_seqno(hot_wallet_address)
            message = wallet.create_transfer_message(
                to_addr=hot_jetton_wallet,
                amount=int(config["tx_value_nanoton"]),
                seqno=seqno,
                payload=body,
            )["message"]
            boc_base64 = base64.b64encode(message.to_boc(False)).decode("ascii")
            external_message_hash = base64.b64encode(message.bytes_hash()).decode("ascii")
            send_payload = await self._send_boc(boc_base64)
        await mark(
            "sent",
            amount_glm=amount,
            amount_base_units=str(amount_base_units),
            hot_wallet_address=hot_wallet_address,
            hot_jetton_wallet_address=hot_jetton_wallet,
            destination_wallet_address=destination,
            query_id=str(query_id),
            seqno=seqno,
            external_message_hash=external_message_hash,
            wallet_version=wallet_version,
            send_response=send_payload,
        )
        await self.db.flush()

        lookup_addresses = [hot_wallet_address, hot_jetton_wallet]
        tx_hash = None
        for _attempt in range(max(1, int(config["settlement_attempts"]))):
            await asyncio.sleep(max(0.0, float(config["settlement_delay_seconds"])))
            tx_hash = await self._find_matching_tx_hash(claim=claim, lookup_addresses=lookup_addresses)
            if tx_hash:
                break

        if not tx_hash:
            return await mark("sent_waiting_settlement", external_message_hash=external_message_hash)

        result = await TonGlmSettlementService(self.db).settle_claim_by_tx_hash(
            claim_id=claim.id,
            tx_hash=tx_hash,
            admin_user_id=UUID(str(admin_user_id)),
            comment="Auto treasury hot-wallet transfer verified.",
            require_verified=True,
        )
        if result.get("status") != "processed":
            return await mark(
                "sent_waiting_settlement",
                tx_hash=tx_hash,
                external_message_hash=external_message_hash,
                settlement=result.get("verification"),
            )
        processed_claim = result.get("claim")
        if isinstance(processed_claim, GlameTokenTransaction):
            processed_meta = processed_claim.meta if isinstance(processed_claim.meta, dict) else {}
            processed_meta["ton_auto_transfer"] = {
                **(processed_meta.get("ton_auto_transfer") if isinstance(processed_meta.get("ton_auto_transfer"), dict) else {}),
                "status": "settled",
                "settled_at": datetime.now(timezone.utc).isoformat(),
                "tx_hash": tx_hash,
                "external_message_hash": external_message_hash,
            }
            processed_claim.meta = processed_meta
            flag_modified(processed_claim, "meta")
            await self.db.flush()
            await GlameTokenService(self.db).sync_bridge_operation(processed_claim)
        return {"status": "settled", "claim_id": str(claim.id), "tx_hash": tx_hash, "settlement": result.get("verification")}

    async def process_pending_claims(self, *, limit: int = 20) -> dict[str, Any]:
        rows = (
            await self.db.execute(
                select(GlameTokenTransaction)
                .where(
                    GlameTokenTransaction.transaction_type == "claim",
                    GlameTokenTransaction.status == "pending",
                    GlameTokenTransaction.reason == "points_to_ton_bridge",
                )
                .order_by(GlameTokenTransaction.created_at.asc(), GlameTokenTransaction.id.asc())
                .limit(max(1, int(limit or 20)))
            )
        ).scalars().all()
        results: list[dict[str, Any]] = []
        for claim in rows:
            try:
                results.append(await self.process_claim(claim=claim))
            except Exception as error:
                results.append({"status": "failed", "claim_id": str(claim.id), "error": str(error)})
        return {
            "checked": len(rows),
            "results": results,
            "config": self.config_payload(),
        }
