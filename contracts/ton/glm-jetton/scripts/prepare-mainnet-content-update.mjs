#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const rootDir = process.cwd();
const DEFAULT_METADATA_URL = 'https://partner.glamejewelry.ru/static/glm_policy/jetton-metadata-mainnet-v2.json';
const DEFAULT_ICON_URL = 'https://partner.glamejewelry.ru/static/glm_policy/glm-token-icon-v3.png';

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

function quoteTs(value) {
  return JSON.stringify(String(value));
}

async function loadLiveMetadata(metadataUrl) {
  const response = await fetch(metadataUrl, {
    headers: { accept: 'application/json' },
  });
  if (!response.ok) {
    fail(`Metadata URL is unavailable: HTTP ${response.status}`);
  }
  return response.json();
}

const args = parseArgs(process.argv.slice(2));
if (args.allowMainnet !== 'true') fail('Refusing mainnet content update without --allow-mainnet true');

const env = { ...loadDotEnv(path.resolve(rootDir, '.env')), ...process.env };
const artifact = loadJson(path.resolve(rootDir, 'glm-jetton.mainnet.json'));
const lock = loadJson(path.resolve(rootDir, 'reference.jetton-contract.lock.json'));
const vendorPath = path.resolve(rootDir, lock.vendor_path || '');
const network = env.TON_NETWORK || artifact.network || 'mainnet';
if (network !== 'mainnet') fail('TON_NETWORK must be mainnet for GLM metadata update');
if (!fs.existsSync(vendorPath)) fail('Pinned Jetton reference is missing. Run npm run reference:fetch first.');

const metadataUrl = args.metadataUrl || env.TON_GLM_METADATA_URL || artifact.token?.metadata_url || DEFAULT_METADATA_URL;
const expectedIconUrl = args.iconUrl || artifact.token?.image || DEFAULT_ICON_URL;
const jettonMasterAddress = args.jettonMasterAddress || env.TON_GLM_JETTON_MASTER_ADDRESS || artifact.contracts?.jetton_master_address;
const adminAddress = args.adminAddress || env.TON_JETTON_ADMIN_ADDRESS || artifact.contracts?.admin_address;

if (!metadataUrl) fail('Missing metadata URL');
if (!jettonMasterAddress) fail('Missing --jetton-master-address or TON_GLM_JETTON_MASTER_ADDRESS');
if (!adminAddress) fail('Missing --admin-address or TON_JETTON_ADMIN_ADDRESS');

try {
  const requireFromVendor = createRequire(path.resolve(vendorPath, 'package.json'));
  const { Address } = requireFromVendor('@ton/core');
  Address.parse(jettonMasterAddress);
  Address.parse(adminAddress);
} catch (error) {
  fail(`Invalid TON address in content update operation: ${error.message}`);
}

let liveMetadata = null;
if (args.skipLive !== 'true') {
  liveMetadata = await loadLiveMetadata(metadataUrl);
  const errors = [];
  if (liveMetadata.name !== 'GLAME Coin') errors.push(`metadata.name must be "GLAME Coin", got ${JSON.stringify(liveMetadata.name)}`);
  if (liveMetadata.symbol !== 'GLM') errors.push(`metadata.symbol must be "GLM", got ${JSON.stringify(liveMetadata.symbol)}`);
  if (String(liveMetadata.decimals) !== '9') errors.push(`metadata.decimals must be "9", got ${JSON.stringify(liveMetadata.decimals)}`);
  if (liveMetadata.image !== expectedIconUrl) errors.push(`metadata.image must be ${expectedIconUrl}, got ${JSON.stringify(liveMetadata.image)}`);
  if (String(liveMetadata.image || '').includes('glame-ton-icon.svg')) errors.push('metadata.image still points to old glame-ton-icon.svg');
  if (/testnet|claim pilot/i.test(String(liveMetadata.description || ''))) {
    errors.push('metadata.description still contains testnet/claim pilot wording');
  }
  if (errors.length) fail(`Live metadata is not production-ready: ${errors.join('; ')}`);
}

const scriptPath = path.resolve(vendorPath, 'scripts', 'updateGlmJettonContent.ts');
const script = `import { Address } from '@ton/core';
import { NetworkProvider } from '@ton/blueprint';
import { JettonMinter } from '../wrappers/JettonMinter';

const GLM_JETTON_MASTER = ${quoteTs(jettonMasterAddress)};
const GLM_ADMIN_ADDRESS = ${quoteTs(adminAddress)};
const GLM_METADATA_URI = ${quoteTs(metadataUrl)};

export async function run(provider: NetworkProvider) {
    if (provider.network() !== 'mainnet') {
        throw new Error('GLM metadata update must run on mainnet only');
    }

    const ui = provider.ui();
    const sender = provider.sender();
    if (!sender.address || !sender.address.equals(Address.parse(GLM_ADMIN_ADDRESS))) {
        throw new Error('Connected wallet must match configured GLM Jetton admin');
    }

    const minter = provider.open(JettonMinter.createFromAddress(Address.parse(GLM_JETTON_MASTER)));
    ui.write('GLM Jetton master: ' + minter.address.toString());
    ui.write('GLM metadata URI: ' + GLM_METADATA_URI);
    ui.write('GLM admin: ' + sender.address.toString());

    await minter.sendChangeContent(sender, { uri: GLM_METADATA_URI });
    ui.write('Metadata update transaction sent. Verify wallet metadata after confirmation/cache refresh.');
}
`;

fs.writeFileSync(scriptPath, script, 'utf8');
const endpoint = env.TON_ENDPOINT || 'https://toncenter.com/api/v2/jsonRPC';
console.log(JSON.stringify({
  ok: true,
  generated_script: path.relative(rootDir, scriptPath),
  network,
  jetton_master_address: jettonMasterAddress,
  admin_address: adminAddress,
  metadata_url: metadataUrl,
  metadata_name: liveMetadata?.name || null,
  metadata_description: liveMetadata?.description || null,
  metadata_image: liveMetadata?.image || null,
  commands: {
    run_update: `cd ${path.relative(rootDir, vendorPath)} && npx blueprint run updateGlmJettonContent --custom ${endpoint} --custom-version v2 --custom-type mainnet${env.TON_API_KEY ? ' --custom-key $TON_API_KEY' : ''}`,
    record_update: `cd ${rootDir} && npm run mainnet:record-content-update -- --content-tx-hash <TON_TX_HASH>`,
  },
}, null, 2));
