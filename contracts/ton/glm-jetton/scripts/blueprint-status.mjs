#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const rootDir = process.cwd();
const lockPath = path.resolve(rootDir, 'reference.jetton-contract.lock.json');
const artifactPath = path.resolve(rootDir, 'glm-jetton.testnet.json');

function loadJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function loadDotEnv(filePath) {
  if (!fs.existsSync(filePath)) return {};
  const result = {};
  for (const line of fs.readFileSync(filePath, 'utf8').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) continue;
    const [key, ...rest] = trimmed.split('=');
    result[key.trim()] = rest.join('=').trim();
  }
  return result;
}

function gitHead(dir) {
  try {
    return execFileSync('git', ['-C', dir, 'rev-parse', 'HEAD'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch {
    return null;
  }
}

const env = { ...loadDotEnv(path.resolve(rootDir, '.env')), ...process.env };
const lock = loadJson(lockPath);
const artifact = loadJson(artifactPath);
const vendorPath = path.resolve(rootDir, lock.vendor_path || '');
const deployScriptPath = path.resolve(vendorPath, 'scripts', 'deployGlmJettonMinter.ts');
const metadataUrl = env.TON_GLM_METADATA_URL || artifact.token?.metadata_url || null;
const adminAddress = env.TON_JETTON_ADMIN_ADDRESS || artifact.contracts?.admin_address || null;
const actualCommit = fs.existsSync(vendorPath) ? gitHead(vendorPath) : null;
const deployScript = fs.existsSync(deployScriptPath) ? fs.readFileSync(deployScriptPath, 'utf8') : '';
const scriptMetadataUrl = deployScript.match(/const GLM_METADATA_URI = "([^"]+)";/)?.[1] || null;
const scriptAdminAddress = deployScript.match(/const GLM_ADMIN_ADDRESS = "([^"]+)";/)?.[1] || null;
const effectiveMetadataUrl = metadataUrl || scriptMetadataUrl;
const effectiveAdminAddress = adminAddress || scriptAdminAddress;

const checks = [
  {
    code: 'network_testnet',
    ok: (env.TON_NETWORK || artifact.network || 'testnet') === 'testnet',
    message: 'TON_NETWORK must be testnet',
  },
  {
    code: 'reference_vendor',
    ok: fs.existsSync(vendorPath),
    message: 'Pinned reference checkout exists',
  },
  {
    code: 'reference_commit',
    ok: actualCommit === lock.commit,
    message: 'Pinned reference checkout matches lock commit',
  },
  {
    code: 'metadata_url',
    ok: Boolean(effectiveMetadataUrl),
    message: 'GLM metadata URL is configured',
  },
  {
    code: 'admin_address',
    ok: Boolean(effectiveAdminAddress),
    message: 'TON_JETTON_ADMIN_ADDRESS or artifact admin_address is configured',
  },
  {
    code: 'deploy_script',
    ok: Boolean(deployScript),
    message: 'GLM Blueprint deploy script exists',
  },
  {
    code: 'deploy_script_metadata',
    ok: Boolean(effectiveMetadataUrl && deployScript.includes(effectiveMetadataUrl)),
    message: 'Deploy script contains GLM metadata URL',
  },
  {
    code: 'deploy_script_admin',
    ok: Boolean(effectiveAdminAddress && deployScript.includes(effectiveAdminAddress)),
    message: 'Deploy script contains GLM admin address',
  },
  {
    code: 'mainnet_guard',
    ok: deployScript.includes("provider.network() === 'mainnet'"),
    message: 'Deploy script has mainnet guard',
  },
];

const blockers = checks.filter((item) => !item.ok);
console.log(JSON.stringify({
  ok: blockers.length === 0,
  status: blockers.length === 0 ? 'ready_for_testnet_deploy' : 'blocked',
  vendor_path: lock.vendor_path,
  expected_commit: lock.commit,
  actual_commit: actualCommit,
  deploy_script: fs.existsSync(deployScriptPath) ? path.relative(rootDir, deployScriptPath) : null,
  metadata_url: effectiveMetadataUrl,
  admin_address_source: adminAddress ? 'env_or_artifact' : scriptAdminAddress ? 'deploy_script' : null,
  has_admin_address: Boolean(effectiveAdminAddress),
  checks,
  blockers,
}, null, 2));
process.exit(blockers.length ? 1 : 0);
