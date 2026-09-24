#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const packageRoot = path.resolve(__dirname, '..');
const verificationRoot = path.join(packageRoot, 'ton-assets-verification');
const policyRoot = path.resolve(packageRoot, '../../../backend/static/glm_policy');

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function cleanScalar(value) {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }
  if (/^-?\d+$/.test(trimmed)) return Number(trimmed);
  return trimmed;
}

function parseSimpleYaml(filePath) {
  const result = {};
  let currentListKey = null;
  const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/);

  for (const line of lines) {
    if (!line.trim() || line.trimStart().startsWith('#')) continue;

    const listMatch = line.match(/^\s+-\s+(.+)$/);
    if (listMatch && currentListKey) {
      result[currentListKey].push(cleanScalar(listMatch[1]));
      continue;
    }

    const scalarMatch = line.match(/^([A-Za-z0-9_-]+):(?:\s*(.*))?$/);
    if (!scalarMatch) continue;

    const key = scalarMatch[1];
    const value = scalarMatch[2] || '';
    if (!value.trim()) {
      result[key] = [];
      currentListKey = key;
      continue;
    }

    result[key] = cleanScalar(value);
    currentListKey = null;
  }

  return result;
}

function pngDimensions(filePath) {
  const buffer = fs.readFileSync(filePath);
  const signature = buffer.subarray(0, 8).toString('hex');
  if (signature !== '89504e470d0a1a0a') {
    throw new Error(`${filePath} is not a PNG file`);
  }
  return {
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
  };
}

function assertEqual(errors, label, actual, expected) {
  if (actual !== expected) {
    errors.push(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

function assertIncludes(errors, label, values, expected) {
  if (!Array.isArray(values) || !values.includes(expected)) {
    errors.push(`${label}: missing ${expected}`);
  }
}

async function checkUrl(errors, warnings, label, url, expectedContentPrefix = null) {
  try {
    const response = await fetch(url, { method: 'HEAD' });
    if (!response.ok) {
      errors.push(`${label}: ${url} returned HTTP ${response.status}`);
      return;
    }
    const contentType = response.headers.get('content-type') || '';
    if (expectedContentPrefix && !contentType.toLowerCase().startsWith(expectedContentPrefix)) {
      errors.push(`${label}: ${url} content-type ${contentType || '<empty>'}, expected ${expectedContentPrefix}`);
    }
  } catch (error) {
    warnings.push(`${label}: ${url} live check failed: ${error.message}`);
  }
}

async function main() {
  const live = process.argv.includes('--live');
  const errors = [];
  const warnings = [];

  const yamlPath = path.join(verificationRoot, 'GLM.yaml');
  const entryPath = path.join(verificationRoot, 'glm-jetton-entry.json');
  const mainnetPath = path.join(packageRoot, 'glm-jetton.mainnet.json');
  const metadataPath = path.join(policyRoot, 'jetton-metadata-mainnet-v2.json');
  const iconPath = path.join(policyRoot, 'glm-token-icon-v3.png');

  const yaml = parseSimpleYaml(yamlPath);
  const entry = readJson(entryPath);
  const mainnet = readJson(mainnetPath);
  const metadata = readJson(metadataPath);
  const dimensions = pngDimensions(iconPath);

  const landingUrl = 'https://partner.glamejewelry.ru/glm';
  const partnerUrl = 'https://partner.glamejewelry.ru/referral';
  const iconUrl = 'https://partner.glamejewelry.ru/static/glm_policy/glm-token-icon-v3.png';
  const metadataUrl = 'https://partner.glamejewelry.ru/static/glm_policy/jetton-metadata-mainnet-v2.json';

  assertEqual(errors, 'yaml.name', yaml.name, mainnet.token.name);
  assertEqual(errors, 'yaml.symbol', yaml.symbol, mainnet.token.symbol);
  assertEqual(errors, 'yaml.decimals', yaml.decimals, mainnet.token.decimals);
  assertEqual(errors, 'yaml.image', yaml.image, iconUrl);
  assertEqual(errors, 'yaml.address', yaml.address, entry.address);
  assertEqual(errors, 'entry.name', entry.name, mainnet.token.name);
  assertEqual(errors, 'entry.symbol', entry.symbol, mainnet.token.symbol);
  assertEqual(errors, 'entry.decimals', entry.decimals, mainnet.token.decimals);
  assertEqual(errors, 'entry.image', entry.image, iconUrl);
  assertEqual(errors, 'metadata.name', metadata.name, mainnet.token.name);
  assertEqual(errors, 'metadata.symbol', metadata.symbol, mainnet.token.symbol);
  assertEqual(errors, 'metadata.decimals', Number(metadata.decimals), mainnet.token.decimals);
  assertEqual(errors, 'metadata.image', metadata.image, iconUrl);
  assertEqual(errors, 'mainnet.metadata_url', mainnet.token.metadata_url, metadataUrl);

  assertIncludes(errors, 'yaml.websites', yaml.websites, landingUrl);
  assertIncludes(errors, 'yaml.websites', yaml.websites, partnerUrl);
  assertIncludes(errors, 'entry.websites', entry.websites, landingUrl);
  assertIncludes(errors, 'metadata.websites', metadata.websites, landingUrl);

  if (!String(yaml.image || '').endsWith('.png')) {
    errors.push('yaml.image must be a direct PNG URL');
  }
  if (dimensions.width !== 1024 || dimensions.height !== 1024) {
    errors.push(`glm-token-icon-v3.png must be 1024x1024, got ${dimensions.width}x${dimensions.height}`);
  }

  if (live) {
    await checkUrl(errors, warnings, 'icon', iconUrl, 'image/png');
    await checkUrl(errors, warnings, 'metadata', metadataUrl, 'application/json');
    await checkUrl(errors, warnings, 'landing', landingUrl, 'text/html');
    await checkUrl(errors, warnings, 'partner', partnerUrl, 'text/html');
  }

  const payload = {
    ok: errors.length === 0,
    live,
    jetton_master: mainnet.contracts.jetton_master_address,
    raw_address: yaml.address,
    metadata_url: metadataUrl,
    icon_url: iconUrl,
    icon_dimensions: dimensions,
    errors,
    warnings,
  };

  console.log(JSON.stringify(payload, null, 2));
  process.exit(errors.length ? 1 : 0);
}

main();
