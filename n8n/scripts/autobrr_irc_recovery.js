#!/usr/bin/env node

const fs = require('node:fs');
const crypto = require('node:crypto');
const net = require('node:net');
const path = require('node:path');
const tls = require('node:tls');

function option(name, fallback) {
  const index = process.argv.indexOf(`--${name}`);
  return index === -1 ? fallback : process.argv[index + 1];
}

const config = {
  networkName: option('network', ''),
  apiBase: option('api-base', process.env.AUTOBRR_API_BASE || 'http://autobrr:7474/api'),
  secretsFile: option('secrets-file', process.env.AUTOBRR_IRC_SECRETS_FILE || '/mnt/e/Docker/n8n/irc-recovery-secrets.json'),
  autobrrSecretsFile: option('autobrr-secrets-file', process.env.AUTOBRR_SECRETS_FILE || '/mnt/e/Docker/autobrr/.env.secret'),
  policyFile: option('policy-file', process.env.AUTOBRR_IRC_POLICY_FILE || '/mnt/e/Docker/n8n/irc-recovery-policies.json'),
  lockDir: option('lock-dir', process.env.AUTOBRR_IRC_LOCK_DIR || '/mnt/e/Docker/autobrr/config'),
  cooldownMinutes: Number(option('cooldown-minutes', process.env.AUTOBRR_IRC_COOLDOWN_MINUTES || 30)),
  dryRun: process.argv.includes('--dry-run'),
  force: process.argv.includes('--force'),
};

function quiesceDelay(policy) {
  const seconds = Number(policy.quiesceSeconds ?? 10);
  if (!Number.isInteger(seconds) || seconds < 0 || seconds > 120) throw new Error('Invalid provider quiesceSeconds policy');
  return config.dryRun ? 0 : seconds * 1000;
}

function readSecrets(file) {
  const values = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (!values || Array.isArray(values) || typeof values !== 'object') throw new Error('Recovery secrets file must contain a JSON object');
  return values;
}

function requireSecret(secrets, key) {
  if (!key || !secrets[key]) throw new Error(`Required secret ${key || '(undefined)'} is missing`);
  return secrets[key];
}

function readDotenvSecret(file, key) {
  const line = fs.readFileSync(file, 'utf8').split(/\r?\n/).find((value) => value.startsWith(`${key}=`));
  if (!line) throw new Error(`Required secret ${key} is missing from ${file}`);
  let value = line.slice(key.length + 1).trim();
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) value = value.slice(1, -1);
  return assertIrcCredential(value, key);
}

function looksRedacted(value) {
  return typeof value === 'string' && (/^\*+$/.test(value) || /^<?redacted>?$/i.test(value));
}

function assertIrcCredential(value, description) {
  if (typeof value !== 'string' || !value || /[\r\n\0]/.test(value)) throw new Error(`${description} is missing or contains an invalid IRC control character`);
  return value;
}

function hydrateNetworkCredentials(network, policy, secrets) {
  let serverPassword = network.pass || '';
  if (policy.serverPasswordSecret) serverPassword = assertIrcCredential(requireSecret(secrets, policy.serverPasswordSecret), 'IRC server password');
  else if (looksRedacted(serverPassword)) throw new Error('IRC server password is redacted but has no encrypted policy mapping');

  const channels = (network.channels || []).map((channel) => {
    let password = channel.password || '';
    const secretKey = policy.channelPasswordSecrets?.[channel.name];
    if (secretKey) password = assertIrcCredential(requireSecret(secrets, secretKey), `IRC channel password for ${channel.name}`);
    else if (looksRedacted(password)) throw new Error(`IRC channel password for ${channel.name} is redacted but has no encrypted policy mapping`);
    return { ...channel, password };
  });
  let inviteCommand = network.invite_command || '';
  if (policy.inviteCommand && policy.inviteTokenDotenvKey) {
    const account = requireSecret(secrets, policy.accountSecret);
    const nick = policy.expectedNickSecret ? requireSecret(secrets, policy.expectedNickSecret) : policy.expectedNick;
    const token = readDotenvSecret(config.autobrrSecretsFile, policy.inviteTokenDotenvKey);
    inviteCommand = policy.inviteCommand.replaceAll('{account}', account).replaceAll('{nick}', nick).replaceAll('{token}', token);
  }
  return { ...network, pass: serverPassword, channels, invite_command: inviteCommand };
}

function sendJoin(session, network, channelName) {
  const channel = network.channels.find((item) => item.name === channelName);
  if (!channel) throw new Error(`IRC channel ${channelName} is missing from network configuration`);
  session.send(`JOIN ${channelName}${channel.password ? ` ${channel.password}` : ''}`);
}

async function executeInviteCommands(session, network) {
  if (!network.invite_command) return;
  const commands = network.invite_command.replaceAll('/msg', '').split(',').map((value) => value.trim()).filter(Boolean);
  for (const command of commands) {
    if (command.startsWith('/sleep ')) {
      const seconds = Number(command.slice(7).trim());
      if (!Number.isInteger(seconds) || seconds < 0 || seconds > 30) throw new Error('Invalid invite-command sleep duration');
      await new Promise((resolve) => setTimeout(resolve, seconds * 1000));
      continue;
    }
    const separator = command.indexOf(' ');
    if (separator < 1) throw new Error('Invalid provider invite command');
    session.send(`PRIVMSG ${command.slice(0, separator)} :${command.slice(separator + 1)}`);
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}

async function apiRequest(url, apiKey, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { 'X-API-Token': apiKey, ...(options.headers || {}) },
    signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok) throw new Error(`${options.method || 'GET'} ${url} returned HTTP ${response.status}`);
  if (response.status === 204) return null;
  const text = await response.text();
  return text ? JSON.parse(text) : null;
}

function acquireLock(networkName) {
  fs.mkdirSync(config.lockDir, { recursive: true });
  const safeName = networkName.toLowerCase().replace(/[^a-z0-9]+/g, '-');
  const lock = path.join(config.lockDir, `.irc-recovery-${safeName}.lock`);
  const create = () => {
    const fd = fs.openSync(lock, 'wx', 0o600);
    fs.writeFileSync(fd, `${JSON.stringify({ pid: process.pid, createdAt: new Date().toISOString() })}\n`);
    return () => { try { fs.closeSync(fd); } catch {} try { fs.unlinkSync(lock); } catch {} };
  };
  try {
    return create();
  } catch (error) {
    if (error.code === 'EEXIST') {
      let active = true;
      try {
        const value = JSON.parse(fs.readFileSync(lock, 'utf8'));
        const age = Date.now() - Date.parse(value.createdAt);
        try { process.kill(value.pid, 0); } catch { active = false; }
        if (!Number.isFinite(age) || age > 10 * 60_000) active = false;
      } catch { active = false; }
      if (active) throw new Error(`Recovery already running for ${networkName}`);
      fs.unlinkSync(lock);
      return create();
    }
    throw error;
  }
}

function statePath(networkName) {
  const safeName = networkName.toLowerCase().replace(/[^a-z0-9]+/g, '-');
  return path.join(config.lockDir, `.irc-recovery-${safeName}.json`);
}

function readState(networkName) {
  try { return JSON.parse(fs.readFileSync(statePath(networkName), 'utf8')); } catch (error) {
    if (error.code === 'ENOENT') return {};
    throw error;
  }
}

function writeState(networkName, state) {
  if (config.dryRun) return;
  const target = statePath(networkName);
  const temporary = `${target}.${process.pid}.tmp`;
  fs.writeFileSync(temporary, `${JSON.stringify(state, null, 2)}\n`, { mode: 0o600 });
  fs.renameSync(temporary, target);
}

class IrcSession {
  constructor(network, nick) {
    this.network = network;
    this.nick = nick;
    this.lines = [];
    this.waiters = [];
    this.buffer = '';
  }

  async open() {
    const options = { host: this.network.server, port: this.network.port, rejectUnauthorized: !this.network.tls_skip_verify, servername: this.network.server };
    this.socket = this.network.tls ? tls.connect(options) : net.connect(options);
    this.socket.setEncoding('utf8');
    this.socket.on('data', (chunk) => this.onData(chunk));
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('IRC connection timed out')), 15_000);
      this.socket.once('secureConnect', () => {
        try {
          if (this.network.tlsFingerprint256) {
            const expected = String(this.network.tlsFingerprint256).replaceAll(':', '').toLowerCase();
            if (!/^[a-f0-9]{64}$/.test(expected)) throw new Error('Invalid pinned TLS certificate fingerprint');
            const certificate = this.socket.getPeerCertificate(true);
            if (!certificate.raw) throw new Error('IRC server did not provide a TLS certificate');
            const actual = crypto.createHash('sha256').update(certificate.raw).digest('hex');
            if (!crypto.timingSafeEqual(Buffer.from(actual, 'hex'), Buffer.from(expected, 'hex'))) {
              throw new Error('IRC TLS certificate fingerprint does not match encrypted policy');
            }
          }
          clearTimeout(timer);
          resolve();
        } catch (error) {
          clearTimeout(timer);
          this.socket.destroy();
          reject(error);
        }
      });
      this.socket.once('connect', () => { if (!this.network.tls) { clearTimeout(timer); resolve(); } });
      this.socket.once('error', (error) => { clearTimeout(timer); reject(error); });
    });
    if (this.network.pass) this.send(`PASS ${this.network.pass}`);
  }

  async connect() {
    await this.open();
    this.send(`NICK ${this.nick}`);
    this.send(`USER ${this.nick} 0 * :autobrr deterministic recovery`);
    await this.waitFor((line) => / (001|376|422) /.test(line), 20_000, 'IRC welcome');
  }

  onData(chunk) {
    this.buffer += chunk;
    const parts = this.buffer.split(/\r?\n/);
    this.buffer = parts.pop();
    for (const line of parts) {
      if (line.startsWith('PING ')) this.send(`PONG ${line.slice(5)}`);
      this.lines.push(line);
      for (const waiter of [...this.waiters]) {
        if (waiter.predicate(line)) { waiter.resolve(line); this.waiters.splice(this.waiters.indexOf(waiter), 1); }
      }
    }
  }

  send(line) { this.socket.write(`${line}\r\n`); }

  waitFor(predicate, timeout, description) {
    const existing = this.lines.find(predicate);
    if (existing) return Promise.resolve(existing);
    return new Promise((resolve, reject) => {
      const waiter = { predicate, resolve: (line) => { clearTimeout(timer); resolve(line); } };
      const timer = setTimeout(() => {
        const index = this.waiters.indexOf(waiter);
        if (index >= 0) this.waiters.splice(index, 1);
        reject(new Error(`Timed out waiting for ${description}`));
      }, timeout);
      this.waiters.push(waiter);
    });
  }

  async noticesAfter(command, settleMs = 2500) {
    const start = this.lines.length;
    this.send(command);
    await new Promise((resolve) => setTimeout(resolve, settleMs));
    return this.lines.slice(start).filter((line) => / NOTICE /.test(line));
  }

  close() { if (this.socket && !this.socket.destroyed) { this.send('QUIT :recovery complete'); this.socket.end(); } }
}

async function verifySasl(network, account, password, nick, channel) {
  const session = new IrcSession(network, nick);
  try {
    await session.open();
    session.send('CAP LS 302');
    session.send(`NICK ${nick}`);
    session.send(`USER ${nick} 0 * :autobrr deterministic SASL recovery`);
    await session.waitFor((line) => / CAP \S+ LS (?!\*)/.test(line), 15_000, 'complete IRC capability list');
    const capabilities = session.lines.filter((line) => / CAP \S+ LS /.test(line)).join(' ');
    if (!/(^|\s|:)sasl([=\s]|$)/i.test(capabilities)) throw new Error('IRC server did not advertise SASL');
    session.send('CAP REQ :sasl');
    await session.waitFor((line) => / CAP \S+ ACK :?sasl/i.test(line), 10_000, 'SASL capability acknowledgement');
    session.send('AUTHENTICATE PLAIN');
    await session.waitFor((line) => line === 'AUTHENTICATE +' || line.endsWith(' AUTHENTICATE +'), 10_000, 'SASL PLAIN challenge');
    const payload = Buffer.from(`\0${account}\0${password}`).toString('base64');
    for (let offset = 0; offset < payload.length; offset += 400) session.send(`AUTHENTICATE ${payload.slice(offset, offset + 400)}`);
    if (payload.length % 400 === 0) session.send('AUTHENTICATE +');
    const result = await session.waitFor((line) => / (900|903|904|905|906|907) /.test(line), 15_000, 'SASL result');
    // 907 means the server considers this connection already authenticated.
    if (!/ (900|903|907) /.test(result)) {
      const numeric = result.match(/ (904|905|906) /)?.[1] || 'unknown';
      throw new Error(`IRC server rejected SASL credentials (numeric ${numeric})`);
    }
    session.send('CAP END');
    await session.waitFor((line) => / (001|376|422) /.test(line), 20_000, 'IRC welcome after SASL');
    await executeInviteCommands(session, network);
    sendJoin(session, network, channel);
    await session.waitFor((line) => (line.includes(` ${nick} `) && (line.includes(` JOIN :${channel}`) || line.includes(` JOIN ${channel}`))) || (/ (353|366) /.test(line) && line.includes(channel)), 15_000, `join confirmation for ${channel}`);
  } finally { session.close(); }
}

function infoState(lines) {
  const text = lines.join('\n').toLowerCase();
  if (/is not registered|isn't registered|not registered/.test(text)) return 'unregistered';
  if (/registered|account|last seen|time registered/.test(text)) return 'registered';
  return 'unknown';
}

async function verifyAndRepairNickServ(network, policy, account, password, botNick, email, channel, actions) {
  const randomNick = `abrrchk${crypto.randomBytes(4).toString('hex')}`;
  let currentNick = randomNick;
  const session = new IrcSession(network, randomNick);
  try {
    await session.connect();
    const accountInfo = await session.noticesAfter(`PRIVMSG NickServ :INFO ${account}`);
    const botInfo = account.toLowerCase() === botNick.toLowerCase() ? accountInfo : await session.noticesAfter(`PRIVMSG NickServ :INFO ${botNick}`);
    const status = { account: infoState(accountInfo), bot: infoState(botInfo) };
    actions.push(`nickserv-account-${status.account}`, `nickserv-bot-${status.bot}`);
    if (status.account === 'unknown') throw new Error('NickServ account state was ambiguous; no mutation performed');
    if (status.account === 'unregistered') {
      if (!policy.allowRegister) throw new Error('NickServ account is unregistered and registration is disabled by policy');
      session.send(`NICK ${account}`);
      await session.waitFor((line) => / NICK /.test(line) && line.toLowerCase().includes(account.toLowerCase()), 10_000, 'primary account nick change');
      currentNick = account;
      const registration = await session.noticesAfter(`PRIVMSG NickServ :REGISTER ${password} ${email}`, 4000);
      const registrationText = registration.join('\n').toLowerCase();
      if (/already registered/.test(registrationText)) {
        actions.push('account-already-registered-after-stale-info');
      } else if (!/registered|confirmation|verification|email/.test(registrationText) || /cannot|failed|error/.test(registrationText)) {
        throw new Error('NickServ did not confirm account registration');
      } else {
        actions.push('registered-account');
      }
    }

    let lines = await session.noticesAfter(`PRIVMSG NickServ :IDENTIFY ${account} ${password}`, 3000);
    let text = lines.join('\n').toLowerCase();
    if (!/identified|recognized|logged in|password accepted/.test(text) || /invalid|incorrect|failed|denied/.test(text)) {
      throw new Error('NickServ identification was not confirmed');
    }
    if (currentNick.toLowerCase() !== botNick.toLowerCase()) {
      session.send(`NICK ${botNick}`);
      await session.waitFor((line) => / NICK /.test(line) && line.toLowerCase().includes(botNick.toLowerCase()), 10_000, 'bot nick change');
    }
    const shouldGroup = status.bot === 'unregistered';
    if (shouldGroup && !policy.allowGroup) throw new Error('Bot nick is unregistered and grouping is disabled by policy');
    if (shouldGroup && account.toLowerCase() !== botNick.toLowerCase()) {
      lines = await session.noticesAfter(`PRIVMSG NickServ :GROUP ${account} ${password}`, 3000);
      text = lines.join('\n').toLowerCase();
      if (!/group|registered/.test(text) || /cannot|failed|denied/.test(text)) throw new Error('NickServ did not confirm nick grouping');
    }
    lines = await session.noticesAfter(`PRIVMSG NickServ :STATUS ${botNick}`, 2500);
    text = lines.join('\n');
    const escapedNick = botNick.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    if (!new RegExp(`STATUS\\s+${escapedNick}\\s+3(?:\\s|$)`, 'i').test(text)) {
      throw new Error('NickServ did not confirm ownership of the configured bot nick');
    }
    await executeInviteCommands(session, network);
    sendJoin(session, network, channel);
    await session.waitFor((line) => line.includes(` ${botNick} `) && (line.includes(` JOIN :${channel}`) || line.includes(` JOIN ${channel}`)) || / (353|366) /.test(line) && line.includes(channel), 15_000, `join confirmation for ${channel}`);
    actions.push(shouldGroup ? 'grouped-and-validated-bot-nick' : 'validated-bot-nick');
  } finally { session.close(); }
}

async function setEnabled(network, enabled, apiKey) {
  const { tlsFingerprint256: _tlsFingerprint256, ...apiNetwork } = network;
  const payload = { ...apiNetwork, enabled };
  await apiRequest(`${config.apiBase}/irc/network/${network.id}`, apiKey, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
}

async function synchronizeNickServConfig(network, policy, account, password, botNick, apiKey, actions) {
  const auth = network.auth || {};
  const payload = {
    ...network,
    nick: botNick,
    auth: { ...auth, mechanism: policy.autobrrMechanism || 'NICKSERV', account, password },
  };
  actions.push(config.dryRun ? 'would-synchronize-autobrr-nickserv-config' : 'synchronized-autobrr-nickserv-config');
  return payload;
}

async function repairSasl(network, policy, secrets, apiKey, actions) {
  const accountKey = policy.accountSecret || policy.requiredSecrets?.[0];
  const passwordKey = policy.passwordSecret || policy.requiredSecrets?.[1];
  const account = requireSecret(secrets, accountKey);
  const password = requireSecret(secrets, passwordKey);
  const nick = policy.expectedNickSecret ? requireSecret(secrets, policy.expectedNickSecret) : policy.expectedNick;
  const channel = network.channels.find((item) => item.enabled)?.name;
  if (!channel) throw new Error(`${network.name} has no enabled IRC channel`);

  const auth = network.auth || {};
  network = { ...network, nick, auth: { ...auth, mechanism: 'SASL_PLAIN', account, password } };
  actions.push(config.dryRun ? 'would-synchronize-autobrr-sasl-config' : 'synchronized-autobrr-sasl-config');

  const wasEnabled = network.enabled;
  if (!config.dryRun) await setEnabled(network, false, apiKey);
  if (wasEnabled) actions.push(config.dryRun ? 'would-disable-autobrr-network' : 'disabled-autobrr-network');
  try {
    await new Promise((resolve) => setTimeout(resolve, quiesceDelay(policy)));
    if (!config.dryRun) await verifySasl(network, account, password, nick, channel);
    actions.push(config.dryRun ? 'would-verify-sasl-and-channel' : 'verified-sasl-and-channel');
  } finally {
    if (wasEnabled && !config.dryRun) { await setEnabled(network, true, apiKey); actions.push('enabled-autobrr-network'); }
  }
}

async function repairNoAuth(network, policy, secrets, apiKey, actions) {
  const nick = policy.expectedNickSecret ? requireSecret(secrets, policy.expectedNickSecret) : policy.expectedNick;
  const channel = network.channels.find((item) => item.enabled)?.name;
  if (!channel) throw new Error(`${network.name} has no enabled IRC channel`);
  network = { ...network, nick, auth: { ...(network.auth || {}), mechanism: 'NONE', account: '', password: '' } };
  actions.push(config.dryRun ? 'would-synchronize-autobrr-no-auth-config' : 'synchronized-autobrr-no-auth-config');

  const wasEnabled = network.enabled;
  if (!config.dryRun) await setEnabled(network, false, apiKey);
  if (wasEnabled) actions.push(config.dryRun ? 'would-disable-autobrr-network' : 'disabled-autobrr-network');
  try {
    await new Promise((resolve) => setTimeout(resolve, quiesceDelay(policy)));
    if (!config.dryRun) {
      const session = new IrcSession(network, nick);
      try {
        await session.connect();
        sendJoin(session, network, channel);
        await session.waitFor((line) => (line.includes(` ${nick} `) && (line.includes(` JOIN :${channel}`) || line.includes(` JOIN ${channel}`))) || (/ (353|366) /.test(line) && line.includes(channel)), 15_000, `join confirmation for ${channel}`);
      } finally { session.close(); }
    }
    actions.push(config.dryRun ? 'would-verify-no-auth-channel' : 'verified-no-auth-channel');
  } finally {
    if (wasEnabled && !config.dryRun) { await setEnabled(network, true, apiKey); actions.push('enabled-autobrr-network'); }
  }
}

async function repairNickServ(network, policy, secrets, apiKey, actions) {
  const account = requireSecret(secrets, policy.accountSecret);
  const password = requireSecret(secrets, policy.passwordSecret);
  const botNick = policy.expectedNickSecret ? requireSecret(secrets, policy.expectedNickSecret) : policy.expectedNick;
  const email = policy.allowRegister ? requireSecret(secrets, policy.emailSecret) : '';
  const channel = network.channels.find((item) => item.enabled)?.name;
  if (!channel) throw new Error(`${network.name} has no enabled IRC channel`);
  network = await synchronizeNickServConfig(network, policy, account, password, botNick, apiKey, actions);

  const wasEnabled = network.enabled;
  if (!config.dryRun) await setEnabled(network, false, apiKey);
  if (wasEnabled) actions.push(config.dryRun ? 'would-disable-autobrr-network' : 'disabled-autobrr-network');
  try {
    await new Promise((resolve) => setTimeout(resolve, quiesceDelay(policy)));
    if (!config.dryRun) await verifyAndRepairNickServ(network, policy, account, password, botNick, email, channel, actions);
    else actions.push('would-inspect-repair-and-validate-nickserv');
  } finally {
    if (wasEnabled && !config.dryRun) { await setEnabled(network, true, apiKey); actions.push('enabled-autobrr-network'); }
  }
}

async function main() {
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(config.networkName)) throw new Error('A valid --network name is required');
  const policies = JSON.parse(fs.readFileSync(config.policyFile, 'utf8'));
  const policy = policies[config.networkName];
  if (!policy) throw new Error(`No recovery policy exists for ${config.networkName}`);
  const secrets = readSecrets(config.secretsFile);
  const apiKey = requireSecret(secrets, 'AUTOBRR_RECOVERY_API_KEY');
  const networks = await apiRequest(`${config.apiBase}/irc`, apiKey);
  let network = networks.find((item) => item.name === config.networkName);
  if (!network) throw new Error(`autobrr network ${config.networkName} was not found`);
  const recoveryUsesCredentials = policy.mode !== 'no-auth' || Boolean(policy.serverPasswordSecret) || Object.keys(policy.channelPasswordSecrets || {}).length > 0;
  if (network.tls && network.tls_skip_verify && recoveryUsesCredentials && !policy.tlsFingerprint256) {
    throw new Error('Credentialed recovery with skipped TLS verification requires a pinned certificate fingerprint');
  }
  network = { ...network, tlsFingerprint256: policy.tlsFingerprint256 };
  network = hydrateNetworkCredentials(network, policy, secrets);
  if (!network.enabled && !config.force) throw new Error(`${config.networkName} is administratively disabled`);
  const expectedNick = policy.expectedNickSecret ? requireSecret(secrets, policy.expectedNickSecret) : policy.expectedNick;
  if (network.nick !== expectedNick && !policy.automaticAccountRepair) {
    throw new Error(`${config.networkName} uses unexpected nick; configured=${network.nick}, policy=${expectedNick}`);
  }

  const release = acquireLock(config.networkName);
  const actions = [];
  try {
    const state = readState(config.networkName);
    const now = Date.now();
    const lastAttempt = state.lastAttemptAt ? Date.parse(state.lastAttemptAt) : 0;
    if (!config.force && lastAttempt && now - lastAttempt < config.cooldownMinutes * 60_000) {
      process.stdout.write(`${JSON.stringify({ ok: true, network: config.networkName, action: 'cooldown', actions: [], lastAttemptAt: state.lastAttemptAt })}\n`);
      return;
    }
    if (network.connected === true && network.healthy === true && !config.force) {
      process.stdout.write(`${JSON.stringify({ ok: true, network: config.networkName, action: 'already-healthy', actions: [] })}\n`);
      return;
    }
    writeState(config.networkName, { ...state, lastAttemptAt: new Date(now).toISOString() });

    try {
      if ((policy.mode === 'nickserv-grouped' || policy.mode === 'nickserv') && policy.automaticAccountRepair) {
        await repairNickServ(network, policy, secrets, apiKey, actions);
      } else if (policy.mode === 'sasl' && policy.automaticAccountRepair) {
        await repairSasl(network, policy, secrets, apiKey, actions);
      } else if (policy.mode === 'no-auth' && policy.automaticAccountRepair) {
        await repairNoAuth(network, policy, secrets, apiKey, actions);
      } else {
        if (!config.dryRun) await apiRequest(`${config.apiBase}/irc/network/${network.id}/restart`, apiKey);
        actions.push(config.dryRun ? 'would-restart-network' : 'restarted-network');
      }
    } catch (error) {
      writeState(config.networkName, { lastAttemptAt: new Date(now).toISOString(), lastFailureAt: new Date().toISOString(), error: error.message, actions });
      throw error;
    }
    writeState(config.networkName, { lastAttemptAt: new Date(now).toISOString(), lastSuccessAt: new Date().toISOString(), actions });
    process.stdout.write(`${JSON.stringify({ ok: true, network: config.networkName, action: config.dryRun ? 'dry-run' : 'recovered', mode: policy.mode, actions })}\n`);
  } finally { release(); }
}

main().catch((error) => {
  process.stdout.write(`${JSON.stringify({ ok: false, network: config.networkName || null, error: error.message })}\n`);
  process.exitCode = 1;
});
