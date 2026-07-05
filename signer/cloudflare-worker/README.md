# GLAME TON Signer for Cloudflare Workers

Cloudflare Worker signer for CryptoGLAME production hot-wallet transfers.

The GLAME backend never receives a seed phrase or private key. It sends a signed-operation intent to this Worker. The Worker checks auth, limits and idempotency, signs the TON Jetton transfer and sends it through TON Center JSON-RPC.

## Endpoints

- `GET /health`
- `POST /ton/jetton-transfer`

The transfer endpoint accepts the `glame_ton_jetton_transfer_intent_v1` payload documented in `/backend/static/glm_policy/production-signer-contract.md`.

## Cloudflare Setup

1. Create a Cloudflare account.
2. Open **Workers & Pages** -> **Create** -> **Connect GitHub**.
3. Select this repository.
4. Set the project root directory to:

```text
signer/cloudflare-worker
```

5. Create a KV namespace:

```bash
npx wrangler kv namespace create SIGNER_KV
```

6. Put the returned namespace id into `wrangler.toml`.

7. Set secrets:

```bash
npx wrangler secret put SIGNER_TOKEN
npx wrangler secret put TON_HOT_WALLET_MNEMONIC
npx wrangler secret put TONCENTER_API_KEY
```

8. Set non-secret vars in `wrangler.toml`:

- `TON_NETWORK`
- `TON_GLM_JETTON_MASTER_ADDRESS`
- `TON_HOT_WALLET_ADDRESS`
- `MAX_AMOUNT_GLM`
- `DAILY_LIMIT_GLM`

9. Deploy:

```bash
npm install
npm run deploy
```

## Backend Env

After deploy, put these values into `/etc/glame-platform/glame-stack.env`:

```env
TON_GLM_PRODUCTION_SIGNER_MODE=external_signer
TON_GLM_PRODUCTION_SIGNER_ENDPOINT=https://glame-ton-signer.<your-subdomain>.workers.dev/ton/jetton-transfer
TON_GLM_PRODUCTION_SIGNER_HEALTH_ENDPOINT=https://glame-ton-signer.<your-subdomain>.workers.dev/health
TON_GLM_PRODUCTION_SIGNER_TOKEN=<same SIGNER_TOKEN>
```

Then restart GLAME stack and press **Проверить signer** in `/admin/crypto`.

## Safety Rules

- Do not use treasury wallet seed here.
- Use only a limited hot-wallet.
- Keep a low operational GLM balance on the hot-wallet.
- Set `MAX_AMOUNT_GLM` and `DAILY_LIMIT_GLM`.
- Rotate `SIGNER_TOKEN` before mainnet if it was pasted anywhere unsafe.
- If something looks wrong, set `EMERGENCY_PAUSED=true` in Cloudflare vars and redeploy.

