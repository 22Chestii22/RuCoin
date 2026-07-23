/* ═══════════════════════════════════════
   RuCoin Wallet — Browser-based
   Token-bound · WebUSB · localStorage
   ═══════════════════════════════════════ */

/* ──── Crypto helpers ──── */

function toHex(buf) {
  return Array.from(buf).map(b => b.toString(16).padStart(2, '0')).join('');
}

async function sha256(data) {
  return new Uint8Array(await crypto.subtle.digest('SHA-256', data));
}

/* ──── WebUSB: connect to JaCarta token ──── */

const JACARTA_VENDOR = 0x24dc;

async function connectToken() {
  if (!navigator.usb) {
    throw new Error('WebUSB не поддерживается в этом браузере. Используй Chrome/Edge с HTTPS.');
  }
  const device = await navigator.usb.requestDevice({
    filters: [{ vendorId: JACARTA_VENDOR }]
  });
  await device.open();
  const serial = device.serialNumber || 'unknown';
  await device.close();
  const addrHash = await sha256(new TextEncoder().encode(serial));
  const address = 'RUC' + toHex(addrHash).slice(0, 40).toUpperCase();
  return { serial, address };
}

/* ──── Storage ──── */

const STORAGE_KEY = 'rucoin_token';

function saveToken(data) {
  const info = { ...data, connectedAt: Date.now() };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(info));
  return info;
}

function loadToken() {
  const raw = localStorage.getItem(STORAGE_KEY);
  return raw ? JSON.parse(raw) : null;
}

function clearToken() {
  localStorage.removeItem(STORAGE_KEY);
  localStorage.removeItem('rucoin_txs');
}

function getTxs() {
  const raw = localStorage.getItem('rucoin_txs');
  return raw ? JSON.parse(raw) : [];
}

function addTx(tx) {
  const txs = getTxs();
  txs.unshift({ ...tx, time: Date.now() });
  localStorage.setItem('rucoin_txs', JSON.stringify(txs));
  return txs;
}

function getBalance() {
  const txs = getTxs();
  let balance = 0;
  for (const tx of txs) {
    if (tx.type === 'receive' || tx.type === 'mining') balance += tx.amount;
    if (tx.type === 'send') balance -= tx.amount;
  }
  return Math.max(0, balance);
}

/* ──── Send transaction ──── */

function sendRuc(to, amount) {
  amount = parseFloat(amount);
  if (isNaN(amount) || amount <= 0) return { error: 'Invalid amount' };
  const balance = getBalance();
  if (amount > balance) return { error: `Insufficient balance. Need ${amount.toFixed(4)} RUC, have ${balance.toFixed(4)}` };
  if (!to || to.length < 10) return { error: 'Invalid recipient address' };
  const token = loadToken();
  const tx = { type: 'send', from: token.address, to, amount, fee: 0, time: Date.now() };
  const txs = addTx(tx);
  localStorage.setItem('rucoin_txs', JSON.stringify(txs));
  return { success: true, tx };
}

/* ──── Mining reward ──── */

function addMiningReward(amount = 0.1) {
  const token = loadToken();
  if (!token) return;
  const tx = { type: 'mining', from: 'SYSTEM', to: token.address, amount, fee: 0 };
  const txs = addTx(tx);
  localStorage.setItem('rucoin_txs', JSON.stringify(txs));
}

/* ──── Export ──── */

window.RuCoin = {
  connectToken,
  loadToken,
  saveToken,
  clearToken,
  getTxs,
  getBalance,
  sendRuc,
  addMiningReward,
};
