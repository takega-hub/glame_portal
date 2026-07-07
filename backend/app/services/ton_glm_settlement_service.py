from __future__ import annotations

import os
import base64
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from tonsdk.boc import Cell
from tonsdk.utils import Address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.glame_token import GlameTokenTransaction
from app.services.glame_token_service import GlameTokenService

JETTON_MINTER_MINT_OP = 0x642B7D07
JETTON_INTERNAL_TRANSFER_OP = 0x178D4519
JETTON_TRANSFER_OP = 0x0F8A7EA5
JETTON_TRANSFER_NOTIFICATION_OP = 0x7362D09C


def _env_bool(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


class TonGlmSettlementService:
    """Verify TON transaction hashes before closing GLM pending claims."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def config_payload() -> dict[str, Any]:
        network = os.getenv("TON_NETWORK", "testnet").strip() or "testnet"
        default_base = "https://testnet.toncenter.com/api/v2" if network == "testnet" else "https://toncenter.com/api/v2"
        lookup_addresses = [
            item.strip()
            for item in (os.getenv("TON_GLM_SETTLEMENT_LOOKUP_ADDRESSES") or "").split(",")
            if item.strip()
        ]
        return {
            "enabled": _env_bool("TON_GLM_SETTLEMENT_WATCHER_ENABLED", "false"),
            "network": network,
            "toncenter_base_url": (os.getenv("TONCENTER_API_BASE_URL") or default_base).rstrip("/"),
            "has_toncenter_api_key": bool((os.getenv("TONCENTER_API_KEY") or "").strip()),
            "lookup_addresses": lookup_addresses,
            "lookup_limit": int(os.getenv("TON_GLM_SETTLEMENT_LOOKUP_LIMIT", "50") or 50),
            "timeout_seconds": float(os.getenv("TON_GLM_SETTLEMENT_TIMEOUT_SECONDS", "12") or 12),
            "jetton_master_address": (os.getenv("TON_GLM_JETTON_MASTER_ADDRESS") or "").strip() or None,
            "decimals": int(os.getenv("TON_GLM_DECIMALS", "9") or 9),
            "require_master_out_msg": _env_bool("TON_GLM_SETTLEMENT_REQUIRE_MASTER_OUT_MSG", "true"),
        }

    @staticmethod
    def _normalize_hash(value: str | None) -> str:
        return (value or "").strip()

    @classmethod
    def _hash_matches(cls, tx: dict[str, Any], expected_hash: str) -> bool:
        candidates = [
            tx.get("hash"),
            (tx.get("transaction_id") or {}).get("hash") if isinstance(tx.get("transaction_id"), dict) else None,
        ]
        return cls._normalize_hash(expected_hash) in {cls._normalize_hash(item) for item in candidates if item}

    @staticmethod
    def _claim_lookup_addresses(claim: GlameTokenTransaction) -> list[str]:
        meta = claim.meta if isinstance(claim.meta, dict) else {}
        addresses: list[str] = []
        for key in ("wallet_address", "jetton_wallet_address", "settlement_lookup_address"):
            value = (meta.get(key) or "").strip() if isinstance(meta.get(key), str) else ""
            if value and value not in addresses:
                addresses.append(value)
        auto_transfer = meta.get("ton_auto_transfer") if isinstance(meta.get("ton_auto_transfer"), dict) else {}
        for key in ("hot_wallet_address", "hot_jetton_wallet_address", "destination_wallet_address"):
            value = (auto_transfer.get(key) or "").strip() if isinstance(auto_transfer.get(key), str) else ""
            if value and value not in addresses:
                addresses.append(value)
        hot_wallet_address = (os.getenv("TON_GLM_AUTO_TRANSFER_HOT_WALLET_ADDRESS") or "").strip()
        if hot_wallet_address and hot_wallet_address not in addresses:
            addresses.append(hot_wallet_address)
        for value in TonGlmSettlementService.config_payload()["lookup_addresses"]:
            if value not in addresses:
                addresses.append(value)
        return addresses

    @staticmethod
    def _candidate_tx_hash(claim: GlameTokenTransaction) -> str | None:
        meta = claim.meta if isinstance(claim.meta, dict) else {}
        for key in ("settlement_tx_hash", "operator_tx_hash", "ton_tx_hash", "tx_hash"):
            value = meta.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        auto_transfer = meta.get("ton_auto_transfer") if isinstance(meta.get("ton_auto_transfer"), dict) else {}
        value = auto_transfer.get("tx_hash")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    @staticmethod
    def _message_destination(message: dict[str, Any]) -> str | None:
        destination = message.get("destination")
        return destination.strip() if isinstance(destination, str) and destination.strip() else None

    @staticmethod
    def _normalize_ton_address(value: str | None) -> str | None:
        if not value:
            return None
        try:
            return Address(value.strip()).to_string(False)
        except Exception:
            return value.strip().lower()

    @staticmethod
    def _address_payload(address: Any) -> dict[str, Any] | None:
        if address is None:
            return None
        try:
            return {
                "raw": address.to_string(False),
                "friendly_testnet_bounceable": address.to_string(True, True, True),
                "friendly_testnet_non_bounceable": address.to_string(True, True, False),
            }
        except Exception:
            return {"raw": str(address)}

    @classmethod
    def _decode_minter_mint_body(cls, body_boc_base64: str | None) -> dict[str, Any]:
        if not body_boc_base64:
            return {
                "ok": False,
                "status": "missing_body",
                "message": "Out message has no BOC body.",
            }
        try:
            cell = Cell.one_from_boc(base64.b64decode(body_boc_base64))
            s = cell.begin_parse()
            op = s.read_uint(32)
            query_id = s.read_uint(64)
            destination = s.read_msg_addr()
            ton_amount = s.read_coins()
            master_msg_ref = s.read_ref()
            inner = master_msg_ref.begin_parse()
            inner_op = inner.read_uint(32)
            inner_query_id = inner.read_uint(64)
            jetton_amount = inner.read_coins()
            sender = inner.read_msg_addr()
            response_address = inner.read_msg_addr()
            return {
                "ok": op == JETTON_MINTER_MINT_OP and inner_op == JETTON_INTERNAL_TRANSFER_OP,
                "status": "decoded" if op == JETTON_MINTER_MINT_OP and inner_op == JETTON_INTERNAL_TRANSFER_OP else "unexpected_op",
                "op": hex(op),
                "expected_op": hex(JETTON_MINTER_MINT_OP),
                "query_id": str(query_id),
                "destination": cls._address_payload(destination),
                "ton_amount": str(ton_amount),
                "inner_op": hex(inner_op),
                "expected_inner_op": hex(JETTON_INTERNAL_TRANSFER_OP),
                "inner_query_id": str(inner_query_id),
                "jetton_amount": str(jetton_amount),
                "sender": cls._address_payload(sender),
                "response_address": cls._address_payload(response_address),
            }
        except Exception as error:
            return {
                "ok": False,
                "status": "decode_error",
                "message": str(error),
            }

    @classmethod
    def _decode_transfer_notification_body(cls, body_boc_base64: str | None) -> dict[str, Any]:
        if not body_boc_base64:
            return {
                "ok": False,
                "status": "missing_body",
                "message": "Incoming message has no BOC body.",
            }
        try:
            cell = Cell.one_from_boc(base64.b64decode(body_boc_base64))
            s = cell.begin_parse()
            op = s.read_uint(32)
            query_id = s.read_uint(64)
            jetton_amount = s.read_coins()
            sender = s.read_msg_addr()
            forward_payload_mode = None
            if not s.is_empty():
                try:
                    forward_payload_mode = int(s.read_bit())
                except Exception:
                    forward_payload_mode = None
            return {
                "ok": op == JETTON_TRANSFER_NOTIFICATION_OP,
                "status": "decoded" if op == JETTON_TRANSFER_NOTIFICATION_OP else "unexpected_op",
                "op": hex(op),
                "expected_op": hex(JETTON_TRANSFER_NOTIFICATION_OP),
                "query_id": str(query_id),
                "jetton_amount": str(jetton_amount),
                "sender": cls._address_payload(sender),
                "forward_payload_mode": forward_payload_mode,
            }
        except Exception as error:
            return {
                "ok": False,
                "status": "decode_error",
                "message": str(error),
            }

    @classmethod
    def _decode_jetton_transfer_body(cls, body_boc_base64: str | None) -> dict[str, Any]:
        if not body_boc_base64:
            return {
                "ok": False,
                "status": "missing_body",
                "message": "Out message has no BOC body.",
            }
        try:
            cell = Cell.one_from_boc(base64.b64decode(body_boc_base64))
            s = cell.begin_parse()
            op = s.read_uint(32)
            query_id = s.read_uint(64)
            jetton_amount = s.read_coins()
            destination = s.read_msg_addr()
            response_destination = s.read_msg_addr()
            custom_payload_mode = None
            forward_ton_amount = None
            forward_payload_mode = None
            if not s.is_empty():
                custom_payload_mode = int(s.read_bit())
                if custom_payload_mode:
                    s.read_ref()
            if not s.is_empty():
                forward_ton_amount = s.read_coins()
            if not s.is_empty():
                forward_payload_mode = int(s.read_bit())
                if forward_payload_mode:
                    s.read_ref()
            return {
                "ok": op == JETTON_TRANSFER_OP,
                "status": "decoded" if op == JETTON_TRANSFER_OP else "unexpected_op",
                "op": hex(op),
                "expected_op": hex(JETTON_TRANSFER_OP),
                "query_id": str(query_id),
                "jetton_amount": str(jetton_amount),
                "destination": cls._address_payload(destination),
                "response_destination": cls._address_payload(response_destination),
                "custom_payload_mode": custom_payload_mode,
                "forward_ton_amount": str(forward_ton_amount) if forward_ton_amount is not None else None,
                "forward_payload_mode": forward_payload_mode,
            }
        except Exception as error:
            return {
                "ok": False,
                "status": "decode_error",
                "message": str(error),
            }

    @staticmethod
    def _visible_transaction_validation(
        *,
        tx: dict[str, Any],
        claim: GlameTokenTransaction | None,
        config: dict[str, Any],
        expected_wallet_address: str | None = None,
        expected_amount_glm: int | None = None,
        context: str = "claim",
    ) -> dict[str, Any]:
        meta = claim.meta if claim is not None and isinstance(claim.meta, dict) else {}
        expected_wallet = expected_wallet_address or (meta.get("wallet_address") if isinstance(meta.get("wallet_address"), str) else None)
        expected_amount_glm = (
            abs(int(expected_amount_glm))
            if expected_amount_glm is not None
            else (abs(int(claim.amount or 0)) if claim is not None else None)
        )
        expected_amount_base_units = (
            expected_amount_glm * (10 ** int(config.get("decimals") or 0))
            if expected_amount_glm is not None
            else None
        )
        jetton_master = config.get("jetton_master_address")
        out_msgs = tx.get("out_msgs") if isinstance(tx.get("out_msgs"), list) else []
        out_destinations = [
            TonGlmSettlementService._message_destination(message)
            for message in out_msgs
            if isinstance(message, dict)
        ]
        out_destinations = [item for item in out_destinations if item]
        has_master_out_msg = bool(jetton_master and jetton_master in out_destinations)
        master_out_msg = next(
            (
                message
                for message in out_msgs
                if isinstance(message, dict)
                and jetton_master
                and TonGlmSettlementService._message_destination(message) == jetton_master
            ),
            None,
        )
        master_body = None
        if isinstance(master_out_msg, dict):
            msg_data = master_out_msg.get("msg_data") if isinstance(master_out_msg.get("msg_data"), dict) else {}
            master_body = msg_data.get("body") if isinstance(msg_data.get("body"), str) else None
        decoded_mint = TonGlmSettlementService._decode_minter_mint_body(master_body) if master_out_msg else None
        decoded_transfer = None
        transfer_out_msg = None
        for message in out_msgs:
            if not isinstance(message, dict):
                continue
            msg_data = message.get("msg_data") if isinstance(message.get("msg_data"), dict) else {}
            decoded = TonGlmSettlementService._decode_jetton_transfer_body(
                msg_data.get("body") if isinstance(msg_data.get("body"), str) else None
            )
            if decoded.get("ok"):
                decoded_transfer = decoded
                transfer_out_msg = message
                break
        require_master = bool(config.get("require_master_out_msg"))
        decoded_destination_raw = (
            ((decoded_mint or {}).get("destination") or {}).get("raw")
            if isinstance((decoded_mint or {}).get("destination"), dict)
            else None
        )
        decoded_amount = int((decoded_mint or {}).get("jetton_amount") or 0) if decoded_mint and str((decoded_mint or {}).get("jetton_amount") or "").isdigit() else None
        transfer_destination_raw = (
            ((decoded_transfer or {}).get("destination") or {}).get("raw")
            if isinstance((decoded_transfer or {}).get("destination"), dict)
            else None
        )
        transfer_amount = (
            int((decoded_transfer or {}).get("jetton_amount") or 0)
            if decoded_transfer and str((decoded_transfer or {}).get("jetton_amount") or "").isdigit()
            else None
        )
        expected_wallet_raw = TonGlmSettlementService._normalize_ton_address(expected_wallet)
        mint_matches_recipient = bool(decoded_mint and decoded_mint.get("ok") and expected_wallet_raw and decoded_destination_raw == expected_wallet_raw)
        mint_matches_amount = bool(decoded_mint and decoded_mint.get("ok") and expected_amount_base_units is not None and decoded_amount == expected_amount_base_units)
        transfer_matches_recipient = bool(decoded_transfer and decoded_transfer.get("ok") and expected_wallet_raw and transfer_destination_raw == expected_wallet_raw)
        transfer_matches_amount = bool(decoded_transfer and decoded_transfer.get("ok") and expected_amount_base_units is not None and transfer_amount == expected_amount_base_units)
        has_valid_mint = mint_matches_recipient and mint_matches_amount
        has_valid_treasury_transfer = transfer_matches_recipient and transfer_matches_amount

        checks = [
            {
                "code": "tx_found",
                "ok": True,
                "message": "TON tx hash найден в истории lookup-адреса.",
            },
            {
                "code": "jetton_execution_body",
                "ok": bool(has_valid_mint or has_valid_treasury_transfer or (has_master_out_msg and not require_master)),
                "message": "TON transaction должен содержать GLM Jetton mint body или Jetton transfer body из treasury.",
                "expected": jetton_master,
                "actual_destinations": out_destinations,
                "required": require_master,
            },
            {
                "code": "recipient_decode",
                "ok": bool(mint_matches_recipient or transfer_matches_recipient)
                if expected_wallet_raw
                else None,
                "message": f"Recipient в Jetton mint/transfer body должен совпадать с TON-кошельком {context}.",
                "expected": expected_wallet_raw,
                "actual": transfer_destination_raw or decoded_destination_raw,
            },
            {
                "code": "amount_decode",
                "ok": bool(mint_matches_amount or transfer_matches_amount)
                if expected_amount_base_units is not None
                else None,
                "message": "Jetton amount в mint/transfer body должен совпадать с claim amount * 10^decimals.",
                "expected_glm": expected_amount_glm,
                "expected_base_units": str(expected_amount_base_units) if expected_amount_base_units is not None else None,
                "actual_base_units": str(transfer_amount if transfer_amount is not None else decoded_amount) if (transfer_amount is not None or decoded_amount is not None) else None,
            },
        ]
        blocking = [item for item in checks if item.get("ok") is False]
        return {
            "ok": not blocking,
            "status": "visible_checks_passed" if not blocking else "visible_checks_failed",
            "checks": checks,
            "blocking": blocking,
            "out_destinations": out_destinations,
            "decoded_minter_mint": decoded_mint,
            "decoded_jetton_transfer": decoded_transfer,
            "jetton_transfer_destination": TonGlmSettlementService._message_destination(transfer_out_msg) if isinstance(transfer_out_msg, dict) else None,
            "settlement_mode": "treasury_transfer" if has_valid_treasury_transfer else ("mint" if has_valid_mint else None),
            "expected_wallet_address": expected_wallet_raw,
            "expected_amount_glm": expected_amount_glm,
            "expected_amount_base_units": str(expected_amount_base_units) if expected_amount_base_units is not None else None,
        }

    @staticmethod
    def _bridge_deposit_lookup_addresses(bridge: GlameTokenTransaction) -> list[str]:
        meta = bridge.meta if isinstance(bridge.meta, dict) else {}
        addresses: list[str] = []
        for key in ("treasury_address", "treasury_deposit_address", "deposit_lookup_address"):
            value = (meta.get(key) or "").strip() if isinstance(meta.get(key), str) else ""
            if value and value not in addresses:
                addresses.append(value)
        treasury = (os.getenv("TON_GLM_TREASURY_ADDRESS") or "").strip()
        if treasury and treasury not in addresses:
            addresses.append(treasury)
        for value in TonGlmSettlementService.config_payload()["lookup_addresses"]:
            if value not in addresses:
                addresses.append(value)
        return addresses

    @staticmethod
    def _bridge_candidate_tx_hash(bridge: GlameTokenTransaction) -> str | None:
        meta = bridge.meta if isinstance(bridge.meta, dict) else {}
        for key in ("deposit_tx_hash", "settlement_tx_hash", "operator_tx_hash", "ton_tx_hash", "tx_hash"):
            value = meta.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _deposit_transaction_validation(
        *,
        tx: dict[str, Any],
        bridge: GlameTokenTransaction,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        meta = bridge.meta if isinstance(bridge.meta, dict) else {}
        expected_sender_raw = TonGlmSettlementService._normalize_ton_address(
            meta.get("expected_ton_sender_address") if isinstance(meta.get("expected_ton_sender_address"), str) else None
        )
        expected_amount_glm = abs(int(bridge.amount or 0))
        expected_amount_base_units = expected_amount_glm * (10 ** int(config.get("decimals") or 0))
        in_msg = tx.get("in_msg") if isinstance(tx.get("in_msg"), dict) else {}
        msg_data = in_msg.get("msg_data") if isinstance(in_msg.get("msg_data"), dict) else {}
        body = msg_data.get("body") if isinstance(msg_data.get("body"), str) else None
        decoded = TonGlmSettlementService._decode_transfer_notification_body(body)
        decoded_sender_raw = (
            ((decoded or {}).get("sender") or {}).get("raw")
            if isinstance((decoded or {}).get("sender"), dict)
            else None
        )
        decoded_amount = int((decoded or {}).get("jetton_amount") or 0) if str((decoded or {}).get("jetton_amount") or "").isdigit() else None

        checks = [
            {
                "code": "tx_found",
                "ok": True,
                "message": "TON tx hash найден в истории treasury lookup-адреса.",
            },
            {
                "code": "transfer_notification_decode",
                "ok": bool(decoded.get("ok")),
                "message": "Treasury transaction должен содержать Jetton transfer_notification body.",
                "decoded_status": decoded.get("status"),
                "op": decoded.get("op"),
            },
            {
                "code": "sender_decode",
                "ok": bool(decoded.get("ok") and expected_sender_raw and decoded_sender_raw == expected_sender_raw)
                if expected_sender_raw
                else None,
                "message": "Sender в transfer_notification должен совпадать с TON-кошельком bridge.",
                "expected": expected_sender_raw,
                "actual": decoded_sender_raw,
            },
            {
                "code": "amount_decode",
                "ok": bool(decoded.get("ok") and decoded_amount == expected_amount_base_units),
                "message": "Jetton amount в transfer_notification должен совпадать с bridge amount * 10^decimals.",
                "expected_glm": expected_amount_glm,
                "expected_base_units": str(expected_amount_base_units),
                "actual_base_units": str(decoded_amount) if decoded_amount is not None else None,
            },
        ]
        blocking = [item for item in checks if item.get("ok") is False]
        return {
            "ok": not blocking,
            "status": "deposit_checks_passed" if not blocking else "deposit_checks_failed",
            "checks": checks,
            "blocking": blocking,
            "decoded_transfer_notification": decoded,
            "expected_sender_address": expected_sender_raw,
            "expected_amount_glm": expected_amount_glm,
            "expected_amount_base_units": str(expected_amount_base_units),
        }

    async def verify_tx_hash(
        self,
        *,
        tx_hash: str,
        lookup_addresses: list[str],
        claim: GlameTokenTransaction | None = None,
        expected_wallet_address: str | None = None,
        expected_amount_glm: int | None = None,
        context: str = "claim",
    ) -> dict[str, Any]:
        config = self.config_payload()
        normalized_hash = self._normalize_hash(tx_hash)
        if not normalized_hash:
            return {
                "ok": False,
                "status": "missing_tx_hash",
                "message": "TON tx hash is required for settlement verification.",
                "config": config,
            }
        if not lookup_addresses:
            return {
                "ok": False,
                "status": "missing_lookup_address",
                "message": "Set TON_GLM_SETTLEMENT_LOOKUP_ADDRESSES or store wallet/jetton wallet address in claim meta.",
                "config": config,
            }

        headers = {}
        api_key = (os.getenv("TONCENTER_API_KEY") or "").strip()
        if api_key:
            headers["X-API-Key"] = api_key

        checked: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=config["timeout_seconds"]) as client:
            for address in lookup_addresses:
                try:
                    response = await client.get(
                        f"{config['toncenter_base_url']}/getTransactions",
                        params={
                            "address": address,
                            "limit": config["lookup_limit"],
                            "archival": "true",
                        },
                        headers=headers,
                    )
                    response.raise_for_status()
                    payload = response.json()
                except Exception as error:
                    checked.append({
                        "address": address,
                        "ok": False,
                        "error": str(error),
                    })
                    continue

                transactions = payload.get("result") if isinstance(payload, dict) else None
                if not isinstance(transactions, list):
                    checked.append({
                        "address": address,
                        "ok": False,
                        "error": "Unexpected TON Center response.",
                    })
                    continue

                for tx in transactions:
                    if isinstance(tx, dict) and self._hash_matches(tx, normalized_hash):
                        visible_validation = self._visible_transaction_validation(
                            tx=tx,
                            claim=claim,
                            config=config,
                            expected_wallet_address=expected_wallet_address,
                            expected_amount_glm=expected_amount_glm,
                            context=context,
                        )
                        return {
                            "ok": bool(visible_validation.get("ok")),
                            "status": "verified" if visible_validation.get("ok") else "visible_validation_failed",
                            "message": "TON tx hash found in TON Center transactions.",
                            "tx_hash": normalized_hash,
                            "matched_address": address,
                            "transaction_id": tx.get("transaction_id"),
                            "utime": tx.get("utime"),
                            "visible_validation": visible_validation,
                            "config": config,
                            "checked": checked,
                        }
                checked.append({
                    "address": address,
                    "ok": True,
                    "transactions_checked": len(transactions),
                })

        return {
            "ok": False,
            "status": "not_found",
            "message": "TON tx hash was not found in checked TON Center transactions.",
            "tx_hash": normalized_hash,
            "config": config,
            "checked": checked,
        }

    @staticmethod
    def _redemption_refund_lookup_addresses(redemption: GlameTokenTransaction) -> list[str]:
        meta = redemption.meta if isinstance(redemption.meta, dict) else {}
        addresses: list[str] = []
        for key in ("treasury_address", "ton_refund_treasury_jetton_wallet", "settlement_lookup_address"):
            value = (meta.get(key) or "").strip() if isinstance(meta.get(key), str) else ""
            if value and value not in addresses:
                addresses.append(value)
        treasury = (os.getenv("TON_GLM_TREASURY_ADDRESS") or "").strip()
        if treasury and treasury not in addresses:
            addresses.append(treasury)
        for value in TonGlmSettlementService.config_payload()["lookup_addresses"]:
            if value not in addresses:
                addresses.append(value)
        return addresses

    async def settle_redemption_ton_refund_by_tx_hash(
        self,
        *,
        redemption_id: UUID,
        tx_hash: str,
        admin_user_id: UUID,
        comment: str | None = None,
        require_verified: bool = True,
    ) -> dict[str, Any]:
        redemption = (
            await self.db.execute(
                select(GlameTokenTransaction).where(
                    GlameTokenTransaction.id == redemption_id,
                    GlameTokenTransaction.transaction_type == "redemption",
                    GlameTokenTransaction.reason == "glm_store_item",
                )
            )
        ).scalar_one_or_none()
        if redemption is None:
            raise ValueError("GLM Store redemption не найден")
        if redemption.status not in {"canceled", "failed"}:
            raise ValueError("TON refund можно сверять только для отмененных или ошибочных GLM Store заказов")

        meta = redemption.meta if isinstance(redemption.meta, dict) else {}
        if meta.get("payment_method") != "ton_glm":
            raise ValueError("TON refund доступен только для GLM Store заказов, оплаченных GLM в TON")

        recipient = (
            (meta.get("ton_refund_recipient_address") or "").strip()
            if isinstance(meta.get("ton_refund_recipient_address"), str)
            else ""
        ) or (
            (meta.get("expected_ton_sender_address") or "").strip()
            if isinstance(meta.get("expected_ton_sender_address"), str)
            else ""
        )
        if not recipient:
            raise ValueError("Не найден TON-кошелек получателя refund")

        verification = await self.verify_tx_hash(
            tx_hash=tx_hash,
            lookup_addresses=self._redemption_refund_lookup_addresses(redemption),
            claim=redemption,
            expected_wallet_address=recipient,
            expected_amount_glm=abs(int(redemption.amount or 0)),
            context="refund",
        )

        now_iso = datetime.now(timezone.utc).isoformat()
        redemption.meta = {
            **meta,
            "ton_refund_tx_hash": tx_hash,
            "ton_refund_status": "verified" if verification.get("ok") else "verification_failed",
            "ton_refund_required": False if verification.get("ok") else meta.get("ton_refund_required", False),
            "ton_refund_verified_at": now_iso if verification.get("ok") else meta.get("ton_refund_verified_at"),
            "ton_refund_settlement_comment": (comment or "").strip() or None,
            "ton_refund_verification": {
                **verification,
                "verified_at": now_iso,
                "verified_by": str(admin_user_id),
            },
        }
        flag_modified(redemption, "meta")
        await self.db.flush()

        if require_verified and not verification.get("ok"):
            return {
                "status": "blocked",
                "redemption": redemption,
                "verification": verification,
            }

        return {
            "status": "verified" if verification.get("ok") else "recorded",
            "redemption": redemption,
            "verification": verification,
        }

    async def settle_claim_by_tx_hash(
        self,
        *,
        claim_id: UUID,
        tx_hash: str,
        admin_user_id: UUID,
        comment: str | None = None,
        require_verified: bool = True,
    ) -> dict[str, Any]:
        claim = (
            await self.db.execute(
                select(GlameTokenTransaction).where(
                    GlameTokenTransaction.id == claim_id,
                    GlameTokenTransaction.transaction_type == "claim",
                )
            )
        ).scalar_one_or_none()
        if claim is None:
            raise ValueError("GLM claim не найден")
        if claim.status != "pending":
            raise ValueError("Можно settlement только pending claim")

        lookup_addresses = self._claim_lookup_addresses(claim)
        verification = await self.verify_tx_hash(tx_hash=tx_hash, lookup_addresses=lookup_addresses, claim=claim)

        meta = claim.meta if isinstance(claim.meta, dict) else {}
        claim.meta = {
            **meta,
            "ton_settlement_verification": {
                **verification,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "verified_by": str(admin_user_id),
            },
        }
        flag_modified(claim, "meta")
        await self.db.flush()
        await GlameTokenService(self.db).sync_bridge_operation(claim)

        if require_verified and not verification.get("ok"):
            return {
                "status": "blocked",
                "claim": claim,
                "verification": verification,
            }

        processed = await GlameTokenService(self.db).update_claim_status(
            claim=claim,
            status="processed",
            admin_user_id=admin_user_id,
            tx_hash=tx_hash,
            comment=comment or "TON settlement verified by watcher.",
        )
        return {
            "status": "processed",
            "claim": processed,
            "verification": verification,
        }

    async def verify_deposit_tx_hash(
        self,
        *,
        tx_hash: str,
        lookup_addresses: list[str],
        bridge: GlameTokenTransaction,
    ) -> dict[str, Any]:
        config = self.config_payload()
        normalized_hash = self._normalize_hash(tx_hash)
        if not normalized_hash:
            return {
                "ok": False,
                "status": "missing_tx_hash",
                "message": "TON tx hash is required for deposit verification.",
                "config": config,
            }
        if not lookup_addresses:
            return {
                "ok": False,
                "status": "missing_lookup_address",
                "message": "Set TON_GLM_TREASURY_ADDRESS or TON_GLM_SETTLEMENT_LOOKUP_ADDRESSES.",
                "config": config,
            }

        headers = {}
        api_key = (os.getenv("TONCENTER_API_KEY") or "").strip()
        if api_key:
            headers["X-API-Key"] = api_key

        checked: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=config["timeout_seconds"]) as client:
            for address in lookup_addresses:
                try:
                    response = await client.get(
                        f"{config['toncenter_base_url']}/getTransactions",
                        params={
                            "address": address,
                            "limit": config["lookup_limit"],
                            "archival": "true",
                        },
                        headers=headers,
                    )
                    response.raise_for_status()
                    payload = response.json()
                except Exception as error:
                    checked.append({"address": address, "ok": False, "error": str(error)})
                    continue

                transactions = payload.get("result") if isinstance(payload, dict) else None
                if not isinstance(transactions, list):
                    checked.append({"address": address, "ok": False, "error": "Unexpected TON Center response."})
                    continue

                for tx in transactions:
                    if isinstance(tx, dict) and self._hash_matches(tx, normalized_hash):
                        deposit_validation = self._deposit_transaction_validation(
                            tx=tx,
                            bridge=bridge,
                            config=config,
                        )
                        return {
                            "ok": bool(deposit_validation.get("ok")),
                            "status": "verified" if deposit_validation.get("ok") else "deposit_validation_failed",
                            "message": "TON deposit tx hash found in TON Center transactions.",
                            "tx_hash": normalized_hash,
                            "matched_address": address,
                            "transaction_id": tx.get("transaction_id"),
                            "utime": tx.get("utime"),
                            "deposit_validation": deposit_validation,
                            "config": config,
                            "checked": checked,
                        }
                checked.append({"address": address, "ok": True, "transactions_checked": len(transactions)})

        return {
            "ok": False,
            "status": "not_found",
            "message": "TON deposit tx hash was not found in checked TON Center transactions.",
            "tx_hash": normalized_hash,
            "config": config,
            "checked": checked,
        }

    async def settle_glm_to_points_bridge_by_deposit_tx_hash(
        self,
        *,
        bridge_id: UUID,
        tx_hash: str,
        admin_user_id: UUID,
        comment: str | None = None,
        require_verified: bool = True,
    ) -> dict[str, Any]:
        bridge = (
            await self.db.execute(
                select(GlameTokenTransaction).where(
                    GlameTokenTransaction.id == bridge_id,
                    GlameTokenTransaction.transaction_type == "bridge",
                )
            )
        ).scalar_one_or_none()
        if bridge is None:
            raise ValueError("GLM -> баллы bridge не найден")
        if bridge.status != "pending":
            raise ValueError("Можно settlement только pending bridge")

        verification = await self.verify_deposit_tx_hash(
            tx_hash=tx_hash,
            lookup_addresses=self._bridge_deposit_lookup_addresses(bridge),
            bridge=bridge,
        )
        meta = bridge.meta if isinstance(bridge.meta, dict) else {}
        bridge.meta = {
            **meta,
            "deposit_tx_hash": tx_hash,
            "ton_deposit_verification": {
                **verification,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "verified_by": str(admin_user_id),
            },
        }
        flag_modified(bridge, "meta")
        await self.db.flush()
        await GlameTokenService(self.db).sync_bridge_operation(bridge)

        if require_verified and not verification.get("ok"):
            return {
                "status": "blocked",
                "bridge": bridge,
                "verification": verification,
            }

        processed = await GlameTokenService(self.db).update_glm_to_points_bridge_status(
            bridge=bridge,
            status="processed",
            admin_user_id=admin_user_id,
            comment=comment or "TON deposit verified by settlement.",
        )
        return {
            "status": "processed",
            "bridge": processed,
            "verification": verification,
        }

    async def _find_matching_deposit_tx_hash(
        self,
        *,
        bridge: GlameTokenTransaction,
    ) -> dict[str, Any]:
        config = self.config_payload()
        lookup_addresses = self._bridge_deposit_lookup_addresses(bridge)
        if not lookup_addresses:
            return {
                "ok": False,
                "status": "missing_lookup_address",
                "message": "Set TON_GLM_TREASURY_ADDRESS or TON_GLM_SETTLEMENT_LOOKUP_ADDRESSES.",
            }

        min_utime = None
        if bridge.created_at:
            created_at = bridge.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            min_utime = int(created_at.timestamp()) - 300

        headers = {}
        api_key = (os.getenv("TONCENTER_API_KEY") or "").strip()
        if api_key:
            headers["X-API-Key"] = api_key

        checked: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=config["timeout_seconds"]) as client:
            for address in lookup_addresses:
                try:
                    response = await client.get(
                        f"{config['toncenter_base_url']}/getTransactions",
                        params={
                            "address": address,
                            "limit": config["lookup_limit"],
                            "archival": "true",
                        },
                        headers=headers,
                    )
                    response.raise_for_status()
                    payload = response.json()
                except Exception as error:
                    checked.append({"address": address, "ok": False, "error": str(error)})
                    continue

                transactions = payload.get("result") if isinstance(payload, dict) else None
                if not isinstance(transactions, list):
                    checked.append({"address": address, "ok": False, "error": "Unexpected TON Center response."})
                    continue

                for tx in transactions:
                    if not isinstance(tx, dict):
                        continue
                    utime = int(tx.get("utime") or 0)
                    if min_utime is not None and utime and utime < min_utime:
                        continue
                    deposit_validation = self._deposit_transaction_validation(
                        tx=tx,
                        bridge=bridge,
                        config=config,
                    )
                    if not deposit_validation.get("ok"):
                        continue
                    tx_hash = tx.get("hash") or (
                        (tx.get("transaction_id") or {}).get("hash")
                        if isinstance(tx.get("transaction_id"), dict)
                        else None
                    )
                    if not tx_hash:
                        continue
                    return {
                        "ok": True,
                        "status": "matched",
                        "tx_hash": str(tx_hash),
                        "matched_address": address,
                        "transaction_id": tx.get("transaction_id"),
                        "utime": tx.get("utime"),
                        "deposit_validation": deposit_validation,
                        "checked": checked,
                    }
                checked.append({"address": address, "ok": True, "transactions_checked": len(transactions)})

        return {
            "ok": False,
            "status": "not_found",
            "message": "Matching GLM deposit was not found in checked TON Center transactions.",
            "checked": checked,
        }

    async def settle_pending_glm_to_points_bridges(
        self,
        *,
        admin_user_id: UUID,
        limit: int = 50,
        require_verified: bool = True,
    ) -> dict[str, Any]:
        rows = (
            await self.db.execute(
                select(GlameTokenTransaction)
                .where(
                    GlameTokenTransaction.transaction_type == "bridge",
                    GlameTokenTransaction.status == "pending",
                    GlameTokenTransaction.reason.in_(("glm_to_points_bridge", "buy_loyalty_points")),
                )
                .order_by(GlameTokenTransaction.created_at.asc(), GlameTokenTransaction.id.asc())
                .limit(max(int(limit or 1), 1))
            )
        ).scalars().all()

        processed: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for bridge in rows:
            meta = bridge.meta if isinstance(bridge.meta, dict) else {}
            tx_hash = self._bridge_candidate_tx_hash(bridge)
            if not tx_hash:
                match = await self._find_matching_deposit_tx_hash(bridge=bridge)
                if match.get("ok"):
                    tx_hash = str(match.get("tx_hash") or "")
                else:
                    bridge.meta = {
                        **meta,
                        "ton_deposit_status": "waiting_for_deposit",
                        "ton_deposit_last_lookup": {
                            **match,
                            "checked_at": datetime.now(timezone.utc).isoformat(),
                        },
                    }
                    flag_modified(bridge, "meta")
                    await GlameTokenService(self.db).sync_bridge_operation(bridge)
                    skipped.append({
                        "bridge_id": str(bridge.id),
                        "reason": match.get("status") or "missing_candidate_tx_hash",
                    })
                    continue
            try:
                result = await self.settle_glm_to_points_bridge_by_deposit_tx_hash(
                    bridge_id=bridge.id,
                    tx_hash=tx_hash,
                    admin_user_id=admin_user_id,
                    require_verified=require_verified,
                    comment="TON deposit verified by background watcher.",
                )
            except Exception as error:
                blocked.append({
                    "bridge_id": str(bridge.id),
                    "tx_hash": tx_hash,
                    "reason": str(error),
                })
                continue

            if result.get("status") == "processed":
                processed.append({
                    "bridge_id": str(bridge.id),
                    "tx_hash": tx_hash,
                    "verification": result.get("verification"),
                })
            else:
                blocked.append({
                    "bridge_id": str(bridge.id),
                    "tx_hash": tx_hash,
                    "verification": result.get("verification"),
                })

        return {
            "checked": len(rows),
            "processed": processed,
            "blocked": blocked,
            "skipped": skipped,
        }

    async def settle_reward_store_redemption_by_deposit_tx_hash(
        self,
        *,
        redemption_id: UUID,
        tx_hash: str,
        admin_user_id: UUID,
        comment: str | None = None,
        require_verified: bool = True,
    ) -> dict[str, Any]:
        redemption = (
            await self.db.execute(
                select(GlameTokenTransaction).where(
                    GlameTokenTransaction.id == redemption_id,
                    GlameTokenTransaction.transaction_type == "redemption",
                    GlameTokenTransaction.reason == "glm_store_item",
                )
            )
        ).scalar_one_or_none()
        if redemption is None:
            raise ValueError("GLM Store redemption не найден")
        if redemption.status != "pending_ton_payment":
            raise ValueError("Можно settlement только pending TON payment")

        verification = await self.verify_deposit_tx_hash(
            tx_hash=tx_hash,
            lookup_addresses=self._bridge_deposit_lookup_addresses(redemption),
            bridge=redemption,
        )
        meta = redemption.meta if isinstance(redemption.meta, dict) else {}
        redemption.meta = {
            **meta,
            "deposit_tx_hash": tx_hash,
            "ton_deposit_status": "verified" if verification.get("ok") else "verification_failed",
            "ton_deposit_verification": {
                **verification,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "verified_by": str(admin_user_id),
            },
        }
        flag_modified(redemption, "meta")
        await self.db.flush()

        if require_verified and not verification.get("ok"):
            return {
                "status": "blocked",
                "redemption": redemption,
                "verification": verification,
            }

        now = datetime.now(timezone.utc)
        redemption.status = "pending_fulfillment"
        redemption.meta = {
            **(redemption.meta or {}),
            "fulfillment_status": "pending",
            "payment_status": "paid",
            "paid_at": now.isoformat(),
            "processed_by": str(admin_user_id),
            "admin_comment": (comment or "TON GLM deposit verified by settlement.").strip(),
        }
        flag_modified(redemption, "meta")
        await self.db.flush()
        return {
            "status": "processed",
            "redemption": redemption,
            "verification": verification,
        }

    async def settle_pending_reward_store_redemptions(
        self,
        *,
        admin_user_id: UUID,
        limit: int = 50,
        require_verified: bool = True,
    ) -> dict[str, Any]:
        rows = (
            await self.db.execute(
                select(GlameTokenTransaction)
                .where(
                    GlameTokenTransaction.transaction_type == "redemption",
                    GlameTokenTransaction.status == "pending_ton_payment",
                    GlameTokenTransaction.reason == "glm_store_item",
                )
                .order_by(GlameTokenTransaction.created_at.asc(), GlameTokenTransaction.id.asc())
                .limit(max(int(limit or 1), 1))
            )
        ).scalars().all()

        processed: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for redemption in rows:
            meta = redemption.meta if isinstance(redemption.meta, dict) else {}
            tx_hash = self._bridge_candidate_tx_hash(redemption)
            if not tx_hash:
                match = await self._find_matching_deposit_tx_hash(bridge=redemption)
                if match.get("ok"):
                    tx_hash = str(match.get("tx_hash") or "")
                else:
                    redemption.meta = {
                        **meta,
                        "ton_deposit_status": "waiting_for_deposit",
                        "ton_deposit_last_lookup": {
                            **match,
                            "checked_at": datetime.now(timezone.utc).isoformat(),
                        },
                    }
                    flag_modified(redemption, "meta")
                    skipped.append({
                        "redemption_id": str(redemption.id),
                        "reason": match.get("status") or "missing_candidate_tx_hash",
                    })
                    continue
            try:
                result = await self.settle_reward_store_redemption_by_deposit_tx_hash(
                    redemption_id=redemption.id,
                    tx_hash=tx_hash,
                    admin_user_id=admin_user_id,
                    require_verified=require_verified,
                    comment="TON GLM Store payment verified by background watcher.",
                )
            except Exception as error:
                blocked.append({
                    "redemption_id": str(redemption.id),
                    "tx_hash": tx_hash,
                    "reason": str(error),
                })
                continue

            if result.get("status") == "processed":
                processed.append({
                    "redemption_id": str(redemption.id),
                    "tx_hash": tx_hash,
                    "verification": result.get("verification"),
                })
            else:
                blocked.append({
                    "redemption_id": str(redemption.id),
                    "tx_hash": tx_hash,
                    "verification": result.get("verification"),
                })

        return {
            "checked": len(rows),
            "processed": processed,
            "blocked": blocked,
            "skipped": skipped,
        }

    async def settle_pending_claims(
        self,
        *,
        admin_user_id: UUID,
        limit: int = 50,
        require_verified: bool = True,
    ) -> dict[str, Any]:
        rows = (
            await self.db.execute(
                select(GlameTokenTransaction)
                .where(
                    GlameTokenTransaction.transaction_type == "claim",
                    GlameTokenTransaction.status == "pending",
                )
                .order_by(GlameTokenTransaction.created_at.asc(), GlameTokenTransaction.id.asc())
                .limit(max(int(limit or 1), 1))
            )
        ).scalars().all()

        processed: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for claim in rows:
            tx_hash = self._candidate_tx_hash(claim)
            if not tx_hash:
                skipped.append({
                    "claim_id": str(claim.id),
                    "reason": "missing_candidate_tx_hash",
                })
                continue
            try:
                result = await self.settle_claim_by_tx_hash(
                    claim_id=claim.id,
                    tx_hash=tx_hash,
                    admin_user_id=admin_user_id,
                    require_verified=require_verified,
                    comment="TON settlement background watcher.",
                )
            except Exception as error:
                blocked.append({
                    "claim_id": str(claim.id),
                    "tx_hash": tx_hash,
                    "reason": str(error),
                })
                continue

            if result.get("status") == "processed":
                processed.append({
                    "claim_id": str(claim.id),
                    "tx_hash": tx_hash,
                    "verification": result.get("verification"),
                })
            else:
                blocked.append({
                    "claim_id": str(claim.id),
                    "tx_hash": tx_hash,
                    "verification": result.get("verification"),
                })

        bridge_result = await self.settle_pending_glm_to_points_bridges(
            admin_user_id=admin_user_id,
            limit=limit,
            require_verified=require_verified,
        )
        reward_store_result = await self.settle_pending_reward_store_redemptions(
            admin_user_id=admin_user_id,
            limit=limit,
            require_verified=require_verified,
        )

        return {
            "checked": len(rows),
            "processed": processed,
            "blocked": blocked,
            "skipped": skipped,
            "glm_to_points": bridge_result,
            "reward_store": reward_store_result,
        }
