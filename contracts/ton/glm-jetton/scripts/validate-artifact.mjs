#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

function main() {
  const artifactPath = path.resolve(process.cwd(), process.argv[2] || 'glm-jetton.testnet.json');
  const artifact = JSON.parse(fs.readFileSync(artifactPath, 'utf8'));
  const errors = [];
  const warnings = [];
  const token = artifact.token || {};
  const contracts = artifact.contracts || {};
  const deployment = artifact.deployment || {};

  if (artifact.network !== 'testnet') errors.push('network must be testnet');
  if (token.symbol !== 'GLM') errors.push('token.symbol must be GLM');
  if (token.decimals !== 9) errors.push('token.decimals must be 9 for TON wallet display compatibility');
  if (!String(token.metadata_url || '').includes('/static/glm_policy/jetton-metadata.json')) {
    errors.push('token.metadata_url must point to GLM policy metadata');
  }
  if (deployment.status === 'testnet_deployed') {
    if (!contracts.jetton_master_address) errors.push('deployed artifact missing contracts.jetton_master_address');
    if (!contracts.admin_address) errors.push('deployed artifact missing contracts.admin_address');
    if (!contracts.treasury_address) errors.push('deployed artifact missing contracts.treasury_address');
    if (!deployment.deploy_tx_hash) errors.push('deployed artifact missing deployment.deploy_tx_hash');
  } else {
    warnings.push('artifact is not testnet_deployed yet');
  }
  if (contracts.implementation && !String(contracts.implementation).includes('tep74')) {
    warnings.push('contracts.implementation should document TEP-74 compatibility');
  }

  const result = {
    ok: errors.length === 0,
    artifact: artifactPath,
    deployment_status: deployment.status || null,
    token: {
      name: token.name || null,
      symbol: token.symbol || null,
      decimals: token.decimals,
      metadata_url: token.metadata_url || null,
    },
    contracts: {
      implementation: contracts.implementation || null,
      jetton_master_address: contracts.jetton_master_address || null,
      admin_address: contracts.admin_address || null,
      treasury_address: contracts.treasury_address || null,
    },
    errors,
    warnings,
  };
  console.log(JSON.stringify(result, null, 2));
  process.exit(errors.length ? 1 : 0);
}

main();
