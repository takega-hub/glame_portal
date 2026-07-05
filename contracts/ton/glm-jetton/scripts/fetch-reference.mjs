import { existsSync, mkdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const lockPath = resolve(rootDir, 'reference.jetton-contract.lock.json');

function run(command, args, options = {}) {
  return execFileSync(command, args, {
    cwd: rootDir,
    encoding: 'utf8',
    stdio: options.capture ? ['ignore', 'pipe', 'pipe'] : 'inherit',
  });
}

function fail(message) {
  console.error(message);
  process.exit(1);
}

const lock = JSON.parse(readFileSync(lockPath, 'utf8'));
const repo = String(lock.repo || '');
const commit = String(lock.commit || '');
const vendorPath = resolve(rootDir, lock.vendor_path || '');

if (!repo || !/^[0-9a-f]{40}$/i.test(commit) || !lock.vendor_path) {
  fail('Invalid reference lock: repo, commit and vendor_path are required');
}

if (existsSync(vendorPath) && !statSync(vendorPath).isDirectory()) {
  fail(`Vendor path exists but is not a directory: ${vendorPath}`);
}

mkdirSync(dirname(vendorPath), { recursive: true });

if (!existsSync(vendorPath)) {
  run('git', ['clone', '--no-checkout', repo, vendorPath]);
}

try {
  run('git', ['-C', vendorPath, 'rev-parse', '--git-dir'], { capture: true });
} catch {
  fail(`Vendor path exists but is not a git repository: ${vendorPath}`);
}

run('git', ['-C', vendorPath, 'fetch', '--depth', '1', 'origin', commit]);
run('git', ['-C', vendorPath, 'checkout', '--detach', commit]);

const actualCommit = run('git', ['-C', vendorPath, 'rev-parse', 'HEAD'], { capture: true }).trim();
if (actualCommit !== commit) {
  fail(`Fetched commit mismatch: expected ${commit}, got ${actualCommit}`);
}

console.log(JSON.stringify({
  ok: true,
  repo,
  commit,
  vendor_path: lock.vendor_path,
  status: 'vendored_matching_lock',
}, null, 2));
