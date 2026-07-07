#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const rootDir = process.cwd();
const artifactPath = path.resolve(rootDir, 'glm-jetton.mainnet.json');
const lockPath = path.resolve(rootDir, 'reference.jetton-contract.lock.json');

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (!item.startsWith('--')) continue;
    const key = item.slice(2).replace(/-([a-z])/g, (_, char) => char.toUpperCase());
    const next = argv[index + 1];
    if (!next || next.startsWith('--')) {
      args[key] = 'true';
    } else {
      args[key] = next;
      index += 1;
    }
  }
  return args;
}

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
  if (!fs.existsSync(vendorPath)) fail('Pinned Jetton reference is missing. Run npm run reference:fetch first.');
  const actualCommit = execFileSync('git', ['-C', vendorPath, 'rev-parse', 'HEAD'], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
  if (actualCommit !== lock.commit) fail(`Pinned Jetton reference mismatch: expected ${lock.commit}, got ${actualCommit}`);
  return vendorPath;
}

function quoteTs(value) {
  return JSON.stringify(String(value));
}

const args = parseArgs(process.argv.slice(2));
if (args.allowMainnet !== 'true') fail('Refusing mainnet deploy preparation without --allow-mainnet true');

const env = { ...loadDotEnv(path.resolve(rootDir, '.env')), ...process.env };
const artifact = loadJson(artifactPath);
const lock = loadJson(lockPath);
const vendorPath = assertReference(lock);
const network = env.TON_NETWORK || artifact.network || 'mainnet';
if (network !== 'mainnet') fail('TON_NETWORK must be mainnet for GLM mainnet deploy');

const metadataUrl = env.TON_GLM_METADATA_URL || artifact.token?.metadata_url;
const adminAddress = env.TON_JETTON_ADMIN_ADDRESS || env.TON_GLM_PRODUCTION_TREASURY_ADDRESS || artifact.contracts?.admin_address;
if (!metadataUrl) fail('TON_GLM_METADATA_URL or artifact token.metadata_url is required');
if (!adminAddress) fail('TON_JETTON_ADMIN_ADDRESS or TON_GLM_PRODUCTION_TREASURY_ADDRESS is required');

try {
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
    if (provider.network() !== 'mainnet') {
        throw new Error('GLM mainnet deploy must run on mainnet only');
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
    ui.write('GLM Jetton admin: ' + admin.toString());
    ui.write('GLM Jetton minter address: ' + minter.address.toString());
    await minter.sendDeploy(provider.sender(), toNano('0.5'));
}
`;

fs.writeFileSync(scriptPath, deployScript, 'utf8');

const endpoint = env.TON_ENDPOINT || 'https://toncenter.com/api/v2/jsonRPC';
console.log(JSON.stringify({
  ok: true,
  generated_script: path.relative(rootDir, scriptPath),
  artifact: path.relative(rootDir, artifactPath),
  reference_commit: lock.commit,
  network,
  metadata_url: metadataUrl,
  admin_address: adminAddress,
  commands: {
    install_reference_deps: `cd ${path.relative(rootDir, vendorPath)} && npm install`,
    build_reference: `cd ${path.relative(rootDir, vendorPath)} && npm run build`,
    deploy_mainnet: `cd ${path.relative(rootDir, vendorPath)} && npx blueprint run deployGlmJettonMinter --custom ${endpoint} --custom-version v2 --custom-type mainnet${env.TON_API_KEY ? ' --custom-key $TON_API_KEY' : ''}`,
  },
}, null, 2));
