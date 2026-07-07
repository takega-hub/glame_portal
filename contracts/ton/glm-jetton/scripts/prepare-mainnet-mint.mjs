#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const rootDir = process.cwd();

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

function formatUnits(value, decimals, unitMultiplier) {
  if (decimals === 0) return value.toString();
  const whole = value / unitMultiplier;
  const fraction = value % unitMultiplier;
  if (fraction === 0n) return whole.toString();
  return `${whole.toString()}.${fraction.toString().padStart(decimals, '0').replace(/0+$/, '')}`;
}

const args = parseArgs(process.argv.slice(2));
if (args.allowMainnet !== 'true') fail('Refusing mainnet mint preparation without --allow-mainnet true');
if (args.allowLarge !== 'true') fail('Refusing large mainnet mint without --allow-large true');

const env = { ...loadDotEnv(path.resolve(rootDir, '.env')), ...process.env };
const artifact = loadJson(path.resolve(rootDir, 'glm-jetton.mainnet.json'));
const lock = loadJson(path.resolve(rootDir, 'reference.jetton-contract.lock.json'));
const vendorPath = path.resolve(rootDir, lock.vendor_path || '');
const network = env.TON_NETWORK || artifact.network || 'mainnet';
if (network !== 'mainnet') fail('TON_NETWORK must be mainnet for GLM mainnet mint');
if (!fs.existsSync(vendorPath)) fail('Pinned Jetton reference is missing. Run npm run reference:fetch first.');

const jettonMasterAddress = args.jettonMasterAddress || env.TON_GLM_JETTON_MASTER_ADDRESS || artifact.contracts?.jetton_master_address;
const destinationAddress = args.destination || env.TON_GLM_PRODUCTION_TREASURY_ADDRESS || artifact.contracts?.treasury_address;
const adminAddress = env.TON_JETTON_ADMIN_ADDRESS || artifact.contracts?.admin_address;
const decimals = Number.parseInt(String(artifact.token?.decimals ?? env.TON_GLM_DECIMALS ?? '9'), 10);
const unitMultiplier = 10n ** BigInt(decimals);
const amount = Number.parseInt(args.amount || env.TON_GLM_MAINNET_INITIAL_MINT_AMOUNT || '10000000', 10);
const amountBaseUnits = args.baseUnits ? BigInt(args.baseUnits) : BigInt(amount) * unitMultiplier;
const displayAmount = args.baseUnits ? formatUnits(amountBaseUnits, decimals, unitMultiplier) : String(amount);

if (!jettonMasterAddress) fail('Missing --jetton-master-address or TON_GLM_JETTON_MASTER_ADDRESS');
if (!destinationAddress) fail('Missing --destination or TON_GLM_PRODUCTION_TREASURY_ADDRESS');
if (!adminAddress) fail('Missing TON_JETTON_ADMIN_ADDRESS or artifact contracts.admin_address');
if (!Number.isSafeInteger(decimals) || decimals < 0 || decimals > 18) fail('Token decimals must be an integer between 0 and 18');
if (!args.baseUnits && (!Number.isSafeInteger(amount) || amount <= 0)) fail('Mint amount must be a positive integer GLM amount');
if (amountBaseUnits <= 0n) fail('Mint base units must be positive');

try {
  const requireFromVendor = createRequire(path.resolve(vendorPath, 'package.json'));
  const { Address } = requireFromVendor('@ton/core');
  Address.parse(jettonMasterAddress);
  Address.parse(destinationAddress);
  Address.parse(adminAddress);
} catch (error) {
  fail(`Invalid TON address in mint operation: ${error.message}`);
}

const scriptPath = path.resolve(vendorPath, 'scripts', 'mintGlmJetton.ts');
const script = `import { Address } from '@ton/core';
import { NetworkProvider } from '@ton/blueprint';
import { JettonMinter } from '../wrappers/JettonMinter';

const GLM_JETTON_MASTER = ${quoteTs(jettonMasterAddress)};
const GLM_DESTINATION = ${quoteTs(destinationAddress)};
const GLM_ADMIN_ADDRESS = ${quoteTs(adminAddress)};
const GLM_DECIMALS = ${JSON.stringify(decimals)};
const GLM_AMOUNT = BigInt(${JSON.stringify(amountBaseUnits.toString())});
const GLM_DISPLAY_AMOUNT = ${quoteTs(displayAmount)};

export async function run(provider: NetworkProvider) {
    if (provider.network() !== 'mainnet') {
        throw new Error('GLM mainnet mint must run on mainnet only');
    }

    const ui = provider.ui();
    const minter = provider.open(JettonMinter.createFromAddress(Address.parse(GLM_JETTON_MASTER)));
    const destination = Address.parse(GLM_DESTINATION);
    const sender = provider.sender();
    if (!sender.address || !sender.address.equals(Address.parse(GLM_ADMIN_ADDRESS))) {
        throw new Error('Connected wallet must match configured GLM Jetton admin');
    }

    ui.write('GLM Jetton master: ' + minter.address.toString());
    ui.write('GLM mint destination: ' + destination.toString());
    ui.write('GLM amount: ' + GLM_DISPLAY_AMOUNT + ' GLM');
    ui.write('GLM base units: ' + GLM_AMOUNT.toString() + ' (decimals=' + GLM_DECIMALS + ')');

    await minter.sendMint(sender, destination, GLM_AMOUNT);
    ui.write('Mint transaction sent. Verify supply/balance after confirmation.');
}
`;

fs.writeFileSync(scriptPath, script, 'utf8');
const endpoint = env.TON_ENDPOINT || 'https://toncenter.com/api/v2/jsonRPC';
console.log(JSON.stringify({
  ok: true,
  generated_script: path.relative(rootDir, scriptPath),
  network,
  jetton_master_address: jettonMasterAddress,
  destination_address: destinationAddress,
  admin_address: adminAddress,
  amount_glm: displayAmount,
  decimals,
  amount_base_units: amountBaseUnits.toString(),
  commands: {
    run_mint: `cd ${path.relative(rootDir, vendorPath)} && npx blueprint run mintGlmJetton --custom ${endpoint} --custom-version v2 --custom-type mainnet${env.TON_API_KEY ? ' --custom-key $TON_API_KEY' : ''}`,
    verify: `cd ${rootDir} && TON_NETWORK=mainnet TON_ENDPOINT=${endpoint} npm run mint:status -- --artifact glm-jetton.mainnet.json --destination ${destinationAddress}`,
  },
}, null, 2));
