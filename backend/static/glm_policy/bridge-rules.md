# GLM Bridge Rules

1C loyalty points and GLM are separate entities connected by approved bridge operations.

1C loyalty points are stored in 1C. GLM is intended to be held in the user's TON wallet as a Jetton. GLAME Platform keeps an operational ledger for requests, reserves, transaction hashes, audit and reconciliation.

Physical GLAME stores do not accept GLM directly in the pilot model. In-store purchases use ordinary 1C loyalty points; GLM can be bridged to points before the purchase.

## Points to GLM

Current MVP reference rate: 1 loyalty point -> 1 GLM.

Points are debited or reserved in 1C/loyalty ledger. GLM is sent to the user's verified TON wallet or placed into a pending TON withdrawal queue until operator/automated settlement.

## GLM to Points

Current MVP reference rate: 1 GLM -> 1 loyalty point.

GLM is confirmed by TON treasury/escrow transaction or reserved in the controlled pilot ledger. Points are issued after GLAME processing and 1C sync or manual document.

Failed or canceled operation refunds reserved GLM.

## Buy Loyalty Points

Current MVP spread: 10%.

Example: 1,000 points require 1,100 GLM.

Issued points follow active loyalty rules at the moment of issuance.
