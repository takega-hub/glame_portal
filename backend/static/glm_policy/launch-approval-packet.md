# CryptoGLAME Launch Approval Packet

Status: final public mainnet launch packet  
Updated: 2026-07-07

This packet lists the artifacts required to move CryptoGLAME from controlled mainnet technical pilot to public partner usage.

## Current Technical State

- GLM Jetton is deployed in TON mainnet.
- Primary bank mint is complete.
- Treasury/bank wallet and hot-wallet are configured.
- External Cloudflare signer is connected for hot-wallet transfers.
- `points_to_glm`, `glm_to_points`, GLM Store and Reward Store flows are implemented.
- Admin CryptoGLAME readiness, treasury balances, replay audit, bridge reconciliation and Telegram alerts are implemented.
- Tonkeeper asset-list PR is submitted: `https://github.com/tonkeeper/ton-assets/pull/5779`.

## Public Launch Blockers

Public launch remains blocked until all of these are complete:

- legal/accounting approval;
- KYC/AML and anti-fraud approval;
- security sign-off;
- treasury approval;
- final production regression;
- token verification propagation or an explicit decision to launch while wallets still show GLM as unverified/spam;
- evidence archive saved.

## Required Documents

| Document | Location | Status before launch |
| --- | --- | --- |
| Token Policy | `/static/glm_policy/token-policy.md` | Must be final. |
| Risk Disclosure | `/static/glm_policy/risk-disclosure.md` | Must be final. |
| Bridge Rules | `/static/glm_policy/bridge-rules.md` | Must be final. |
| Emission and Anti-Farm Policy | `/static/glm_policy/emission-policy.md` | Must be final. |
| Operator Runbook | `/static/glm_policy/operator-runbook.md` | Must be final. |
| Security Review Checklist | `/static/glm_policy/security-review-checklist.md` | Must be signed off. |
| Legal and Accounting Approval | `/static/glm_policy/legal-accounting-approval.md` | Must be signed off. |
| Treasury Approval | `/static/glm_policy/treasury-approval.md` | Must be signed off. |
| Production Signer Contract | `/static/glm_policy/production-signer-contract.md` | Must match deployed signer behavior. |
| Escalation Policy | `/static/glm_policy/production-escalation-policy.md` | Must be final. |

## Evidence Checklist

Capture and archive:

- `/admin/crypto` readiness screenshot after final config;
- signer health/preflight result;
- `python3 scripts/security/run_crypto_glame_launch_checks.py` output;
- `python3 scripts/security/build_crypto_glame_evidence_packet.py --skip-live --write <private-path>` output; do not publish this packet under `/backend/static`;
- `/api/referrals/admin/glm-launch-evidence` result or `/admin/crypto` Launch evidence screenshot;
- admin route audit output;
- secret exposure scan output;
- replay/idempotency audit output;
- bridge reconciliation CSV;
- treasury turnover CSV;
- hot-wallet/treasury balance snapshot;
- small `points_to_glm` mainnet E2E operation;
- small `glm_to_points` mainnet E2E operation;
- GLM Store checkout/fulfillment or checkout/refund operation;
- 1C movement report for the same operations;
- Tonkeeper/asset verification status.

## Go/No-Go Decision

Launch decision:

- date:
- decision: go / no-go
- launch mode: controlled public beta / public partner rollout / delayed
- approver:
- comment:

If any Critical item is open in security, legal/accounting, treasury or reconciliation, the decision must be `no-go`.

## Post-Launch Monitoring

For the first production period:

- check `/admin/crypto` daily;
- monitor Telegram critical alerts immediately;
- review bridge and treasury CSV daily;
- keep hot-wallet above approved threshold;
- do not enable DEX/P2P/listing without a separate approval packet.
