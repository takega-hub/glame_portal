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

const args = parseArgs(process.argv.slice(2));
if (args.allowMainnet !== 'true') {
  console.error('Refusing to record mainnet content update without --allow-mainnet true.');
  process.exit(2);
}

const artifactPath = path.resolve(process.cwd(), 'glm-jetton.mainnet.json');
const artifact = JSON.parse(fs.readFileSync(artifactPath, 'utf8'));
const metadataUrl = nonEmpty(args.metadataUrl) || artifact.token?.metadata_url;
const imageUrl = nonEmpty(args.imageUrl) || artifact.token?.image;
const jettonMasterAddress = nonEmpty(args.jettonMasterAddress) || artifact.contracts?.jetton_master_address;
const adminAddress = nonEmpty(args.adminAddress) || artifact.contracts?.admin_address;
const contentTxHash = nonEmpty(args.contentTxHash);

const errors = [];
if (!metadataUrl) errors.push('Missing metadata URL');
if (!imageUrl) errors.push('Missing image URL');
if (!jettonMasterAddress) errors.push('Missing Jetton master address');
if (!adminAddress) errors.push('Missing admin address');
if (!contentTxHash) errors.push('Missing --content-tx-hash');
if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

artifact.metadata_updates = [
  ...(Array.isArray(artifact.metadata_updates) ? artifact.metadata_updates : []),
  {
    status: nonEmpty(args.status) || 'submitted',
    metadata_url: metadataUrl,
    image_url: imageUrl,
    jetton_master_address: jettonMasterAddress,
    admin_address: adminAddress,
    tx_hash: contentTxHash,
    recorded_at: new Date().toISOString(),
    note: nonEmpty(args.note) || 'Mainnet GLM Jetton metadata content URI update submitted.',
  },
];

fs.writeFileSync(artifactPath, `${JSON.stringify(artifact, null, 2)}\n`, 'utf8');
console.log(JSON.stringify({
  ok: true,
  artifact: artifactPath,
  metadata_url: metadataUrl,
  image_url: imageUrl,
  jetton_master_address: jettonMasterAddress,
  tx_hash: contentTxHash,
}, null, 2));
