# CryptoGLAME Security Review Checklist

Updated: 2026-07-07

This checklist is the production security gate for CryptoGLAME before public mainnet launch.
It is not a legal approval. It is an operator/security checklist for TON Connect, GLM Jetton,
external signer, bridge, treasury and incident controls.

## Review status

Public mainnet launch is blocked until:

- all Critical items are closed;
- High items are closed or have an approved temporary mitigation;
- legal/accounting/treasury approvals are recorded separately;
- a small-amount mainnet smoke test is repeated after the final config change.

## 1. TON Connect and ton_proof

Critical checks:

- TON Connect manifest domain is the production domain used by partners.
- Backend verifies `ton_proof` server-side and does not trust frontend-only wallet state.
- Proof challenge is single-use or short-lived and bound to the authenticated partner session.
- The verified wallet address stored for the partner is the address used for bridge and GLM Store flows.
- Manual wallet address entry does not grant `verified` status.

High checks:

- Reconnect flow invalidates stale challenge/proof state.
- UI clearly shows the currently verified wallet and wallet app label.
- Network mismatch is visible before creating TON requests.
- Wallet disconnect/reconnect cannot reuse another partner's challenge.

Evidence to capture:

- screenshot of verified wallet state;
- backend log/request id for a successful proof verification without secret payload;
- failed proof attempt with wrong address or expired challenge.

## 2. Bridge replay and idempotency

Critical checks:

- `points_to_glm` cannot send GLM before 1C spend is successful or explicitly approved as manual recovery.
- `points_to_glm` settlement cannot mark processed without a TON tx hash or approved legacy/manual marker.
- `glm_to_points` cannot credit 1C points without a verified TON deposit to GLAME treasury.
- A TON tx hash can be attached to only one bridge/store/refund operation.
- Re-running settlement/auto-transfer does not double-send GLM or double-credit 1C points.

High checks:

- Bridge operations have a stable domain row in `glame_token_bridge_operations`.
- Legacy ledger transactions and bridge-domain rows are reconciled.
- Canceled operations with already-sent TON transfer require explicit recovery path.
- Failed/canceled 1C spend creates an admin alert or reconciliation issue.

Evidence to capture:

- bridge reconciliation CSV export;
- `/api/referrals/admin/glm-replay-idempotency-audit` result or `/admin/crypto` Replay audit screenshot;
- one repeated settlement run showing no duplicate state transition;
- one failed/canceled operation reviewed through admin action flow.

## 3. External signer and hot-wallet

Critical checks:

- Production backend runtime does not store a production hot-wallet seed phrase or private key.
- Backend sends only `glame_ton_jetton_transfer_intent_v1` to the signer.
- Signer validates auth token, network, Jetton master, hot-wallet address, amount and recipient.
- Signer rejects requests above per-transaction and daily limits.
- Emergency pause works without deploy and returns a visible health state.

High checks:

- Signer token is not the Toncenter API key.
- Signer health endpoint does not reveal secrets.
- Signer logs do not include mnemonic, private key, bearer token or raw secret material.
- Mainnet smoke test is repeated after changing signer env or Jetton master.

Evidence to capture:

- `/api/referrals/admin/glm-production-signer/check` result;
- signer `/health` result with emergency pause state;
- rejected over-limit request;
- rejected request with wrong bearer token.

## 4. Treasury, refill and approvals

Critical checks:

- Treasury/bank wallet and hot-wallet addresses are recorded in readiness.
- Treasury refill uses TON Connect/manual admin flow, not backend auto-signing from treasury.
- Large refill requires two-step approval before TON Connect payload is prepared.
- Hot-wallet balance thresholds and TON gas thresholds are configured.
- Low-balance alerts go to admin Telegram and link to the production portal.

High checks:

- Refill journal records manual/TON Connect refill events.
- Treasury turnover CSV export is available.
- Refill plan cannot use stale approval for a changed amount/address/network.
- Refund flow records tx hash and settlement status.

Evidence to capture:

- readiness screenshot with treasury/hot-wallet balances;
- approved `refill_approval` row;
- treasury turnover CSV export;
- Telegram low-balance alert sample.

## 5. GLM Store and refunds

Critical checks:

- GLM Store TON checkout verifies recipient treasury, Jetton master, amount and tx uniqueness.
- Fulfillment can only close after payment is verified or an approved manual correction exists.
- Refund recipient is the original verified wallet unless explicitly escalated.
- Canceled paid orders create refund-required visibility.

High checks:

- Inventory quantity reservation is not duplicated on retry.
- Admin refund action records tx hash and comment.
- Treasury turnover shows incoming GLM Store payments and outgoing refunds.

Evidence to capture:

- one paid order lifecycle: pending payment -> pending fulfillment -> fulfilled;
- one canceled paid order with refund-required status;
- verified refund tx settlement.

## 6. Secrets, logs and UI exposure

Critical checks:

- UI never displays seed phrases, private keys, signer tokens, Toncenter keys, Telegram bot token or 1C credentials.
- Backend logs do not print Authorization headers or secret env values.
- Cloudflare Worker secrets are stored as secrets, not plaintext variables, where Cloudflare supports it.
- Git repository does not contain live production secrets.

High checks:

- Admin pages show only boolean flags for secret configured/missing.
- Error messages are actionable but do not include raw secret payloads.
- Export files do not include secret values.

Evidence to capture:

- grep/security scan output for known secret key names;
- `python3 scripts/security/check_referrals_admin_routes.py` output for admin route protection;
- screenshots of readiness secret flags;
- sample failed signer request without secret leakage.

## 7. Mainnet go/no-go

Before public launch, attach these artifacts to the internal launch decision:

- latest `/admin/crypto` readiness screenshot;
- bridge reconciliation CSV;
- treasury turnover CSV;
- signer health/preflight result;
- token verification/anti-spam package status;
- legal/accounting approval;
- treasury policy approval;
- security approval with this checklist signed off.

If any Critical item is open, public launch remains blocked.
