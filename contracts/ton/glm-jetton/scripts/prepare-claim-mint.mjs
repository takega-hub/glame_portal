#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

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

function parseCsv(content) {
  const lines = content.trim().split(/\r?\n/).filter(Boolean);
  if (!lines.length) return [];
  const headers = splitCsvLine(lines[0]);
  return lines.slice(1).map((line) => {
    const values = splitCsvLine(line);
    return Object.fromEntries(headers.map((header, index) => [header, values[index] || '']));
  });
}

function fail(message, extra = {}) {
  console.error(JSON.stringify({ ok: false, error: message, ...extra }, null, 2));
  process.exit(1);
}

const args = parseArgs(process.argv.slice(2));
const csvPath = args.csv || args.claimCsv || args.file;
if (!csvPath) {
  fail('Usage: npm run mint:prepare-claim -- --csv ./pending-claims.csv [--claim-id ...]');
}

const absoluteCsvPath = path.resolve(process.cwd(), csvPath);
if (!fs.existsSync(absoluteCsvPath)) {
  fail(`CSV not found: ${absoluteCsvPath}`);
}

const rows = parseCsv(fs.readFileSync(absoluteCsvPath, 'utf8'));
const pendingRows = rows.filter((row) => (row.status || '').toLowerCase() === 'pending');
const selected = args.claimId
  ? pendingRows.find((row) => row.claim_id === args.claimId)
  : pendingRows[0];

if (!selected) {
  fail('No pending claim row matched', {
    claim_id: args.claimId || null,
    pending_count: pendingRows.length,
    rows_count: rows.length,
  });
}

const amount = Number.parseInt(selected.amount_glm || '0', 10);
const issues = [];
if (!selected.claim_id) issues.push('missing_claim_id');
if (!selected.wallet_address) issues.push('missing_wallet_address');
if (!Number.isSafeInteger(amount) || amount <= 0) issues.push('invalid_amount');
if ((selected.ton_network || '') !== 'testnet') issues.push('network_not_testnet');
if (!selected.jetton_master_address) issues.push('missing_jetton_master_address');
if (issues.length) {
  fail('Selected claim is not ready for TON mint', {
    claim_id: selected.claim_id || null,
    issues,
  });
}

const prepareOutput = execFileSync(
  'node',
  [
    'scripts/prepare-mint-operation.mjs',
    '--destination',
    selected.wallet_address,
    '--amount',
    String(amount),
    '--jetton-master-address',
    selected.jetton_master_address,
  ],
  {
    cwd: process.cwd(),
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    env: process.env,
  }
);

const prepared = JSON.parse(prepareOutput);
console.log(JSON.stringify({
  ok: true,
  claim: {
    claim_id: selected.claim_id,
    amount_glm: amount,
    wallet_address: selected.wallet_address,
    partner_name: selected.partner_name || null,
    partner_phone: selected.partner_phone || null,
    created_at: selected.created_at || null,
  },
  prepared_mint: prepared,
  after_tx_action: 'Paste TON tx hash into GLAME admin claim queue and mark claim processed',
}, null, 2));
