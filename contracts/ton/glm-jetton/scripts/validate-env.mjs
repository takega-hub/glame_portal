#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

function loadDotEnv(filePath) {
  if (!fs.existsSync(filePath)) return {};
  const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/);
  const result = {};
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) continue;
    const [key, ...rest] = trimmed.split('=');
    result[key.trim()] = rest.join('=').trim();
  }
  return result;
}

function mergedEnv() {
  const localEnv = loadDotEnv(path.resolve(process.cwd(), '.env'));
  return { ...localEnv, ...process.env };
}

function main() {
  const env = mergedEnv();
  const required = [
    'TON_NETWORK',
    'TON_ENDPOINT',
    'TON_GLM_METADATA_URL',
  ];
  const recommendedForDeploy = [
    'TON_DEPLOYER_MNEMONIC',
    'TON_JETTON_ADMIN_ADDRESS',
    'TON_GLM_TREASURY_ADDRESS',
    'TON_GLM_JETTON_MASTER_ADDRESS',
  ];

  const errors = [];
  const warnings = [];
  for (const key of required) {
    if (!env[key]) errors.push(`Missing ${key}`);
  }
  if ((env.TON_NETWORK || '').trim() !== 'testnet') {
    errors.push('TON_NETWORK must be testnet for this package');
  }
  for (const key of recommendedForDeploy) {
    if (!env[key]) warnings.push(`Missing ${key}; deploy/mint is not ready`);
  }

  const payload = {
    ok: errors.length === 0,
    network: env.TON_NETWORK || null,
    endpoint: env.TON_ENDPOINT || null,
    metadata_url: env.TON_GLM_METADATA_URL || null,
    has_deployer_mnemonic: Boolean(env.TON_DEPLOYER_MNEMONIC),
    has_admin_address: Boolean(env.TON_JETTON_ADMIN_ADDRESS),
    has_treasury_address: Boolean(env.TON_GLM_TREASURY_ADDRESS),
    has_jetton_master_address: Boolean(env.TON_GLM_JETTON_MASTER_ADDRESS),
    errors,
    warnings,
  };
  console.log(JSON.stringify(payload, null, 2));
  process.exit(errors.length ? 1 : 0);
}

main();

