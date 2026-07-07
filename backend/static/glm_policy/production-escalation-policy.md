# CryptoGLAME Production Escalation Policy

Updated: 2026-07-07

This policy defines when CryptoGLAME operators escalate production incidents, which channel is used and what actions are allowed before public mainnet launch.

It complements the operator runbook. The runbook explains how to investigate and resolve an issue; this policy explains severity, timing and escalation ownership.

## Severity levels

### Critical

Escalate immediately in Telegram admin alerts and pause the affected automated flow if user funds, GLM supply, 1C balances or treasury funds may be at risk.

Examples:

- GLM was sent on-chain but the platform cannot settle or reconcile the operation.
- 1C points were debited but GLM transfer cannot be sent or retried safely.
- A bridge/store/refund tx hash appears reused by more than one operation.
- Hot-wallet GLM or TON gas is insufficient for pending `points_to_glm` operations.
- Treasury or hot-wallet balance check returns inconsistent or impossible values.
- External signer is unhealthy while pending outgoing operations exist.
- Secret leakage is suspected in logs, UI, repo, screenshots or exports.

Required action:

1. Pause affected automation if available.
2. Preserve operation IDs, tx hashes, wallet addresses, screenshots and export files.
3. Notify admin Telegram immediately.
4. Do not perform corrective transfer/refund without operator note and approval path.

### Warning

Escalate through admin Telegram, but automation may continue if the issue is bounded and no double-spend/double-credit risk exists.

Examples:

- Toncenter is unavailable for one or more checks, but balances were healthy recently.
- Bridge operation is pending longer than the configured stale window.
- 1C retry has temporary failures.
- Hot-wallet drops below refill threshold but still has enough GLM/TON for pending operations.
- Token verification/anti-spam status is not yet applied in wallets.

Required action:

1. Add operator note if the issue affects a specific partner/order.
2. Re-run readiness/reconciliation after the next scheduler cycle.
3. Escalate to Critical if the warning remains unresolved beyond the time limits below.

### Info

Visible in admin UI or digest. No immediate action required.

Examples:

- Refill completed and readiness returned to OK.
- Bridge reconciliation has no issues.
- Daily treasury export was generated.

## Time limits

| Scenario | Warning threshold | Critical threshold |
| --- | ---: | ---: |
| Toncenter outage | 10 minutes | 30 minutes or pending funds impacted |
| Hot-wallet below refill threshold | Immediate warning | 60 minutes without refill record or pending operations blocked |
| Bridge pending without TON/1C progress | 2 hours | 24 hours or user complaint |
| GLM sent, settlement not closed | Immediate warning | 30 minutes |
| 1C retry failures | 15 minutes | 60 minutes or balance mismatch |
| Refund required | Immediate warning | 24 hours without refund decision |
| Secret exposure suspicion | Critical immediately | Critical immediately |

## Channels

Primary channel:

- Admin Telegram bot alerts.

Admin action URLs:

- Crypto dashboard: `https://portal.glamejewelry.ru/admin/crypto`
- Partner/referral dashboard: `https://portal.glamejewelry.ru/admin/referrals`

Evidence channels:

- Export `bridge reconciliation CSV`.
- Export `treasury turnover CSV`.
- Capture readiness screenshot.
- Record TON tx hash and operation ID in admin comments.

## Toncenter outage

If Toncenter is unavailable:

1. Do not mark TON-dependent operations as processed from UI state alone.
2. Keep pending operations pending unless a verified on-chain tx hash is available through an alternate explorer/API and operator approval.
3. Pause settlement if repeated API errors could create duplicate retries.
4. Resume only after a successful readiness check and one manual verification of an affected tx.

Escalate to Critical if:

- outgoing GLM has already been sent and settlement cannot verify it;
- GLM Store paid order depends on the unavailable tx;
- balances cannot be checked while hot-wallet is near threshold.

## Balance gaps

Balance gap means platform expected balances, on-chain GLM/TON balances or 1C balances disagree.

Critical balance gaps:

- platform points differ from 1C "К списанию";
- hot-wallet safe GLM capacity is below pending outgoing amount;
- treasury GLM is below required refill plus buffer;
- on-chain balance shows lower amount than expected after a recorded transfer.

Required action:

1. Stop any automation that can worsen the gap.
2. Export treasury turnover and bridge reconciliation.
3. Identify last successful operation before the gap.
4. Resolve by settlement/retry/reversal according to operator runbook.

Do not mass-edit 1C documents or on-chain records to make numbers look aligned.

## Bridge stuck states

Escalate `points_to_glm` to Critical when:

- 1C spend succeeded but TON transfer failed or signer is unavailable;
- TON transfer was sent but settlement cannot attach tx hash;
- operation was canceled after 1C spend or TON transfer.

Escalate `glm_to_points` to Critical when:

- verified TON deposit exists but 1C credit fails repeatedly;
- same TON tx hash is seen on multiple operations;
- sender wallet does not match verified wallet and manual approval was not recorded.

## GLM Store and refunds

Escalate GLM Store payment to Critical when:

- payment tx is valid but order remains pending;
- order is fulfilled without verified payment;
- refund is required but recipient wallet differs from original payer.

Refunds must include:

- original operation ID;
- refund reason;
- recipient wallet;
- refund tx hash;
- operator/admin comment.

## Signer incidents

Escalate signer incident to Critical when:

- `/health` is down and pending outgoing operations exist;
- signer returns success without tx hash;
- signer signs an unexpected Jetton master, amount or recipient;
- auth token or mnemonic exposure is suspected.

Allowed immediate action:

- enable signer emergency pause;
- pause backend auto-transfer;
- rotate signer token after preserving incident evidence.

## Escalation close-out

An incident can be closed only after:

- affected operations have final status or documented manual recovery path;
- balances are rechecked;
- bridge reconciliation has no new Critical issue for the incident;
- admin Telegram alert state is no longer active or has a clear follow-up note;
- the root cause and corrective action are recorded in operator comments or internal notes.

## Public mainnet rule

Public launch remains blocked while any Critical escalation is open or while security/legal/treasury approval gates are incomplete.
