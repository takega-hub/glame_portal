# GLM Jetton Testnet Package

Status: draft deployment package  
Network target: TON testnet first  
Token: GLAME Coin (`GLM`)

## Decision

Use a standard TON Jetton implementation compatible with TEP-74 Jetton master/wallet contracts. Do not write a custom fungible token protocol from scratch.

Recommended implementation path:

1. Use the official TON Jetton reference or audited TON stablecoin-style Jetton implementation as the contract base.
2. Configure GLM metadata and admin/treasury addresses.
3. Deploy only to TON testnet until legal and security approval are complete.
4. Connect GLAME `pending claim` records to testnet mint/transfer operations.
5. Store the resulting TON tx hash in the existing GLM claim transaction metadata.

Manual operator workflow is documented in `OPERATOR_CLAIM_RUNBOOK.md`.

## Local Tooling

```bash
npm run validate:env
npm run validate:artifact
npm run reference:status
npm run reference:fetch
npm run blueprint:prepare
npm run blueprint:status
npm run build:status
npm run mint:prepare -- --destination EQ... --amount 10
npm run mint:prepare-claim -- --csv ./pending-claims.csv
npm run mint:status -- --destination EQ...
npm run deploy:handoff
npm run prepare:claims -- ./pending-claims.csv
npm run prepare:claims:sample
npm run record:deploy -- --jetton-master-address EQ... --deploy-tx-hash ... --admin-address EQ... --treasury-address EQ...
```

The deployment and claim scripts are intentionally dry-run/preflight only. They do not send transactions or use private keys.
`reference:fetch` only downloads the pinned Jetton reference implementation into `vendor/ton-blockchain-jetton-contract`.
`blueprint:prepare` generates a GLM-specific Blueprint deploy script inside that pinned reference checkout.
`blueprint:status` verifies that the generated deploy script matches the pinned reference, metadata URL and admin address.
`build:status` verifies that the pinned reference compiled artifacts exist and include Jetton hashes.
`deploy:handoff` prints the current operator checklist for testnet deploy without exposing private keys.

## Reference Lock

The selected Jetton reference is pinned in `reference.jetton-contract.lock.json`.

- Repo: `https://github.com/ton-blockchain/jetton-contract.git`
- Branch: `main`
- Commit: `d55f228edb0eb477cb4845d67e0dacc6489c6b57`
- Local vendor path: `vendor/ton-blockchain-jetton-contract`

Use `npm run reference:status` before review/deploy to confirm the local vendor checkout matches the lock.

## Blueprint Deploy Preparation

Before testnet deploy:

1. Set `TON_NETWORK=testnet`.
2. Set `TON_JETTON_ADMIN_ADDRESS` to the public GLAME testnet admin/treasury wallet.
3. Set `TON_GLM_METADATA_URL` to the public metadata URL.
4. Run:
   ```bash
   npm run reference:fetch
   npm run blueprint:prepare
   npm run blueprint:status
   ```

The generated script is `vendor/ton-blockchain-jetton-contract/scripts/deployGlmJettonMinter.ts`.
It rejects mainnet and uses the GLM metadata/admin values from this package.

For operator handoff, use `DEPLOY_OPERATOR_HANDOFF.md` or run `npm run deploy:handoff`.

## GLM Testnet Parameters

- Name: GLAME Coin
- Symbol: GLM
- Decimals: 0
- Initial mainnet supply: not defined
- Testnet minting: admin-controlled, only for verified GLAME claim tests
- Admin: GLAME testnet treasury wallet
- Content URI: `/static/glm_policy/jetton-metadata.json`

## Decimals

GLAME ledger uses integer GLM units, but TON wallets commonly render Jettons with 9 decimals. For wallet display compatibility, GLM Jetton metadata uses `decimals = 9`.

Operator tools accept integer GLM amounts and convert them to on-chain base units. Example: `10 GLM` is minted as `10000000000` base units.

## Claim Flow

1. Partner verifies TON wallet through TON Connect and `ton_proof`.
2. Admin enables GLM claim for that partner.
3. Partner creates off-chain pending claim from available GLM balance.
4. Operator prepares the exact claim mint with `mint:prepare-claim` and mints/transfers GLM Jetton to verified wallet on TON testnet.
5. Operator stores TON tx hash in GLAME admin claim queue.
6. GLAME marks claim as `processed`.

## Non-goals

- No mainnet deployment in this package.
- No DEX liquidity in this package.
- No public price, buyback or growth promise.
- No automatic bridge to 1C points through external transfers.

## References

- TON Jetton docs: https://docs.ton.org/contracts/standard/tokens/jettons/how-it-works
- TON minting docs: https://docs.ton.org/contracts/standard/tokens/jettons/mint
- TON standard Jetton reference: https://github.com/ton-blockchain/jetton-contract
- TON stablecoin Jetton sample: https://github.com/ton-blockchain/stablecoin-contract
