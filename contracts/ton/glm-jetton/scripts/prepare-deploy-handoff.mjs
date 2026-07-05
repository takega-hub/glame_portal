#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const rootDir = process.cwd();

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

function short(value) {
  if (!value) return '-';
  const text = String(value);
  return text.length > 18 ? `${text.slice(0, 9)}...${text.slice(-8)}` : text;
}

function tick(ok) {
  return ok ? '[x]' : '[ ]';
}

const env = { ...loadDotEnv(path.resolve(rootDir, '.env')), ...process.env };
const artifact = loadJson(path.resolve(rootDir, 'glm-jetton.testnet.json'));
const lock = loadJson(path.resolve(rootDir, 'reference.jetton-contract.lock.json'));
const vendorPath = path.resolve(rootDir, lock.vendor_path || '');
const deployScriptPath = path.resolve(vendorPath, 'scripts', 'deployGlmJettonMinter.ts');
const deployScript = fs.existsSync(deployScriptPath) ? fs.readFileSync(deployScriptPath, 'utf8') : '';
const scriptMetadataUrl = deployScript.match(/const GLM_METADATA_URI = "([^"]+)";/)?.[1] || '';
const scriptAdminAddress = deployScript.match(/const GLM_ADMIN_ADDRESS = "([^"]+)";/)?.[1] || '';
const metadataUrl = env.TON_GLM_METADATA_URL || artifact.token?.metadata_url || scriptMetadataUrl || '';
const adminAddress = env.TON_JETTON_ADMIN_ADDRESS || artifact.contracts?.admin_address || scriptAdminAddress || '';
const treasuryAddress = env.TON_GLM_TREASURY_ADDRESS || artifact.contracts?.treasury_address || '';
const endpoint = env.TON_ENDPOINT || 'https://testnet.toncenter.com/api/v2/';
const actualCommit = fs.existsSync(vendorPath) ? gitHead(vendorPath) : null;

const checks = [
  ['TON_NETWORK is testnet', (env.TON_NETWORK || artifact.network || 'testnet') === 'testnet'],
  ['Pinned reference is fetched', fs.existsSync(vendorPath)],
  ['Pinned reference commit matches lock', actualCommit === lock.commit],
  ['GLM metadata URL is set', Boolean(metadataUrl)],
  ['TON_JETTON_ADMIN_ADDRESS is set', Boolean(adminAddress)],
  ['TON_GLM_TREASURY_ADDRESS is set', Boolean(treasuryAddress)],
  ['GLM Blueprint deploy script is generated', fs.existsSync(deployScriptPath)],
];

const lines = [
  '# GLM TON Testnet Deploy Handoff',
  '',
  `Generated at: ${new Date().toISOString()}`,
  '',
  '## Current Status',
  '',
  `- Network: ${env.TON_NETWORK || artifact.network || 'testnet'}`,
  `- Metadata URL: ${metadataUrl || '-'}`,
  `- Admin address: ${short(adminAddress)}`,
  `- Treasury address: ${short(treasuryAddress)}`,
  `- Reference commit: ${actualCommit || '-'}${actualCommit === lock.commit ? ' (matches lock)' : ''}`,
  `- Deploy script: ${fs.existsSync(deployScriptPath) ? path.relative(rootDir, deployScriptPath) : '-'}`,
  '',
  '## Predeploy Checklist',
  '',
  ...checks.map(([label, ok]) => `- ${tick(ok)} ${label}`),
  '',
  '## Operator Commands',
  '',
  'Run from `contracts/ton/glm-jetton`:',
  '',
  '```bash',
  'npm run reference:fetch',
  'npm run reference:status',
  'TON_JETTON_ADMIN_ADDRESS=EQ... TON_GLM_TREASURY_ADDRESS=EQ... npm run blueprint:prepare',
  'TON_JETTON_ADMIN_ADDRESS=EQ... TON_GLM_TREASURY_ADDRESS=EQ... npm run blueprint:status',
  'cd vendor/ton-blockchain-jetton-contract',
  'npm install',
  'npx blueprint build JettonMinter',
  'npx blueprint build JettonWallet',
  'cd ../..',
  'npm run build:status',
  'cd vendor/ton-blockchain-jetton-contract',
  `npx blueprint run deployGlmJettonMinter --custom ${endpoint} --custom-version v2 --custom-type testnet${env.TON_API_KEY ? ' --custom-key $TON_API_KEY' : ''}`,
  `npx blueprint run checkWalletLib --custom ${endpoint} --custom-version v2 --custom-type testnet${env.TON_API_KEY ? ' --custom-key $TON_API_KEY' : ''}`,
  '```',
  '',
  '## After Deploy',
  '',
  'Copy from deploy output/explorer:',
  '',
  '- Jetton master address',
  '- Deploy tx hash',
  '- Admin address',
  '- Treasury address',
  '- Wallet code hash, if available from `checkWalletLib` or explorer',
  '',
  'Then record the artifact:',
  '',
  '```bash',
  'cd contracts/ton/glm-jetton',
  'npm run record:deploy -- \\',
  '  --jetton-master-address EQ... \\',
  '  --deploy-tx-hash ... \\',
  '  --admin-address EQ... \\',
  '  --treasury-address EQ... \\',
  '  --wallet-code-hash ...',
  '```',
  '',
  '## Backend Env After Deploy',
  '',
  '```bash',
  'TON_NETWORK=testnet',
  'TON_GLM_JETTON_MASTER_ADDRESS=EQ...',
  'TON_GLM_TREASURY_ADDRESS=EQ...',
  `TON_GLM_METADATA_URL=${metadataUrl || 'https://partner.glamejewelry.ru/static/glm_policy/jetton-metadata.json'}`,
  '```',
  '',
  '## Stop Conditions',
  '',
  '- Do not deploy to mainnet.',
  '- Do not continue if `reference:status` does not match the lock.',
  '- Do not process partner claims until `record:deploy` is done and admin readiness has no deploy blockers.',
  '- Do not mark a GLM claim processed without a TON tx hash.',
];

const output = `${lines.join('\n')}\n`;
if (process.argv.includes('--write')) {
  const outDir = path.resolve(rootDir, 'generated');
  fs.mkdirSync(outDir, { recursive: true });
  const outPath = path.resolve(outDir, 'deploy-testnet-handoff.md');
  fs.writeFileSync(outPath, output, 'utf8');
  console.log(JSON.stringify({ ok: true, path: path.relative(rootDir, outPath) }, null, 2));
} else {
  process.stdout.write(output);
}
