#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

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

function nonEmpty(value) {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null;
}

function toBaseUnits(amount, decimals) {
  const raw = String(amount).trim();
  if (!/^\d+(\.\d+)?$/.test(raw)) {
    throw new Error(`Invalid amount: ${amount}`);
  }
  const [whole, fraction = ''] = raw.split('.');
  const padded = fraction.padEnd(decimals, '0').slice(0, decimals);
  return `${whole}${padded}`.replace(/^0+(?=\d)/, '') || '0';
}

const args = parseArgs(process.argv.slice(2));
if (args.allowMainnet !== 'true') {
  console.error('Refusing to record mainnet mint without --allow-mainnet true.');
  process.exit(2);
}

const artifactPath = path.resolve(process.cwd(), 'glm-jetton.mainnet.json');
const artifact = JSON.parse(fs.readFileSync(artifactPath, 'utf8'));
const decimals = Number.parseInt(String(artifact.token?.decimals ?? '9'), 10);
const amountGlm = nonEmpty(args.amountGlm);
const destinationAddress = nonEmpty(args.destinationAddress) || artifact.contracts?.treasury_address;
const jettonWalletAddress = nonEmpty(args.jettonWalletAddress);
const mintTxHash = nonEmpty(args.mintTxHash);
const status = nonEmpty(args.status) || 'wallet_visible';

const errors = [];
if (!amountGlm) errors.push('Missing --amount-glm');
if (!destinationAddress) errors.push('Missing --destination-address');
if (!jettonWalletAddress) errors.push('Missing --jetton-wallet-address');
if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

artifact.mainnet_mints = Array.isArray(artifact.mainnet_mints) ? artifact.mainnet_mints : [];
artifact.mainnet_mints.push({
  kind: nonEmpty(args.kind) || 'initial_bank_mint',
  status,
  amount_glm: amountGlm,
  amount_base_units: nonEmpty(args.amountBaseUnits) || toBaseUnits(amountGlm, decimals),
  destination_address: destinationAddress,
  jetton_wallet_address: jettonWalletAddress,
  tx_hash: mintTxHash,
  recorded_at: nonEmpty(args.recordedAt) || new Date().toISOString(),
  note: nonEmpty(args.note) || 'Mainnet mint is visible in treasury wallet UI; Toncenter verification can be repeated after rate limit clears.',
});

fs.writeFileSync(artifactPath, `${JSON.stringify(artifact, null, 2)}\n`, 'utf8');
console.log(JSON.stringify({
  ok: true,
  artifact: artifactPath,
  amount_glm: amountGlm,
  destination_address: destinationAddress,
  jetton_wallet_address: jettonWalletAddress,
  status,
}, null, 2));
