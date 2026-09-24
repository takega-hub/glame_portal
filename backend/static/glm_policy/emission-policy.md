# GLM Emission and Anti-Farm Policy

Status: production approval draft  
Updated: 2026-07-07

This document explains how GLAME controls GLM issuance and utility so GLM cannot be farmed endlessly through artificial purchases, referral abuse or repeated bridge loops.

## 1. Token Supply

GLM mainnet supply starts from an approved bank mint held by the GLAME treasury/bank wallet.

New minting is not a per-user operation. User actions such as `points_to_glm`, referral rewards, GLM Store purchases and `glm_to_points` should normally move existing GLM between treasury, hot-wallets and user wallets.

Any additional mint must require a separate treasury approval record with:

- reason;
- amount;
- destination wallet;
- expected utility budget;
- approver;
- date;
- transaction hash after execution.

## 2. Reward Budget

Referral GLM is earned only for confirmed referral purchases under active campaign rules.

GLAME may set:

- monthly referral emission limits;
- partner-level earning caps;
- hold periods before release;
- return and cancellation windows;
- manual review for abnormal activity;
- campaign-specific budgets.

Rewards are not final until fraud, return and accounting checks are complete.

## 3. Loyalty Bridge Limits

1C loyalty points and GLM are separate entities connected only by approved bridge operations.

The `points_to_glm` bridge does not create unlimited value. It spends eligible 1C loyalty points and sends GLM from the approved operational wallet. The operation is limited by:

- available 1C points;
- per-operation minimum and maximum;
- monthly partner limits;
- hot-wallet balance;
- treasury policy;
- 1C reconciliation state;
- anti-fraud checks.

The reverse `glm_to_points` bridge requires an actual TON transfer to GLAME treasury before points are issued.

## 4. Purchase And Return Controls

GLM is connected to real GLAME retail activity, but this is utility support, not a price guarantee.

To prevent circular farming:

- points from canceled or returned purchases may be reversed;
- referral rewards can be held until purchase confirmation;
- suspicious repeated self-referrals, linked accounts, refund loops or same-wallet loops can be blocked;
- GLM Store purchases can require TON transaction settlement before fulfillment;
- refund operations must be linked to a verified original transaction.

## 5. Treasury And Hot-Wallet Controls

The hot-wallet is an operational wallet for small automatic transfers. It must stay within approved limits and refill rules.

Treasury/bank wallet funds are not automatically exposed to user requests. Large refills, mint operations and incident recovery require the approved treasury process.

## 6. No Investment Promise

GLM utility may grow if more GLAME services, partner mechanics, store items and bridge scenarios use GLM.

This does not mean GLAME promises:

- market price growth;
- a fixed external exchange rate;
- buyback;
- liquidity;
- exchange listing;
- profit;
- redemption in fiat or USDT.

GLM is a utility token for approved GLAME scenarios, with limits, holds, reconciliation and compliance controls.
