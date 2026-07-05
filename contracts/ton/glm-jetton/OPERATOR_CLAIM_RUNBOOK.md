# GLM TON Testnet Claim Operator Runbook

Status: draft operator workflow  
Scope: pending GLM claims -> TON testnet mint/transfer -> GLAME tx hash

## Purpose

This runbook connects the existing GLAME pending claim queue with manual TON testnet operations.

It does not enable mainnet withdrawals, cash-out, DEX trading or buyback.

## Inputs

Admin export:

`/api/referrals/admin/glm-claims/ton-operator.csv?status=pending&limit=1000`

Each row includes:

- `claim_id`;
- `amount_glm`;
- `wallet_address`;
- `ton_network`;
- `jetton_master_address`;
- `treasury_address`;
- `metadata_url`.

## Local Preflight

From this directory:

```bash
npm run validate:env
npm run mint:prepare -- --destination EQ... --amount 10
npm run mint:prepare-claim -- --csv ./pending-claims.csv
npm run mint:status -- --destination EQ...
npm run prepare:claims -- ./pending-claims.csv
```

The preflight validates readiness and produces operation plans. `mint:prepare` generates a narrow GLM-only mint script, and `mint:prepare-claim` fills it from the operator CSV. Neither command sends a transaction by itself. Integer GLM amounts are converted to TON base units with `decimals = 9`.

## Operator Steps

1. Open admin GLM claim queue.
2. Export `TON CSV` for pending claims.
3. Check that each row has:
   - positive `amount_glm`;
   - verified destination wallet;
   - testnet network;
   - Jetton master address after deployment.
4. Prepare and execute a GLM-only mint operation. If `--claim-id` is omitted, the first pending row is used:
   ```bash
   npm run mint:prepare-claim -- --csv ./pending-claims.csv --claim-id ...
   cd vendor/ton-blockchain-jetton-contract
   npx blueprint run mintGlmJetton --custom https://testnet.toncenter.com/api/v2/jsonRPC --custom-version v2 --custom-type testnet
   ```
5. Copy TON transaction hash.
6. In GLAME admin, paste tx hash into `TON tx hash`.
7. Mark the claim as `Processed`.
8. If mint/transfer fails, mark claim as `Failed` or `Canceled`; GLAME ledger refunds internal GLM for failed/canceled claim.

## Idempotency

One `claim_id` must map to exactly one successful TON transaction hash.

Never process the same pending claim twice. If uncertain, check TON explorer and GLAME claim status before retrying.

## Failure Handling

- No tx sent: mark `Failed` or `Canceled` to refund GLM.
- Tx sent but pending on TON: wait; do not mark processed until tx hash is final enough for pilot.
- Wrong wallet or amount: escalate, do not create a second compensating tx without written approval.
- Missing Jetton master address: do not process; deployment is not ready.

## Mainnet Gate

Mainnet claim processing remains blocked until legal, security and treasury approval.
