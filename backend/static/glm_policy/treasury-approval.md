# CryptoGLAME Treasury Approval

Status: approval template for production sign-off  
Updated: 2026-07-07

This document defines the treasury approval required before public CryptoGLAME mainnet usage.

## Scope

The approval covers:

- treasury/bank wallet role;
- hot-wallet role;
- refill and low-balance thresholds;
- transfer limits;
- two-step approvals;
- burn/refund/manual recovery policy;
- incident response for treasury operations.

## Wallet Roles

| Role | Purpose | Signing model |
| --- | --- | --- |
| Treasury/bank wallet | Holds primary GLM reserve, receives GLM Store and `glm_to_points` deposits, funds hot-wallet refill. | Manual TON Connect or separately approved treasury signer. Backend auto-signing is not allowed. |
| Hot-wallet | Sends GLM to verified partner wallets for `points_to_glm` and controlled automated payouts. | External signer with strict limits, auth token, emergency pause and monitoring. |
| Partner wallet | Receives GLM and sends GLM for store/bridge scenarios. | User-controlled TON Connect wallet. |

## Approved Mainnet Operating Rules

- Hot-wallet target GLM balance: `5000 GLM`.
- Low-balance alert threshold: below `5000 GLM`.
- Fixed refill amount: `5000 GLM`, unless a specific incident plan says otherwise.
- Hot-wallet TON gas minimum: `0.5 TON`.
- Hot-wallet TON gas target: `2 TON`.
- Treasury TON gas minimum: `0.2 TON`.
- Refill alerts go to admin Telegram and link to `https://portal.glamejewelry.ru/admin/referrals`.
- Large treasury/refill actions require two-step approval before TON Connect payload is prepared.

## Signer Limits

The production signer must enforce:

- maximum GLM per transfer;
- daily GLM cap;
- hourly GLM cap;
- minimum seconds between transfers;
- correct TON network;
- correct Jetton master;
- correct hot-wallet address;
- valid signer token;
- emergency pause.

The signer must not expose seed phrases, private keys, bearer tokens or raw Toncenter keys in responses or logs.

## Refill Procedure

Normal refill:

1. Operator opens `/admin/crypto`.
2. Operator checks hot-wallet GLM/TON gas and treasury GLM/TON gas.
3. If below threshold, operator uses the refill plan.
4. For small approved refill, operator sends from treasury to hot-wallet through TON Connect and records the result.
5. For large refill, operator requests two-step approval, waits for approval, then sends.
6. Operator runs balance check and confirms readiness returns to OK.

Backend must not automatically sign treasury/bank wallet transactions in the current production model.

## Refund and Recovery

Refunds require:

- original operation reference;
- refund reason;
- verified recipient wallet;
- amount;
- TON tx hash after execution;
- operator comment.

If 1C points were spent but GLM was not sent, the approved recovery path is retry transfer or explicit 1C reversal. If GLM was already sent, the operation must not be canceled as if nothing happened.

## Burn and Reuse

Returned GLM may be:

- held in treasury for future utility operations;
- reserved for refunds or corrections;
- burned only after separate written treasury/accounting/legal approval.

No burn campaign may be marketed as price support or investment mechanics.

## Required Evidence

Attach or capture:

- current readiness screenshot with treasury/hot-wallet balances;
- signer `/health` and preflight check;
- hot-wallet limits screenshot or config export;
- treasury turnover CSV;
- refill journal sample;
- Telegram low-balance alert sample;
- incident escalation policy;
- successful small mainnet smoke test tx.

## Sign-Off

Treasury owner approval:

- approver:
- date:
- comment:

Finance owner approval:

- approver:
- date:
- comment:

Operations owner approval:

- approver:
- date:
- comment:

Public launch may proceed only if treasury roles, limits, refill, refund and incident procedures are approved.
