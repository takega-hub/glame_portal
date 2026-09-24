# CryptoGLAME P2P Marketplace Approval Packet

Status: draft for future gate
Updated: 2026-07-18

This packet defines the safe path for adding a controlled GLM marketplace after the current mainnet pilot. It does not approve public DEX listing, guaranteed liquidity, GLAME buyback, investment promotion or fixed external price support.

## Scope

Allowed first scope:

- verified CryptoGLAME partners only;
- GLM listed for sale by a partner and bought by another verified partner;
- GLM moves on-chain between TON wallets or through a controlled escrow wallet after both sides confirm the trade;
- platform records listing, trade, TON tx hashes, fees, disputes and review decisions;
- GLAME may charge a transparent marketplace fee after legal/accounting approval.

Out of scope for this gate:

- public DEX pool;
- USDT cash-out promise;
- GLAME guaranteed buyback;
- guaranteed price floor;
- investment language;
- anonymous users;
- unlimited transfers;
- automatic fiat settlement outside approved accounting flow.

## Recommended MVP Order

1. **Observation-only marketplace**
   - show public demand indicators without enabling trades;
   - collect interest: wanted amount, acceptable price range, verified wallet;
   - no asset movement.

2. **Manual brokered pilot**
   - admin matches seller and buyer manually;
   - both sides are verified partners;
   - GLM transfer and TON/payment evidence are checked by operator;
   - marketplace fee is recorded manually;
   - all trades have admin review before completion.

3. **Escrow pilot**
   - seller sends GLM to GLAME escrow;
   - buyer sends consideration using approved method;
   - GLAME releases GLM to buyer after checks;
   - refunds and disputes follow a written runbook.

4. **Automated marketplace**
   - only after legal/security/treasury approval of the escrow and settlement model;
   - requires anti-fraud scoring, limits, fee accounting, replay audit and incident controls.

5. **DEX/listing**
   - separate approval packet;
   - separate liquidity policy;
   - separate public wording review.

## Starting Parameters

Recommended conservative defaults:

| Parameter | Draft value |
| --- | --- |
| Eligible users | verified partners only |
| Minimum trade | 100 GLM |
| Max trade without manual enhanced review | 1 000 GLM |
| Daily user limit | 5 000 GLM |
| Monthly user limit | 50 000 GLM |
| Marketplace fee | 1-2% draft, final value after accounting approval |
| Settlement | manual evidence first, escrow second |
| Price display | user-selected price; no GLAME guaranteed price |
| KYC trigger | suspicious activity, high velocity, large cumulative volume or compliance request |

## Required Controls

- verified TON wallet with `ton_proof` and `walletStateInit` verification;
- wallet address lock for the trade;
- stable idempotency key per listing/trade;
- unique TON tx hash checks;
- manual review queue for stale, disputed or high-risk trades;
- audit log for every operator action;
- Telegram alerts for high-value, stale or suspicious trades;
- clear user disclosure that market price can differ from internal GLAME reference;
- no automatic 1C bonus changes from P2P/DEX trades.

## Data Model Draft

Suggested tables:

- `glame_token_marketplace_listings`
  - seller member/user/account;
  - seller TON wallet;
  - amount GLM;
  - asking price and currency;
  - status: `draft`, `listed`, `reserved`, `matched`, `canceled`, `expired`, `completed`, `disputed`;
  - limits snapshot and policy version;
  - metadata.

- `glame_token_marketplace_trades`
  - listing id;
  - buyer member/user/account;
  - buyer TON wallet;
  - amount GLM;
  - agreed price and currency;
  - fee amount;
  - seller GLM tx hash;
  - buyer payment tx/reference;
  - escrow tx hashes, if escrow is used;
  - status: `pending_payment`, `pending_glm`, `under_review`, `settled`, `refunded`, `failed`, `disputed`;
  - operator decision trail.

## Accounting Questions Before Enabling

- fee treatment and VAT/tax handling;
- whether GLAME is broker, marketplace operator, escrow agent or principal;
- required user documents and public wording;
- reporting period and export format;
- handling of failed, reversed or disputed trades;
- thresholds for mandatory manual review.

## Security Questions Before Enabling

- escrow wallet custody and signer model;
- maximum loss per incident;
- replay/idempotency across listing/trade/refund;
- wallet substitution prevention;
- anti-fraud velocity rules;
- emergency pause and incident response;
- public/private log redaction.

## Go/No-Go Checklist

- legal approval for P2P marketplace model;
- accounting approval for fee and reporting;
- security approval for escrow/signing model;
- treasury approval for escrow wallet, limits and runbook;
- public wording approved without investment claims;
- pilot limits configured;
- admin queue and replay audit ready;
- one internal dry-run trade completed;
- one small verified-partner trade completed.

Until this checklist is complete, P2P/marketplace must stay disabled.
