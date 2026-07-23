/* ═══════════════════════════════════════
   RuCoin Wallet — Browser-based
   Secret Key Only · localStorage
   ═══════════════════════════════════════ */

/* ──── Crypto helpers ──── */

function toHex(buf) {
  return Array.from(buf).map(b => b.toString(16).padStart(2, '0')).join('');
}

async function sha256(data) {
  return new Uint8Array(await crypto.subtle.digest('SHA-256', data));
}

/* ──── Derivation: Secret Key -> Address ──── */

async function secretToAddress(secretKey) {
  const addrHash = await sha256(new TextEncoder().encode(secretKey.trim()));
  return 'RUC' + toHex(addrHash).slice(0, 40).toUpperCase();
}

function isValidSecretKey(key) {
  return /^[a-fA-F0-9]{64}$/.test(key.trim());
}

/* ──── Storage ──── */

const STORAGE_KEY = 'rucoin_wallet';

function saveWallet(data) {
  const info = { ...data, connectedAt: Date.now() };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(info));
  return info;
}

function loadWallet() {
  const raw = localStorage.getItem(STORAGE_KEY);
  return raw ? JSON.parse(raw) : null;
}

function clearWallet() {
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
  if (isNaN(amount) || amount <= 0) return { error: 'Неверная сумма' };
  const balance = getBalance();
  if (amount > balance) return { error: `Недостаточно средств. На балансе ${balance.toFixed(4)} RUC` };
  if (!to || !/^RUC[A-F0-9]{40}$/i.test(to.trim())) return { error: 'Неверный адрес получателя' };
  const wallet = loadWallet();
  if (!wallet) return { error: 'Кошелёк не загружен' };
  const tx = { type: 'send', from: wallet.address, to: to.trim().toUpperCase(), amount, fee: 0, time: Date.now() };
  addTx(tx);
  return { success: true, tx };
}

/* ──── Mining reward ──── */

function addMiningReward(amount = 0.1) {
  const wallet = loadWallet();
  if (!wallet) return;
  const tx = { type: 'mining', from: 'SYSTEM', to: wallet.address, amount, fee: 0 };
  addTx(tx);
}

/* ──── Export ──── */

window.RuCoin = {
  secretToAddress,
  isValidSecretKey,
  saveWallet,
  loadWallet,
  clearWallet,
  getTxs,
  getBalance,
  sendRuc,
  addMiningReward,
};