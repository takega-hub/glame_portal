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
  console.error('Refusing to record mainnet deployment without --allow-mainnet true.');
  process.exit(2);
}

const artifactPath = path.resolve(process.cwd(), 'glm-jetton.mainnet.json');
const artifact = JSON.parse(fs.readFileSync(artifactPath, 'utf8'));
const jettonMasterAddress = nonEmpty(args.jettonMasterAddress) || nonEmpty(process.env.TON_GLM_JETTON_MASTER_ADDRESS);
const deployTxHash = nonEmpty(args.deployTxHash);
const adminAddress = nonEmpty(args.adminAddress) || nonEmpty(process.env.TON_JETTON_ADMIN_ADDRESS) || artifact.contracts?.admin_address;
const treasuryAddress = nonEmpty(args.treasuryAddress) || nonEmpty(process.env.TON_GLM_PRODUCTION_TREASURY_ADDRESS) || artifact.contracts?.treasury_address;
const walletCodeHash = nonEmpty(args.walletCodeHash);
const deployer = nonEmpty(args.deployer);

const errors = [];
if (!jettonMasterAddress) errors.push('Missing --jetton-master-address or TON_GLM_JETTON_MASTER_ADDRESS');
if (!deployTxHash) errors.push('Missing --deploy-tx-hash');
if (!adminAddress) errors.push('Missing --admin-address or TON_JETTON_ADMIN_ADDRESS');
if (!treasuryAddress) errors.push('Missing --treasury-address or TON_GLM_PRODUCTION_TREASURY_ADDRESS');
if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

artifact.network = 'mainnet';
artifact.contracts = {
  ...artifact.contracts,
  implementation: artifact.contracts?.implementation || 'standard_tep74_jetton',
  jetton_master_address: jettonMasterAddress,
  jetton_wallet_code_hash: walletCodeHash,
  admin_address: adminAddress,
  treasury_address: treasuryAddress,
};
artifact.deployment = {
  ...artifact.deployment,
  status: 'mainnet_deployed',
  deployed_at: nonEmpty(args.deployedAt) || new Date().toISOString(),
  deploy_tx_hash: deployTxHash,
  deployer,
};

fs.writeFileSync(artifactPath, `${JSON.stringify(artifact, null, 2)}\n`, 'utf8');
console.log(JSON.stringify({
  ok: true,
  artifact: artifactPath,
  network: artifact.network,
  jetton_master_address: artifact.contracts.jetton_master_address,
  treasury_address: artifact.contracts.treasury_address,
  deploy_tx_hash: artifact.deployment.deploy_tx_hash,
  backend_env: {
    TON_NETWORK: 'mainnet',
    TON_GLM_JETTON_MASTER_ADDRESS: artifact.contracts.jetton_master_address,
    TON_GLM_TREASURY_ADDRESS: artifact.contracts.treasury_address,
    TON_GLM_METADATA_URL: artifact.token?.metadata_url || null,
  },
}, null, 2));
