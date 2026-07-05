# GLM TON Testnet Deploy Operator Handoff

Status: operator handoff template  
Scope: GLM Jetton master deploy to TON testnet

## Goal

Deploy the GLM Jetton master on TON testnet using the pinned `ton-blockchain/jetton-contract` reference implementation, then record the resulting addresses and transaction hash back into GLAME.

This is not a mainnet launch.

## Required Operator Inputs

- GLAME testnet admin wallet public address.
- GLAME testnet treasury wallet public address.
- Testnet deployer wallet with testnet TON.
- TON API endpoint/API key, if required by the selected provider.

Never paste mnemonic/private keys into this repository, docs, admin UI or chat.

## Generate The Live Handoff

From `contracts/ton/glm-jetton`:

```bash
npm run deploy:handoff
```

To save a local generated copy:

```bash
npm run deploy:handoff:write
```

The generated handoff includes current reference commit, metadata URL, predeploy checks and exact deploy/record commands.

## Minimum Command Sequence

```bash
npm run reference:fetch
npm run reference:status
TON_JETTON_ADMIN_ADDRESS=EQ... TON_GLM_TREASURY_ADDRESS=EQ... npm run blueprint:prepare
TON_JETTON_ADMIN_ADDRESS=EQ... TON_GLM_TREASURY_ADDRESS=EQ... npm run blueprint:status
cd vendor/ton-blockchain-jetton-contract
npm install
npx blueprint build JettonMinter
npx blueprint build JettonWallet
cd ../..
npm run build:status
cd vendor/ton-blockchain-jetton-contract
npx blueprint run deployGlmJettonMinter --custom https://testnet.toncenter.com/api/v2/ --custom-version v2 --custom-type testnet
npx blueprint run checkWalletLib --custom https://testnet.toncenter.com/api/v2/ --custom-version v2 --custom-type testnet
```

## After Deploy

Record the deployment:

```bash
cd contracts/ton/glm-jetton
npm run record:deploy -- \
  --jetton-master-address EQ... \
  --deploy-tx-hash ... \
  --admin-address EQ... \
  --treasury-address EQ... \
  --wallet-code-hash ...
```

Then set backend env:

- `TON_NETWORK=testnet`
- `TON_GLM_JETTON_MASTER_ADDRESS=EQ...`
- `TON_GLM_TREASURY_ADDRESS=EQ...`
- `TON_GLM_METADATA_URL=https://partner.glamejewelry.ru/static/glm_policy/jetton-metadata.json`

## Stop Conditions

- Mainnet is blocked.
- Reference commit mismatch.
- Missing admin/treasury address.
- `checkWalletLib` fails or cannot confirm wallet library readiness.
- Legal/security asks to pause.
