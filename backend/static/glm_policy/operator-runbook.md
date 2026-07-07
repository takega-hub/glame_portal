# CryptoGLAME Operator Runbook

This runbook is for GLAME operators handling CryptoGLAME testnet and future mainnet incidents.

## Safety rules

Never request or store a user's seed phrase, private key, wallet password, Telegram code, or one-time password.

Use only public wallet addresses, TON transaction hashes, operation IDs and partner identifiers.

For production, do not run hot-wallet or treasury signing from a plain seed phrase in backend runtime env. Use the approved signer mode and limits.

## Daily checks

1. Open `https://portal.glamejewelry.ru/admin/crypto`.
2. Check TON readiness:
   - network;
   - hot-wallet GLM;
   - hot-wallet TON gas;
   - treasury GLM;
   - treasury TON gas;
   - auto-transfer status;
   - settlement status;
   - 1C retry status.
3. If hot-wallet is below target, use the refill plan and record the refill transaction.
4. Check bridge health, store queue, refund queue and 1C reconciliation.

## Points to GLM

Normal state:

1. Partner creates "points -> GLM".
2. Platform debits 1C points using the approved 1C spend path.
3. Auto-transfer sends GLM from hot-wallet to the verified TON wallet.
4. Settlement writes the TON tx hash and closes the operation.

If the operation is waiting:

1. Check that the partner has a verified TON Connect wallet.
2. Check 1C reconciliation and confirm points were debited or not debited.
3. Check hot-wallet GLM and TON gas.
4. If auto-transfer is paused, resume only after the cause is fixed.
5. If GLM was sent but settlement did not close the operation, search by recipient wallet, amount and timestamp.

Cancellation rule:

- If points were not debited and GLM was not sent, cancel the operation.
- If points were debited but GLM was not sent, either retry transfer or perform the approved 1C reversal path.
- If GLM was already sent, do not cancel as if nothing happened; resolve through settlement or a separate corrective operation.

## GLM to points

Normal state:

1. Partner creates "GLM -> points".
2. Partner confirms TON transfer from the verified wallet to GLAME treasury.
3. Watcher finds the TON transaction.
4. 1C points are credited.
5. Operation is marked processed.

If the user says they paid but points did not arrive:

1. Ask for TON tx hash and sender wallet address.
2. Verify recipient is the GLAME treasury wallet shown in the interface.
3. Verify amount, Jetton master and network.
4. If TON tx is valid, trigger settlement/retry 1C.
5. If 1C is unavailable, leave the operation in retry queue and add an operator comment.

Do not mark the operation processed without a verified TON tx or approved manual correction.

## GLM Store payments

Normal state:

1. Partner chooses an item.
2. For GLM payment, TON Connect sends GLM to treasury.
3. Watcher confirms payment.
4. Order moves to fulfillment queue.
5. Operator ships/provides the item and marks it fulfilled.

If payment is stuck:

1. Verify tx hash, amount, Jetton master and treasury recipient.
2. Check if the same tx hash is already attached to another order.
3. If valid and unmatched, attach it through the approved settlement action.
4. If invalid or underpaid, keep the order pending/failed and leave a comment.

## Refunds

Refund only through the approved admin flow.

1. Confirm refund reason and original operation.
2. Confirm the refund recipient wallet.
3. Send refund from the approved treasury/hot-wallet flow.
4. Record tx hash.
5. Verify settlement status after the transaction appears on-chain.

Never refund to a different wallet without explicit approved escalation.

## Hot-wallet refill

Use refill when readiness shows hot-wallet GLM or TON gas below safe limits.

1. Open the refill plan in TON readiness.
2. Confirm source treasury wallet and target hot-wallet.
3. Send only the required GLM/TON amount.
4. Record tx hash in the manual refill journal if the flow requires it.
5. Press balance check and confirm status returns to OK or Ready.

Automatic treasury refill remains disabled until production signer, limits and approval policy are approved.

## 1C reconciliation

For CryptoGLAME, the working points source is 1C "К списанию".

If the 1C card form, lot report and platform disagree:

1. Trust "К списанию" for available points.
2. Use the reconciliation block to compare platform, 1C working balance and lot diagnostics.
3. Do not mass-delete 1C documents in production.
4. For old test documents, prepare a separate cleanup list with before/after screenshots and approval.

## Mainnet go/no-go

Mainnet can be enabled only when all are true:

- production treasury and hot-wallet are approved;
- signer does not use a seed phrase in runtime env;
- `TON_GLM_PRODUCTION_SIGNER_ENDPOINT` is connected and accepts `glame_ton_jetton_transfer_intent_v1`;
- per-transaction and daily limits are configured;
- emergency pause works without deploy;
- public policy, FAQ, risk disclosure and accounting model are approved;
- security review has no open critical findings;
- a small-amount mainnet smoke test plan is approved.
