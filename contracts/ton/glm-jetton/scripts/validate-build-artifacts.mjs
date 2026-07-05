#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const rootDir = process.cwd();
const lockPath = path.resolve(rootDir, 'reference.jetton-contract.lock.json');
const lock = JSON.parse(fs.readFileSync(lockPath, 'utf8'));
const vendorPath = path.resolve(rootDir, lock.vendor_path || '');

function readCompiled(name) {
  const filePath = path.resolve(vendorPath, 'build', `${name}.compiled.json`);
  if (!fs.existsSync(filePath)) {
    return { name, exists: false, path: path.relative(rootDir, filePath), ok: false };
  }
  try {
    const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    const hash = String(data.hash || '');
    const hashBase64 = String(data.hashBase64 || '');
    return {
      name,
      exists: true,
      path: path.relative(rootDir, filePath),
      ok: /^[0-9a-f]{64}$/i.test(hash) && Boolean(hashBase64),
      hash,
      hashBase64,
      libraryHash: data.libraryHash || null,
    };
  } catch (error) {
    return {
      name,
      exists: true,
      path: path.relative(rootDir, filePath),
      ok: false,
      error: error.message,
    };
  }
}

const contracts = [readCompiled('JettonMinter'), readCompiled('JettonWallet')];
const wallet = contracts.find((item) => item.name === 'JettonWallet');
const checks = [
  {
    code: 'minter_compiled',
    ok: Boolean(contracts.find((item) => item.name === 'JettonMinter')?.ok),
    message: 'JettonMinter compiled artifact exists and has hash',
  },
  {
    code: 'wallet_compiled',
    ok: Boolean(wallet?.ok),
    message: 'JettonWallet compiled artifact exists and has hash',
  },
  {
    code: 'wallet_library_hash',
    ok: Boolean(wallet?.libraryHash),
    message: 'JettonWallet compiled artifact includes libraryHash',
  },
];

const blockers = checks.filter((item) => !item.ok);
console.log(JSON.stringify({
  ok: blockers.length === 0,
  status: blockers.length === 0 ? 'compiled' : 'blocked',
  vendor_path: lock.vendor_path,
  contracts,
  checks,
  blockers,
}, null, 2));
process.exit(blockers.length ? 1 : 0);
