import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const lockPath = resolve(rootDir, 'reference.jetton-contract.lock.json');

function fail(message) {
  console.error(JSON.stringify({ ok: false, error: message }, null, 2));
  process.exit(1);
}

function readLock() {
  if (!existsSync(lockPath)) {
    fail(`Missing lock file: ${lockPath}`);
  }

  try {
    return JSON.parse(readFileSync(lockPath, 'utf8'));
  } catch (error) {
    fail(`Invalid lock JSON: ${error.message}`);
  }
}

const lock = readLock();
const expectedCommit = String(lock.commit || '');

if (!/^[0-9a-f]{40}$/i.test(expectedCommit)) {
  fail('reference.jetton-contract.lock.json must contain a 40-character commit hash');
}

if (!lock.repo || !lock.vendor_path) {
  fail('reference lock must contain repo and vendor_path');
}

const vendorPath = resolve(rootDir, lock.vendor_path);
const result = {
  ok: true,
  name: lock.name,
  repo: lock.repo,
  branch: lock.branch,
  expected_commit: expectedCommit,
  vendor_path: lock.vendor_path,
  vendored: false,
  status: 'locked_not_vendored',
};

if (existsSync(vendorPath)) {
  if (!statSync(vendorPath).isDirectory()) {
    fail(`Vendor path exists but is not a directory: ${vendorPath}`);
  }

  try {
    const actualCommit = execFileSync('git', ['-C', vendorPath, 'rev-parse', 'HEAD'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim();
    result.vendored = true;
    result.actual_commit = actualCommit;
    result.status = actualCommit === expectedCommit ? 'vendored_matching_lock' : 'vendored_mismatch';
    result.ok = actualCommit === expectedCommit;
  } catch (error) {
    fail(`Vendor path is not a readable git checkout: ${error.message}`);
  }
}

console.log(JSON.stringify(result, null, 2));
process.exit(result.ok ? 0 : 1);
