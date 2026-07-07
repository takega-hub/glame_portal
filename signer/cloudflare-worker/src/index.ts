import { mnemonicToPrivateKey } from '@ton/crypto';
import {
  Address,
  beginCell,
  internal,
  JettonMaster,
  SendMode,
  TonClient,
  WalletContractV5R1,
} from '@ton/ton';

type Env = {
  SIGNER_KV: KVNamespace;
  SIGNER_TOKEN: string;
  TON_HOT_WALLET_MNEMONIC: string;
  TONCENTER_API_KEY?: string;
  TON_NETWORK?: string;
  TONCENTER_ENDPOINT?: string;
  TON_GLM_JETTON_MASTER_ADDRESS: string;
  TON_HOT_WALLET_ADDRESS: string;
  TON_WALLET_VERSION?: string;
  TON_GLM_DECIMALS?: string;
  TX_VALUE_NANOTON?: string;
  FORWARD_NANOTON?: string;
  MAX_AMOUNT_GLM?: string;
  DAILY_LIMIT_GLM?: string;
  HOURLY_LIMIT_GLM?: string;
  MIN_SECONDS_BETWEEN_TRANSFERS?: string;
  EMERGENCY_PAUSED?: string;
};

type TransferIntent = {
  schema?: string;
  network?: string;
  signer_mode?: string;
  wallet_address?: string;
  jetton_wallet_address?: string;
  jetton_master_address?: string;
  destination_wallet_address?: string;
  amount_base_units?: string;
  tx_value_nanoton?: string;
  forward_nanoton?: string;
  query_id?: string;
  comment?: string;
  created_at?: string;
};

const SCHEMA = 'glame_ton_jetton_transfer_intent_v1';
const EMERGENCY_PAUSE_KEY = 'emergency:pause';

function json(data: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(data, null, 2), {
    ...init,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      ...(init.headers || {}),
    },
  });
}

function envBool(value: string | undefined): boolean {
  return String(value || '').trim().toLowerCase() === 'true';
}

function requireAuth(request: Request, env: Env): Response | null {
  const expected = String(env.SIGNER_TOKEN || '').trim();
  const actual = request.headers.get('authorization') || '';
  if (!expected || actual !== `Bearer ${expected}`) {
    return json({ status: 'error', error: 'unauthorized' }, { status: 401 });
  }
  return null;
}

function parsePositiveBigInt(value: string | undefined, field: string): bigint {
  const raw = String(value || '').trim();
  if (!/^[0-9]+$/.test(raw)) {
    throw new Error(`${field} must be a positive integer string`);
  }
  const parsed = BigInt(raw);
  if (parsed <= 0n) {
    throw new Error(`${field} must be positive`);
  }
  return parsed;
}

function parsePositiveNumber(value: string | undefined, fallback: number): number {
  const parsed = Number(value ?? fallback);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function endpoint(env: Env): string {
  const raw = env.TONCENTER_ENDPOINT || (network(env) === 'mainnet'
    ? 'https://toncenter.com/api/v2/jsonRPC'
    : 'https://testnet.toncenter.com/api/v2/jsonRPC');
  const trimmed = raw.replace(/\/$/, '');
  return trimmed.endsWith('/jsonRPC') ? trimmed : `${trimmed}/jsonRPC`;
}

function network(env: Env): string {
  return String(env.TON_NETWORK || 'mainnet').trim() || 'mainnet';
}

function todayKey(): string {
  return new Date().toISOString().slice(0, 10);
}

function hourKey(): string {
  return new Date().toISOString().slice(0, 13);
}

function glmToBaseUnits(glm: number, decimals: number): bigint {
  return BigInt(Math.floor(glm * 10 ** decimals));
}

function baseUnitsToGlmString(value: bigint, decimals: number): string {
  const divider = 10n ** BigInt(decimals);
  const whole = value / divider;
  const fraction = value % divider;
  if (fraction === 0n) {
    return whole.toString();
  }
  return `${whole}.${fraction.toString().padStart(decimals, '0').replace(/0+$/, '')}`;
}

function usageKey(env: Env, period: 'daily' | 'hourly' | 'last_transfer'): string {
  const prefix = `${network(env)}:${env.TON_HOT_WALLET_ADDRESS}`;
  if (period === 'daily') return `usage:${prefix}:daily:${todayKey()}`;
  if (period === 'hourly') return `usage:${prefix}:hourly:${hourKey()}`;
  return `usage:${prefix}:last_transfer`;
}

async function hotWallet(env: Env) {
  const runtime = globalThis as typeof globalThis & { window?: unknown };
  if (!runtime.window) {
    runtime.window = runtime;
  }
  const words = String(env.TON_HOT_WALLET_MNEMONIC || '')
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (words.length !== 24) {
    throw new Error('TON_HOT_WALLET_MNEMONIC must contain 24 words');
  }
  const keyPair = await mnemonicToPrivateKey(words);
  const wallet = WalletContractV5R1.create({
    workchain: 0,
    publicKey: keyPair.publicKey,
    walletId: network(env) === 'testnet' ? { networkGlobalId: -3 } : undefined,
  });
  const expected = Address.parse(env.TON_HOT_WALLET_ADDRESS);
  if (!wallet.address.equals(expected)) {
    throw new Error('TON_HOT_WALLET_MNEMONIC does not match TON_HOT_WALLET_ADDRESS');
  }
  return { keyPair, wallet };
}

async function signerLimitSnapshot(env: Env, decimals: number): Promise<Record<string, unknown>> {
  const dailyKey = usageKey(env, 'daily');
  const hourlyKey = usageKey(env, 'hourly');
  const dailyUsed = BigInt((await env.SIGNER_KV.get(dailyKey)) || '0');
  const hourlyUsed = BigInt((await env.SIGNER_KV.get(hourlyKey)) || '0');
  const lastTransferAt = Number((await env.SIGNER_KV.get(usageKey(env, 'last_transfer'))) || '0');
  const maxAmountGlm = parsePositiveNumber(env.MAX_AMOUNT_GLM, 1000);
  const dailyLimitGlm = parsePositiveNumber(env.DAILY_LIMIT_GLM, 5000);
  const hourlyLimitGlm = parsePositiveNumber(env.HOURLY_LIMIT_GLM, dailyLimitGlm);
  const minSecondsBetweenTransfers = Math.max(0, Math.floor(Number(env.MIN_SECONDS_BETWEEN_TRANSFERS || '2') || 0));
  return {
    max_amount_glm: maxAmountGlm,
    daily_limit_glm: dailyLimitGlm,
    hourly_limit_glm: hourlyLimitGlm,
    min_seconds_between_transfers: minSecondsBetweenTransfers,
    daily_used_glm: baseUnitsToGlmString(dailyUsed, decimals),
    hourly_used_glm: baseUnitsToGlmString(hourlyUsed, decimals),
    last_transfer_at_unix: lastTransferAt || null,
  };
}

async function checkTransferLimits(env: Env, amountBaseUnits: bigint, decimals: number): Promise<void> {
  const nowUnix = Math.floor(Date.now() / 1000);
  const maxAmountGlm = parsePositiveNumber(env.MAX_AMOUNT_GLM, 1000);
  const maxAmountBaseUnits = glmToBaseUnits(maxAmountGlm, decimals);
  if (amountBaseUnits > maxAmountBaseUnits) {
    throw new Error(`amount exceeds per-transaction limit: ${amountBaseUnits}/${maxAmountBaseUnits} base units`);
  }

  const dailyLimitGlm = parsePositiveNumber(env.DAILY_LIMIT_GLM, 5000);
  const dailyLimitBaseUnits = glmToBaseUnits(dailyLimitGlm, decimals);
  const dailyCurrent = BigInt((await env.SIGNER_KV.get(usageKey(env, 'daily'))) || '0');
  if (dailyCurrent + amountBaseUnits > dailyLimitBaseUnits) {
    throw new Error(`daily limit exceeded: ${dailyCurrent + amountBaseUnits}/${dailyLimitBaseUnits} base units`);
  }

  const hourlyLimitGlm = parsePositiveNumber(env.HOURLY_LIMIT_GLM, dailyLimitGlm);
  const hourlyLimitBaseUnits = glmToBaseUnits(hourlyLimitGlm, decimals);
  const hourlyCurrent = BigInt((await env.SIGNER_KV.get(usageKey(env, 'hourly'))) || '0');
  if (hourlyCurrent + amountBaseUnits > hourlyLimitBaseUnits) {
    throw new Error(`hourly limit exceeded: ${hourlyCurrent + amountBaseUnits}/${hourlyLimitBaseUnits} base units`);
  }

  const minSecondsBetweenTransfers = Math.max(0, Math.floor(Number(env.MIN_SECONDS_BETWEEN_TRANSFERS || '2') || 0));
  if (minSecondsBetweenTransfers > 0) {
    const lastTransferAt = Number((await env.SIGNER_KV.get(usageKey(env, 'last_transfer'))) || '0');
    if (lastTransferAt > 0 && nowUnix - lastTransferAt < minSecondsBetweenTransfers) {
      throw new Error(`velocity limit exceeded: wait ${minSecondsBetweenTransfers - (nowUnix - lastTransferAt)} seconds`);
    }
  }
}

async function recordTransferUsage(env: Env, amountBaseUnits: bigint): Promise<void> {
  const dailyKey = usageKey(env, 'daily');
  const hourlyKey = usageKey(env, 'hourly');
  const dailyCurrent = BigInt((await env.SIGNER_KV.get(dailyKey)) || '0');
  const hourlyCurrent = BigInt((await env.SIGNER_KV.get(hourlyKey)) || '0');
  await env.SIGNER_KV.put(dailyKey, String(dailyCurrent + amountBaseUnits), { expirationTtl: 60 * 60 * 48 });
  await env.SIGNER_KV.put(hourlyKey, String(hourlyCurrent + amountBaseUnits), { expirationTtl: 60 * 60 * 3 });
  await env.SIGNER_KV.put(usageKey(env, 'last_transfer'), String(Math.floor(Date.now() / 1000)), { expirationTtl: 60 * 60 * 48 });
}

async function emergencyPauseState(env: Env): Promise<{
  paused: boolean;
  reason?: string;
  updated_at?: string;
  updated_by?: string;
  source: string;
}> {
  if (envBool(env.EMERGENCY_PAUSED)) {
    return { paused: true, source: 'env' };
  }
  const raw = await env.SIGNER_KV.get(EMERGENCY_PAUSE_KEY);
  if (!raw) {
    return { paused: false, source: 'kv' };
  }
  try {
    const payload = JSON.parse(raw) as Record<string, unknown>;
    return {
      paused: Boolean(payload.paused),
      reason: typeof payload.reason === 'string' ? payload.reason : undefined,
      updated_at: typeof payload.updated_at === 'string' ? payload.updated_at : undefined,
      updated_by: typeof payload.updated_by === 'string' ? payload.updated_by : undefined,
      source: 'kv',
    };
  } catch {
    return { paused: true, reason: 'invalid emergency pause KV payload', source: 'kv_error' };
  }
}

async function handleHealth(request: Request, env: Env): Promise<Response> {
  const auth = requireAuth(request, env);
  if (auth) return auth;
  const pause = await emergencyPauseState(env);
  const decimals = Number(env.TON_GLM_DECIMALS || '9');
  return json({
    status: pause.paused ? 'paused' : 'ok',
    mode: 'external_signer',
    network: network(env),
    wallet_address: env.TON_HOT_WALLET_ADDRESS,
    jetton_master_address_configured: Boolean(env.TON_GLM_JETTON_MASTER_ADDRESS),
    limits_loaded: Boolean(env.MAX_AMOUNT_GLM && env.DAILY_LIMIT_GLM && env.HOURLY_LIMIT_GLM),
    limits: await signerLimitSnapshot(env, decimals),
    emergency_paused: pause.paused,
    emergency_pause_source: pause.source,
    emergency_pause_reason: pause.reason || null,
    emergency_pause_updated_at: pause.updated_at || null,
    emergency_pause_updated_by: pause.updated_by || null,
    policy_version: '2026-07-05',
  });
}

async function handleEmergencyPause(request: Request, env: Env): Promise<Response> {
  const auth = requireAuth(request, env);
  if (auth) return auth;
  const payload = (await request.json()) as Record<string, unknown>;
  const paused = Boolean(payload.paused);
  const next = {
    paused,
    reason: typeof payload.reason === 'string' && payload.reason.trim() ? payload.reason.trim().slice(0, 500) : null,
    updated_at: new Date().toISOString(),
    updated_by: typeof payload.updated_by === 'string' && payload.updated_by.trim() ? payload.updated_by.trim().slice(0, 120) : 'backend',
  };
  await env.SIGNER_KV.put(EMERGENCY_PAUSE_KEY, JSON.stringify(next));
  return json({
    status: paused ? 'paused' : 'ok',
    emergency_paused: paused,
    emergency_pause_source: 'kv',
    emergency_pause_reason: next.reason,
    emergency_pause_updated_at: next.updated_at,
    emergency_pause_updated_by: next.updated_by,
  });
}

async function handleTransfer(request: Request, env: Env): Promise<Response> {
  const auth = requireAuth(request, env);
  if (auth) return auth;
  const pause = await emergencyPauseState(env);
  if (pause.paused) {
    return json({
      status: 'error',
      error: 'signer paused',
      emergency_pause_source: pause.source,
      emergency_pause_reason: pause.reason || null,
    }, { status: 423 });
  }

  const intent = (await request.json()) as TransferIntent;
  const expectedNetwork = network(env);
  if (intent.schema !== SCHEMA) throw new Error('invalid schema');
  if (intent.network !== expectedNetwork) throw new Error('invalid network');
  if (intent.wallet_address !== env.TON_HOT_WALLET_ADDRESS) throw new Error('invalid wallet_address');
  if (intent.jetton_master_address !== env.TON_GLM_JETTON_MASTER_ADDRESS) throw new Error('invalid jetton_master_address');
  if (!intent.destination_wallet_address) throw new Error('destination_wallet_address is required');
  if (!intent.query_id) throw new Error('query_id is required');

  const idempotencyKey = `query:${intent.query_id}`;
  const existing = await env.SIGNER_KV.get(idempotencyKey);
  if (existing) {
    return json(JSON.parse(existing));
  }

  const decimals = Number(env.TON_GLM_DECIMALS || '9');
  const amountBaseUnits = parsePositiveBigInt(intent.amount_base_units, 'amount_base_units');
  await checkTransferLimits(env, amountBaseUnits, decimals);

  const client = new TonClient({
    endpoint: endpoint(env),
    apiKey: env.TONCENTER_API_KEY || undefined,
  });
  const { keyPair, wallet } = await hotWallet(env);
  const openedWallet = client.open(wallet);
  const seqno = await openedWallet.getSeqno();
  const master = client.open(JettonMaster.create(Address.parse(env.TON_GLM_JETTON_MASTER_ADDRESS)));
  const hotJettonWallet = await master.getWalletAddress(wallet.address);
  if (intent.jetton_wallet_address && !hotJettonWallet.equals(Address.parse(intent.jetton_wallet_address))) {
    throw new Error('invalid jetton_wallet_address');
  }

  const destination = Address.parse(intent.destination_wallet_address);
  const queryId = BigInt(intent.query_id);
  const txValueNanoton = parsePositiveBigInt(intent.tx_value_nanoton || env.TX_VALUE_NANOTON || '50000000', 'tx_value_nanoton');
  const forwardNanoton = parsePositiveBigInt(intent.forward_nanoton || env.FORWARD_NANOTON || '1', 'forward_nanoton');

  const forwardPayload = beginCell()
    .storeUint(0, 32)
    .storeStringTail(intent.comment || '')
    .endCell();
  const transferBody = beginCell()
    .storeUint(0x0f8a7ea5, 32)
    .storeUint(queryId, 64)
    .storeCoins(amountBaseUnits)
    .storeAddress(destination)
    .storeAddress(wallet.address)
    .storeBit(0)
    .storeCoins(forwardNanoton)
    .storeBit(1)
    .storeRef(forwardPayload)
    .endCell();

  await openedWallet.sendTransfer({
    secretKey: keyPair.secretKey,
    seqno,
    sendMode: SendMode.PAY_GAS_SEPARATELY,
    messages: [
      internal({
        to: hotJettonWallet,
        value: txValueNanoton,
        bounce: true,
        body: transferBody,
      }),
    ],
  });

  await recordTransferUsage(env, amountBaseUnits);
  const response = {
    status: 'sent',
    request_id: intent.query_id,
    seqno,
    query_id: intent.query_id,
    wallet_address: wallet.address.toString({ testOnly: expectedNetwork !== 'mainnet' }),
    jetton_wallet_address: hotJettonWallet.toString({ testOnly: expectedNetwork !== 'mainnet' }),
  };
  await env.SIGNER_KV.put(idempotencyKey, JSON.stringify(response), { expirationTtl: 60 * 60 * 48 });
  return json(response);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      const url = new URL(request.url);
      if (request.method === 'GET' && url.pathname === '/health') {
        return await handleHealth(request, env);
      }
      if (request.method === 'POST' && url.pathname === '/admin/emergency-pause') {
        return await handleEmergencyPause(request, env);
      }
      if (request.method === 'POST' && url.pathname === '/ton/jetton-transfer') {
        return await handleTransfer(request, env);
      }
      return json({ status: 'error', error: 'not found' }, { status: 404 });
    } catch (error) {
      return json({ status: 'error', error: error instanceof Error ? error.message : String(error) }, { status: 400 });
    }
  },
};
