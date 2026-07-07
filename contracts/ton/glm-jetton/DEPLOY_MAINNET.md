# GLM Jetton Mainnet Deploy Runbook

Status: production preflight
Scope: deploy GLAME Coin (`GLM`) Jetton master to TON mainnet and mint initial bank supply.

## Fixed Mainnet Parameters

- Token: GLAME Coin (`GLM`)
- Decimals: `9`
- Metadata URL: `https://partner.glamejewelry.ru/static/glm_policy/jetton-metadata.json`
- Icon URL: `https://partner.glamejewelry.ru/static/glm_policy/glm-token-icon-v3.png`
- Treasury/bank wallet: `UQAY9ub55iQ3U9G8r6h74Mk2GPaNVy8YkJSHkGyV1-Hn_7Dq`
- Initial bank mint: `10000000 GLM`

## Safety Rules

- Do not put seed phrases in this repository.
- Do not paste seed phrases into chat, logs, admin UI, or shell history.
- Deploy and mint must be signed only by the approved treasury/admin wallet.
- Mainnet commands require explicit `--allow-mainnet true` in scripts.
- Stop if metadata/icon URL is unavailable or points to the wrong brand asset.

## Preflight

```bash
cd contracts/ton/glm-jetton
npm run reference:status
npm run build:status
curl -fsS https://partner.glamejewelry.ru/static/glm_policy/jetton-metadata.json
curl -fsS -I https://partner.glamejewelry.ru/static/glm_policy/glm-token-icon-v3.png
```

## Prepare Deploy

```bash
cd contracts/ton/glm-jetton
TON_NETWORK=mainnet \
TON_ENDPOINT=https://toncenter.com/api/v2/jsonRPC \
TON_GLM_METADATA_URL=https://partner.glamejewelry.ru/static/glm_policy/jetton-metadata.json \
TON_JETTON_ADMIN_ADDRESS=UQAY9ub55iQ3U9G8r6h74Mk2GPaNVy8YkJSHkGyV1-Hn_7Dq \
TON_GLM_PRODUCTION_TREASURY_ADDRESS=UQAY9ub55iQ3U9G8r6h74Mk2GPaNVy8YkJSHkGyV1-Hn_7Dq \
npm run mainnet:prepare-deploy
```

Then run the printed `deploy_mainnet` command and confirm the transaction in the wallet.

## Record Deploy

After deploy, copy Jetton master address and deploy transaction hash from Blueprint/explorer:

```bash
cd contracts/ton/glm-jetton
npm run mainnet:record-deploy -- \
  --jetton-master-address EQ... \
  --deploy-tx-hash ... \
  --admin-address UQAY9ub55iQ3U9G8r6h74Mk2GPaNVy8YkJSHkGyV1-Hn_7Dq \
  --treasury-address UQAY9ub55iQ3U9G8r6h74Mk2GPaNVy8YkJSHkGyV1-Hn_7Dq \
  --deployer UQAY9ub55iQ3U9G8r6h74Mk2GPaNVy8YkJSHkGyV1-Hn_7Dq
```

## Prepare Initial Mint

```bash
cd contracts/ton/glm-jetton
TON_NETWORK=mainnet \
TON_ENDPOINT=https://toncenter.com/api/v2/jsonRPC \
TON_JETTON_ADMIN_ADDRESS=UQAY9ub55iQ3U9G8r6h74Mk2GPaNVy8YkJSHkGyV1-Hn_7Dq \
TON_GLM_PRODUCTION_TREASURY_ADDRESS=UQAY9ub55iQ3U9G8r6h74Mk2GPaNVy8YkJSHkGyV1-Hn_7Dq \
npm run mainnet:prepare-mint -- --amount 10000000
```

Then run the printed `run_mint` command and confirm the transaction in the wallet.

## After Mint

1. Verify treasury GLM balance.
2. Set production/backend env only after deploy and mint are verified:
   - `TON_NETWORK=mainnet`
   - `TON_GLM_JETTON_MASTER_ADDRESS=EQ...`
   - `TON_GLM_TREASURY_ADDRESS=UQAY9ub55iQ3U9G8r6h74Mk2GPaNVy8YkJSHkGyV1-Hn_7Dq`
3. Run a small mainnet smoke test before enabling user-facing mainnet operations.
