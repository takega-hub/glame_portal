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

const args = parseArgs(process.argv.slice(2));
const env = { ...loadDotEnv(path.resolve(rootDir, '.env')), ...process.env };
const artifact = loadJson(path.resolve(rootDir, 'glm-jetton.testnet.json'));
const lock = loadJson(path.resolve(rootDir, 'reference.jetton-contract.lock.json'));
const vendorPath = path.resolve(rootDir, lock.vendor_path || '');

const network = env.TON_NETWORK || artifact.network || 'testnet';
const jettonMasterAddress = args.jettonMasterAddress || env.TON_GLM_JETTON_MASTER_ADDRESS || artifact.contracts?.jetton_master_address;
const treasuryAddress = args.from || env.TON_GLM_TREASURY_ADDRESS || artifact.contracts?.treasury_address;
const destinationAddress = args.destination || env.TON_GLM_AUTO_TRANSFER_HOT_WALLET_ADDRESS;
const decimals = Number.parseInt(String(artifact.token?.decimals ?? env.TON_GLM_DECIMALS ?? '9'), 10);
const unitMultiplier = 10n ** BigInt(decimals);
const amount = Number.parseInt(args.amount || '0', 10);
const amountBaseUnits = args.baseUnits ? BigInt(args.baseUnits) : BigInt(amount) * unitMultiplier;
const transferTonValue = args.value || env.TON_GLM_TRANSFER_TX_VALUE_TON || '0.15';
const forwardNanoton = args.forwardNanoton || env.TON_GLM_AUTO_TRANSFER_FORWARD_NANOTON || '1';

if (network !== 'testnet') fail('TON_NETWORK must be testnet for GLM refill transfer');
if (!fs.existsSync(vendorPath)) fail('Pinned Jetton reference is missing. Run npm run reference:fetch first.');
if (!jettonMasterAddress) fail('Missing Jetton master address');
if (!treasuryAddress) fail('Missing treasury/admin --from address');
if (!destinationAddress) fail('Missing --destination or TON_GLM_AUTO_TRANSFER_HOT_WALLET_ADDRESS');
if (!Number.isSafeInteger(decimals) || decimals < 0 || decimals > 18) fail('Token decimals must be an integer between 0 and 18');
if (!args.baseUnits && (!Number.isSafeInteger(amount) || amount <= 0)) fail('Refill amount must be a positive integer GLM amount');
if (amountBaseUnits <= 0n) fail('Refill base units must be positive');

try {
  const requireFromVendor = createRequire(path.resolve(vendorPath, 'package.json'));
  const { Address } = requireFromVendor('@ton/core');
  Address.parse(jettonMasterAddress);
  Address.parse(treasuryAddress);
  Address.parse(destinationAddress);
} catch (error) {
  fail(`Invalid TON address in refill operation: ${error.message}`);
}

const scriptPath = path.resolve(vendorPath, 'scripts', 'transferGlmRefill.ts');
const script = `import { Address, beginCell, toNano } from '@ton/core';
import { NetworkProvider } from '@ton/blueprint';
import { JettonMinter } from '../wrappers/JettonMinter';
import { JettonWallet } from '../wrappers/JettonWallet';

const GLM_JETTON_MASTER = ${quoteTs(jettonMasterAddress)};
const GLM_TREASURY = ${quoteTs(treasuryAddress)};
const GLM_DESTINATION = ${quoteTs(destinationAddress)};
const GLM_AMOUNT = BigInt(${JSON.stringify(amountBaseUnits.toString())});
const GLM_DISPLAY_AMOUNT = ${quoteTs(args.baseUnits ? amountBaseUnits.toString() : String(amount))};
const TRANSFER_TON_VALUE = ${quoteTs(transferTonValue)};
const FORWARD_NANOTON = BigInt(${JSON.stringify(String(forwardNanoton))});

export async function run(provider: NetworkProvider) {
    if (provider.network() === 'mainnet') {
        throw new Error('GLM refill transfer is testnet-only');
    }

    const sender = provider.sender();
    const treasury = Address.parse(GLM_TREASURY);
    if (!sender.address || !sender.address.equals(treasury)) {
        throw new Error('Connected wallet must match configured GLM treasury/admin');
    }

    const ui = provider.ui();
    const minter = provider.open(JettonMinter.createFromAddress(Address.parse(GLM_JETTON_MASTER)));
    const treasuryJettonWalletAddress = await minter.getWalletAddress(treasury);
    const treasuryJettonWallet = provider.open(JettonWallet.createFromAddress(treasuryJettonWalletAddress));
    const destination = Address.parse(GLM_DESTINATION);

    ui.write('GLM treasury wallet: ' + treasury.toString({ testOnly: true }));
    ui.write('GLM treasury Jetton wallet: ' + treasuryJettonWalletAddress.toString({ testOnly: true }));
    ui.write('GLM refill destination hot-wallet: ' + destination.toString({ testOnly: true }));
    ui.write('GLM refill amount: ' + GLM_DISPLAY_AMOUNT + ' GLM');

    await treasuryJettonWallet.sendTransfer(
        sender,
        toNano(TRANSFER_TON_VALUE),
        GLM_AMOUNT,
        destination,
        treasury,
        null,
        FORWARD_NANOTON,
        beginCell().storeUint(0, 32).endCell(),
    );
    ui.write('Refill transfer transaction sent. Verify hot-wallet balance after confirmation.');
}
`;

fs.writeFileSync(scriptPath, script, 'utf8');

console.log(JSON.stringify({
  ok: true,
  generated_script: path.relative(rootDir, scriptPath),
  network,
  jetton_master_address: jettonMasterAddress,
  treasury_address: treasuryAddress,
  destination_address: destinationAddress,
  amount_glm: args.baseUnits ? amountBaseUnits.toString() : String(amount),
  decimals,
  amount_base_units: amountBaseUnits.toString(),
  commands: {
    run_transfer: `cd ${path.relative(rootDir, vendorPath)} && npx blueprint run transferGlmRefill --custom ${env.TON_ENDPOINT || 'https://testnet.toncenter.com/api/v2/jsonRPC'} --custom-version v2 --custom-type testnet${env.TON_API_KEY ? ' --custom-key $TON_API_KEY' : ''}`,
  },
}, null, 2));
