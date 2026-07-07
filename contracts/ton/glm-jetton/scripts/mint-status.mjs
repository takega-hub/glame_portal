#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

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

function runTsNode(script, args, cwd) {
  const result = spawnSync('npx', ['ts-node', script, ...args], {
    cwd,
    encoding: 'utf8',
  });
  if (result.status !== 0) {
    throw new Error(result.stderr || result.stdout || `node exited with ${result.status}`);
  }
  return JSON.parse(result.stdout);
}

const args = parseArgs(process.argv.slice(2));
const env = { ...loadDotEnv(path.resolve(rootDir, '.env')), ...process.env };
const network = String(args.network || env.TON_NETWORK || 'testnet').toLowerCase();
const artifactFile = args.artifact || (network === 'mainnet' ? 'glm-jetton.mainnet.json' : 'glm-jetton.testnet.json');
const artifact = loadJson(path.resolve(rootDir, artifactFile));
const lock = loadJson(path.resolve(rootDir, 'reference.jetton-contract.lock.json'));
const vendorPath = path.resolve(rootDir, lock.vendor_path || '');
const jettonMasterAddress = args.jettonMasterAddress || env.TON_GLM_JETTON_MASTER_ADDRESS || artifact.contracts?.jetton_master_address;
const destinationAddress = args.destination || env.TON_GLM_TEST_MINT_DESTINATION || env.TON_GLM_TREASURY_ADDRESS || artifact.contracts?.treasury_address;
const decimals = Number.parseInt(String(artifact.token?.decimals ?? env.TON_GLM_DECIMALS ?? '9'), 10);
const isTestnet = network !== 'mainnet';

function formatUnits(value, precision) {
  const raw = BigInt(value);
  if (precision === 0) return raw.toString();
  const multiplier = 10n ** BigInt(precision);
  const whole = raw / multiplier;
  const fraction = raw % multiplier;
  if (fraction === 0n) return whole.toString();
  return `${whole.toString()}.${fraction.toString().padStart(precision, '0').replace(/0+$/, '')}`;
}

if (!jettonMasterAddress || !destinationAddress) {
  console.error(JSON.stringify({ ok: false, error: 'Missing Jetton master or destination address' }, null, 2));
  process.exit(1);
}

const probePath = path.resolve(vendorPath, 'scripts', '.glmMintStatusProbe.ts');
const apiKey = env.TON_API_KEY || env.TONCENTER_API_KEY || '';

fs.writeFileSync(probePath, `import { TonClient, Address } from '@ton/ton';
import { JettonMinter } from '../wrappers/JettonMinter';
import { JettonWallet } from '../wrappers/JettonWallet';

async function main() {
  const network = process.env.TON_NETWORK || 'testnet';
  const endpoint = process.env.TON_ENDPOINT || (network === 'mainnet' ? 'https://toncenter.com/api/v2/jsonRPC' : 'https://testnet.toncenter.com/api/v2/jsonRPC');
  const isTestnet = network !== 'mainnet';
  const client = new TonClient({ endpoint, apiKey: process.env.TON_API_KEY || process.env.TONCENTER_API_KEY || undefined });
  const minter = client.open(JettonMinter.createFromAddress(Address.parse(process.argv[2])));
  const destination = Address.parse(process.argv[3]);
  const walletAddress = await minter.getWalletAddress(destination);
  const wallet = client.open(JettonWallet.createFromAddress(walletAddress));
  const data = await minter.getJettonData();
  const balance = await wallet.getJettonBalance();
  console.log(JSON.stringify({
    ok: true,
    network,
    jetton_master_address: process.argv[2],
    destination_address: process.argv[3],
    jetton_wallet_address: walletAddress.toString({ testOnly: isTestnet }),
    total_supply: data.totalSupply.toString(),
    destination_balance: balance.toString(),
    admin_address: data.adminAddress?.toString({ testOnly: isTestnet }) || null,
  }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
`, 'utf8');

try {
  process.env.TON_NETWORK = network;
  if (apiKey && !process.env.TON_API_KEY) {
    process.env.TON_API_KEY = apiKey;
  }
  const status = runTsNode(probePath, [jettonMasterAddress, destinationAddress], vendorPath);
  console.log(JSON.stringify({
    ...status,
    decimals,
    total_supply_glm: formatUnits(status.total_supply, decimals),
    destination_balance_glm: formatUnits(status.destination_balance, decimals),
  }, null, 2));
} catch (error) {
  console.error(JSON.stringify({ ok: false, error: error.message }, null, 2));
  process.exit(1);
}
