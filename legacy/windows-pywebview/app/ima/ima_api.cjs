#!/usr/bin/env node

const fs = require('fs');
const os = require('os');
const path = require('path');

const DEFAULT_BASE_URL = 'https://ima.qq.com';
const DEFAULT_LAST_CHECK_FILE = path.join(os.homedir(), '.config/ima/last_update_check');

// Only two categories of errors:
//   -100: programmatic error (bad args, missing credentials, network, etc.)
//   -200: skill update available
const ERR_PROGRAMMATIC = -100;
const ERR_UPDATE_AVAILABLE = -200;

function readFileSafe(filePath) {
  try {
    return fs.readFileSync(filePath, 'utf8').trim();
  } catch {
    return '';
  }
}

function loadCredentials(options = {}) {
  const clientId =
    options.clientId ||
    process.env.IMA_CLIENT_ID ||
    process.env.IMA_OPENAPI_CLIENTID ||
    readFileSafe(path.join(os.homedir(), '.config/ima/client_id'));
  const apiKey =
    options.apiKey ||
    process.env.IMA_API_KEY ||
    process.env.IMA_OPENAPI_APIKEY ||
    readFileSafe(path.join(os.homedir(), '.config/ima/api_key'));

  if (!clientId || !apiKey) {
    const err = new Error('missing credentials');
    err.code = ERR_PROGRAMMATIC;
    err.msg =
      '未找到 IMA 凭证（clientId / apiKey）。请设置 IMA_CLIENT_ID 和 IMA_API_KEY 环境变量，或将凭证放置在 ~/.config/ima/ 目录下。';
    throw err;
  }

  return { clientId, apiKey };
}

function loadSkillVersion(options = {}) {
  if (options.skillVersion) return options.skillVersion;
  if (process.env.IMA_SKILL_VERSION) return process.env.IMA_SKILL_VERSION;

  const metaPath = path.join(__dirname, 'meta.json');
  try {
    const meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
    return meta.version || 'unknown';
  } catch {
    return 'unknown';
  }
}

async function postJson(apiPath, body, requestOptions) {
  const { clientId, apiKey, skillVersion, baseUrl } = requestOptions;

  const res = await fetch(`${baseUrl}/${apiPath}`, {
    method: 'POST',
    headers: {
      'ima-openapi-clientid': clientId,
      'ima-openapi-apikey': apiKey,
      'ima-openapi-ctx': `skill_version=${skillVersion}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  return await res.text();
}

async function imaApi(apiPath, body, options = {}) {
  const forceCheck = options.forceCheck || options.forceUpdateCheck || process.env.IMA_FORCE_UPDATE_CHECK === '1';
  const baseUrl = options.baseUrl || process.env.IMA_BASE_URL || DEFAULT_BASE_URL;
  const lastCheckFile = options.lastCheckFile || process.env.IMA_LAST_CHECK_FILE || DEFAULT_LAST_CHECK_FILE;
  const { clientId, apiKey } = loadCredentials(options);
  const skillVersion = loadSkillVersion(options);

  const requestOptions = {
    forceCheck,
    clientId,
    apiKey,
    skillVersion,
    baseUrl,
    lastCheckFile,
  };

  // Bundled-with-Aegis build: the online skill update check is disabled.
  return postJson(apiPath, body, requestOptions);
}

function parseBody(raw) {
  if (!raw || !raw.trim()) return {};

  try {
    return JSON.parse(raw);
  } catch {
    const err = new Error('invalid JSON body');
    err.code = ERR_PROGRAMMATIC;
    err.msg = '请求 body 不是合法的 JSON，请检查输入。';
    throw err;
  }
}

function parseOptions(raw, restArgs) {
  let options = {};

  if (raw && raw.trim()) {
    try {
      options = JSON.parse(raw);
    } catch {
      const err = new Error('invalid options JSON');
      err.code = ERR_PROGRAMMATIC;
      err.msg = 'options 参数不是合法的 JSON，请检查输入。';
      throw err;
    }
  }

  if (restArgs.includes('--force-update-check')) {
    options.forceCheck = true;
  }

  return options;
}

async function main() {
  const [, , apiPath, rawBody = '{}', rawOptions = '{}', ...rest] = process.argv;

  if (!apiPath) {
    process.stderr.write(JSON.stringify({ code: ERR_PROGRAMMATIC, msg: '缺少必需参数：apiPath。' }));
    // Unix exit codes are 0-255; use 1 as generic failure. Callers should parse stderr JSON for the real code.
    process.exit(1);
  }

  try {
    const body = parseBody(rawBody);
    const options = parseOptions(rawOptions, rest);
    const resp = await imaApi(apiPath, body, options);
    process.stdout.write(resp);
  } catch (err) {
    const code = err && typeof err.code === 'number' ? err.code : ERR_PROGRAMMATIC;
    const msg = (err && err.msg) || (err && err.message) || '未知错误';
    process.stderr.write(JSON.stringify({ code, msg }));
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}

module.exports = {
  imaApi,
  ERR_PROGRAMMATIC,
  ERR_UPDATE_AVAILABLE,
};
