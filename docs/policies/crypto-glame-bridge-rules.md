# CryptoGLAME Bridge Rules Draft

Status: internal/public draft for legal review  
Last updated: 2026-07-02

## 1. Entities

1C loyalty points and GLM are separate entities connected by approved bridge operations.

- 1C loyalty points are stored in 1C; GLAME Platform synchronizes balances and initiates approved 1C debit/credit operations.
- GLM is intended to be held in the user's TON wallet as a Jetton.
- GLAME Platform keeps an operational ledger for requests, reserves, audit trail, transaction hashes and reconciliation. The platform ledger is not the target GLM wallet.
- Physical GLAME stores do not accept GLM directly in the pilot model. In-store purchases use ordinary 1C loyalty points; GLM can be bridged to points before the purchase.

## 2. Points to GLM

`points_to_glm` lets a customer transfer available 1C loyalty points to GLM before points expire.

Current MVP rules:

- reference rate: 1 loyalty point -> 1 GLM;
- operation minimum: 100 points;
- operation maximum: 10,000 points;
- monthly limit: 50,000 GLM;
- points are debited/reserved in 1C/loyalty ledger;
- GLM is sent to the user's verified TON wallet or placed into a pending TON withdrawal queue until operator/automated settlement;
- GLAME ledger records the request, limits, reserve, TON transaction hash and audit trail;
- operation may be blocked for fraud, technical inconsistency or insufficient balance.

## 3. GLM to Points

`glm_to_points` lets a customer send GLM to GLAME treasury/escrow and request 1C loyalty points.

Current MVP rules:

- reference rate: 1 GLM -> 1 loyalty point;
- GLM is confirmed by TON treasury/escrow transaction or reserved in the controlled pilot ledger;
- points are issued after GLAME processing and 1C sync/manual document;
- failed or canceled operation refunds reserved GLM;
- issued points follow active loyalty rules at the moment of issuance.

## 4. Buy Loyalty Points

`buy_loyalty_points` is a product where a customer receives loyalty points for GLM with GLAME spread.

Current MVP rules:

- spread: 10%;
- example: 1,000 points require 1,100 GLM;
- minimum: 100 points;
- maximum: 10,000 points;
- issued points expire after 365 days unless changed in approved rules.

## 5. Cancelation and Repair

- Pending bridge can be canceled before processing.
- Failed/canceled GLM -> points bridge must refund reserved GLM.
- Processed bridge can be repaired only through admin workflow with audit comment.
- 1C sync errors require retry, manual document recording or reviewed status.

## 6. External GLM Transfers

External GLM transfer, sale or exchange does not automatically change 1C loyalty points. A new holder receives 1C points only through `glm_to_points` bridge after GLAME confirms the TON/treasury operation.
