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

function fail(message) {
  console.error(JSON.stringify({ ok: false, error: message }, null, 2));
  process.exit(1);
}

function assertReference(lock) {
  const vendorPath = path.resolve(rootDir, lock.vendor_path || '');
  if (!fs.existsSync(vendorPath)) {
    fail('Pinned Jetton reference is missing. Run npm run reference:fetch first.');
  }
  const actualCommit = execFileSync('git', ['-C', vendorPath, 'rev-parse', 'HEAD'], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
  if (actualCommit !== lock.commit) {
    fail(`Pinned Jetton reference mismatch: expected ${lock.commit}, got ${actualCommit}`);
  }
  return vendorPath;
}

function quoteTs(value) {
  return JSON.stringify(String(value));
}

const lock = loadJson(lockPath);
const artifact = loadJson(artifactPath);
const vendorPath = assertReference(lock);
const env = { ...loadDotEnv(path.resolve(rootDir, '.env')), ...process.env };

const network = env.TON_NETWORK || artifact.network || 'testnet';
if (network !== 'testnet') {
  fail('TON_NETWORK must be testnet for GLM pilot deploy');
}

const metadataUrl = env.TON_GLM_METADATA_URL || artifact.token?.metadata_url;
const adminAddress = env.TON_JETTON_ADMIN_ADDRESS || artifact.contracts?.admin_address;
if (!metadataUrl) fail('TON_GLM_METADATA_URL or artifact token.metadata_url is required');
if (!adminAddress) fail('TON_JETTON_ADMIN_ADDRESS or artifact contracts.admin_address is required');

try {
  // URL constructor keeps this check dependency-free.
  new URL(metadataUrl);
} catch {
  fail(`Invalid metadata URL: ${metadataUrl}`);
}

const scriptPath = path.resolve(vendorPath, 'scripts', 'deployGlmJettonMinter.ts');
const deployScript = `import { Address, toNano } from '@ton/core';
import { compile, NetworkProvider } from '@ton/blueprint';
import { JettonMinter } from '../wrappers/JettonMinter';

const GLM_ADMIN_ADDRESS = ${quoteTs(adminAddress)};
const GLM_METADATA_URI = ${quoteTs(metadataUrl)};

export async function run(provider: NetworkProvider) {
    if (provider.network() === 'mainnet') {
        throw new Error('GLM pilot deploy is testnet-only');
    }

    const ui = provider.ui();
    const admin = Address.parse(GLM_ADMIN_ADDRESS);
    const jettonWalletCode = await compile('JettonWallet');
    const jettonMinterCode = await compile('JettonMinter');
    const minter = provider.open(JettonMinter.createFromConfig({
        admin,
        wallet_code: jettonWalletCode,
        jetton_content: { uri: GLM_METADATA_URI },
    }, jettonMinterCode));

    ui.write('GLM Jetton metadata: ' + GLM_METADATA_URI);
    ui.write('GLM Jetton admin: ' + admin.toString({ testOnly: true }));
    ui.write('GLM Jetton minter address: ' + minter.address.toString({ testOnly: true }));
    await minter.sendDeploy(provider.sender(), toNano('0.5'));
}
`;

fs.writeFileSync(scriptPath, deployScript, 'utf8');

const commands = {
  install_reference_deps: `cd ${path.relative(rootDir, vendorPath)} && npm install`,
  build_reference: `cd ${path.relative(rootDir, vendorPath)} && npm run build`,
  deploy_testnet: `cd ${path.relative(rootDir, vendorPath)} && npx blueprint run deployGlmJettonMinter --custom ${env.TON_ENDPOINT || 'https://testnet.toncenter.com/api/v2/'} --custom-version v2 --custom-type testnet${env.TON_API_KEY ? ' --custom-key $TON_API_KEY' : ''}`,
  check_wallet_library: `cd ${path.relative(rootDir, vendorPath)} && npx blueprint run checkWalletLib --custom ${env.TON_ENDPOINT || 'https://testnet.toncenter.com/api/v2/'} --custom-version v2 --custom-type testnet${env.TON_API_KEY ? ' --custom-key $TON_API_KEY' : ''}`,
};

console.log(JSON.stringify({
  ok: true,
  generated_script: path.relative(rootDir, scriptPath),
  reference_commit: lock.commit,
  network,
  metadata_url: metadataUrl,
  admin_address: adminAddress,
  commands,
}, null, 2));
