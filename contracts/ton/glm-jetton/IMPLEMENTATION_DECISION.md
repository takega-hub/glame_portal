# GLM Jetton Implementation Decision

Status: draft decision  
Date: 2026-07-02

## Decision

Use a standard TON Jetton implementation compatible with TEP-74:

- Jetton master contract;
- Jetton wallet contract;
- mintable testnet master controlled by GLAME admin/treasury wallet;
- GLAME ledger remains integer GLM, while Jetton metadata uses `decimals = 9` for TON wallet display compatibility. Operator tooling converts integer GLM amounts to on-chain base units.

Do not write a custom Jetton protocol from scratch.

## Preferred Base

Preferred reference:

- `ton-blockchain/jetton-contract`
- locked commit: `d55f228edb0eb477cb4845d67e0dacc6489c6b57`
- lock file: `reference.jetton-contract.lock.json`

Reason:

- closest to standard Jetton behavior;
- avoids adding stablecoin-specific issuer controls unless GLAME explicitly needs them;
- easier security review because the behavior is closer to common Jetton expectations.

## Not Preferred for First Testnet Pilot

`ton-blockchain/stablecoin-contract` is useful as a reference, but it includes additional issuer/admin controls designed for regulated stablecoin-like assets. For GLM testnet pilot, those controls may increase legal/product complexity.

Use it only if legal/security explicitly approves the extra controls.

## Tooling

TON docs describe Blueprint as supported for smart contract development, testing and deployment. The same docs also note that Acton is recommended for new smart contract projects, while Blueprint remains supported for existing projects.

For GLM pilot:

1. Start with a standard Jetton reference implementation.
2. Verify the pinned reference with `npm run reference:status`.
3. Fetch the pinned reference with `npm run reference:fetch` only when contract review/deploy work starts.
4. Generate GLM-specific Blueprint deploy script with `npm run blueprint:prepare`.
5. Verify GLM Blueprint deploy readiness with `npm run blueprint:status`.
6. Keep deployment on TON testnet.
7. Record deployment artifact through `npm run record:deploy`.
8. Keep mainnet blocked until legal/security/treasury approval.

## Acceptance Criteria

- Jetton master deployed on TON testnet.
- Metadata URL points to `https://partner.glamejewelry.ru/static/glm_policy/jetton-metadata.json`.
- Decimals are `0`.
- Admin address is GLAME testnet admin/treasury.
- Deployment artifact has `status = testnet_deployed`.
- Backend env points to the same master/treasury addresses as artifact.
- First claim is tested with a verified TON wallet and tx hash saved in GLAME admin.

## References

- TON Jetton mechanics: https://docs.ton.org/contracts/standard/tokens/jettons/how-it-works
- TON Jetton minting: https://docs.ton.org/contracts/standard/tokens/jettons/mint
- TON Blueprint overview: https://docs.ton.org/contracts/blueprint/overview
- TON Blueprint first contract: https://docs.ton.org/contracts/blueprint/first-smart-contract
- Standard Jetton reference: https://github.com/ton-blockchain/jetton-contract
- Stablecoin-style reference: https://github.com/ton-blockchain/stablecoin-contract
