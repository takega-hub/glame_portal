# CryptoGLAME Production Signer Contract

Production signing must happen outside the GLAME backend runtime.

The backend sends a transfer intent without private keys. The signer service validates policy, signs with KMS/Vault/external wallet infrastructure and broadcasts the TON transaction.

## Environment

- `TON_GLM_PRODUCTION_SIGNER_MODE`: `kms`, `vault`, or `external_signer`.
- `TON_GLM_PRODUCTION_SIGNER_ENDPOINT`: HTTPS endpoint accepting transfer intents.
- `TON_GLM_PRODUCTION_SIGNER_HEALTH_ENDPOINT`: optional health endpoint. If it is not set, backend checks `<TON_GLM_PRODUCTION_SIGNER_ENDPOINT>/health`.
- `TON_GLM_PRODUCTION_SIGNER_PAUSE_ENDPOINT`: optional emergency pause endpoint. If it is not set, backend derives `<signer-base>/admin/emergency-pause` from `TON_GLM_PRODUCTION_SIGNER_ENDPOINT`.
- `TON_GLM_PRODUCTION_SIGNER_TOKEN`: bearer token for backend-to-signer authentication.
- `TON_GLM_PRODUCTION_HOT_WALLET_ADDRESS`: production hot-wallet public address.
- `TON_GLM_PRODUCTION_LEGAL_APPROVED`, `TON_GLM_PRODUCTION_SECURITY_APPROVED`, `TON_GLM_PRODUCTION_TREASURY_APPROVED`: approval gates.

`TON_GLM_AUTO_TRANSFER_HOT_WALLET_MNEMONIC` must not be present in production runtime env.

## Request

`POST TON_GLM_PRODUCTION_SIGNER_ENDPOINT`

Headers:

- `Content-Type: application/json`
- `Authorization: Bearer <TON_GLM_PRODUCTION_SIGNER_TOKEN>`

Body:

```json
{
  "schema": "glame_ton_jetton_transfer_intent_v1",
  "network": "mainnet",
  "signer_mode": "external_signer",
  "wallet_address": "EQ...",
  "jetton_wallet_address": "EQ...",
  "jetton_master_address": "EQ...",
  "destination_wallet_address": "EQ...",
  "amount_base_units": "100000000000",
  "tx_value_nanoton": "50000000",
  "forward_nanoton": "1",
  "query_id": "1780000000",
  "comment": "GLAME points_to_glm <operation_id>",
  "created_at": "2026-07-05T00:00:00+00:00"
}
```

The signer must reject:

- any network other than `mainnet`;
- unknown `schema`;
- wallet address different from the approved production hot-wallet;
- amount above per-transaction limit;
- daily amount above daily cap;
- destination blocked by security policy;
- missing or invalid authentication;
- stale `created_at` or duplicated `query_id` when replay protection is enabled.

## Response

Accepted response:

```json
{
  "status": "sent",
  "request_id": "signer-request-id",
  "tx_hash": "optional-ton-tx-hash",
  "external_message_hash": "optional-external-message-hash",
  "seqno": 42,
  "query_id": "1780000000"
}
```

Allowed statuses: `ok`, `accepted`, `sent`.

Error response:

```json
{
  "status": "error",
  "error": "policy limit exceeded"
}
```

The signer must never return private keys, seed phrases, raw secret material or debug payloads containing secrets.

## Reference Implementation

The repository contains a Cloudflare Workers reference signer:

```text
signer/cloudflare-worker
```

Use it as the first mainnet MVP signer only with a limited hot-wallet, strict per-transaction limit, daily cap and emergency pause.

## Health Check

`GET TON_GLM_PRODUCTION_SIGNER_HEALTH_ENDPOINT`

Headers:

- `Accept: application/json`
- `Authorization: Bearer <TON_GLM_PRODUCTION_SIGNER_TOKEN>`

Recommended response:

```json
{
  "status": "ok",
  "mode": "external_signer",
  "wallet_address": "EQ...",
  "limits_loaded": true,
  "policy_version": "2026-07-05"
}
```

Allowed healthy statuses: `ok`, `ready`, `healthy`.

The health endpoint must not sign, broadcast, reserve funds or return secret material.

## Emergency Pause

`POST TON_GLM_PRODUCTION_SIGNER_PAUSE_ENDPOINT`

Headers:

- `Content-Type: application/json`
- `Authorization: Bearer <TON_GLM_PRODUCTION_SIGNER_TOKEN>`

Body:

```json
{
  "paused": true,
  "reason": "Admin emergency pause",
  "updated_by": "admin-user-id"
}
```

Expected response:

```json
{
  "status": "paused",
  "emergency_paused": true,
  "emergency_pause_source": "kv",
  "emergency_pause_reason": "Admin emergency pause",
  "emergency_pause_updated_at": "2026-07-06T00:00:00.000Z"
}
```

When emergency pause is enabled, the signer must reject transfer requests with HTTP `423` and must keep `/health` available.
