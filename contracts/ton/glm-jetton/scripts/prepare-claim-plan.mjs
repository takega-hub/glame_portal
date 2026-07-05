#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

function parseCsv(content) {
  const lines = content.trim().split(/\r?\n/);
  if (!lines.length) return [];
  const headers = splitCsvLine(lines[0]);
  return lines.slice(1).filter(Boolean).map((line) => {
    const values = splitCsvLine(line);
    return Object.fromEntries(headers.map((header, index) => [header, values[index] || '']));
  });
}

function splitCsvLine(line) {
  const cells = [];
  let cell = '';
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    const next = line[i + 1];
    if (char === '"' && quoted && next === '"') {
      cell += '"';
      i += 1;
      continue;
    }
    if (char === '"') {
      quoted = !quoted;
      continue;
    }
    if (char === ',' && !quoted) {
      cells.push(cell);
      cell = '';
      continue;
    }
    cell += char;
  }
  cells.push(cell);
  return cells;
}

function main() {
  const csvPath = process.argv[2];
  if (!csvPath) {
    console.error('Usage: npm run prepare:claims -- ./pending-claims.csv');
    process.exit(2);
  }
  const absolutePath = path.resolve(process.cwd(), csvPath);
  const rows = parseCsv(fs.readFileSync(absolutePath, 'utf8'));
  const issues = [];
  const transfers = rows.map((row) => {
    const amount = Number.parseInt(row.amount_glm || '0', 10);
    const claimIssues = [];
    if (!row.claim_id) claimIssues.push('missing_claim_id');
    if (!row.wallet_address) claimIssues.push('missing_wallet_address');
    if (!Number.isFinite(amount) || amount <= 0) claimIssues.push('invalid_amount');
    if ((row.ton_network || '') !== 'testnet') claimIssues.push('network_not_testnet');
    if (!row.jetton_master_address) claimIssues.push('missing_jetton_master_address');
    if (claimIssues.length) {
      issues.push({ claim_id: row.claim_id || null, issues: claimIssues });
    }
    return {
      claim_id: row.claim_id,
      destination_wallet: row.wallet_address,
      amount_glm: amount,
      ton_network: row.ton_network || 'testnet',
      jetton_master_address: row.jetton_master_address || null,
      treasury_address: row.treasury_address || null,
      metadata_url: row.metadata_url || null,
      operator_action: row.operator_action || 'mint_or_transfer_testnet_glm_to_wallet',
      after_tx_action: row.after_tx_action || 'paste_ton_tx_hash_and_mark_processed',
      ready: claimIssues.length === 0,
      issues: claimIssues,
    };
  });

  const plan = {
    schema: 'glame_ton_claim_operator_plan_v1',
    generated_at: new Date().toISOString(),
    source_csv: absolutePath,
    rows_count: rows.length,
    ready_count: transfers.filter((item) => item.ready).length,
    blocked_count: transfers.filter((item) => !item.ready).length,
    issues,
    transfers,
  };
  console.log(JSON.stringify(plan, null, 2));
  process.exit(issues.length ? 1 : 0);
}

main();

