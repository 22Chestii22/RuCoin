#!/usr/bin/env python3
"""
RuCoin — Proof-of-Streebog Miner
─────────────────────────────────
Вставил токен → python3 rucoin.py → майнишь на свой кошелёк.

Эмиссия: 256 000 000 RUC
Награда: 2048 RUC/блок, халвинг каждые 62 500 блоков
Стрибог-256 на аппаратном токене JaCarta (без пароля!)
"""

import subprocess, json, time, struct, sys, os, codecs, hashlib
from datetime import datetime, timezone
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

# ═══ Параметры эмиссии ═══

INITIAL_REWARD = 2048        # RUC (2¹¹)
HALVING_INTERVAL = 62500
TOTAL_SUPPLY = 256_000_000
SATOSHI = 0.00000001

DIFFICULTY = 3
WALLET_FILE = "rucoin_wallet.pem"
CHAIN_FILE = "rucoin_chain.json"

PKCS11_PATHS = {
    "linux":  "/usr/lib/libjcPKCS11-2.so",
    "linux2": "/usr/lib/libjcPKCS11-2.so",
    "win32":  "C:/Windows/System32/jcPKCS11-2.dll",
    "cygwin": "jcPKCS11-2.dll",
    "darwin": "/Library/Frameworks/jcPKCS11-2.framework/jcPKCS11-2",
}


def detect_module() -> str:
    plat = sys.platform
    if plat in PKCS11_PATHS:
        path = PKCS11_PATHS[plat]
        if os.path.exists(path):
            return path
    for p in set(PKCS11_PATHS.values()):
        if os.path.exists(p):
            return p
    for p in ["/usr/lib/libjcPKCS11-2.so", "/usr/lib64/libjcPKCS11-2.so",
              "/usr/lib/x86_64-linux-gnu/libjcPKCS11-2.so"]:
        if os.path.exists(p):
            return p
    if plat in ("win32", "cygwin"):
        for p in ["jcPKCS11-2.dll", "C:/Windows/System32/jcPKCS11-2.dll"]:
            if os.path.exists(p):
                return p
    if plat == "darwin":
        for p in ["/Library/Frameworks/jcPKCS11-2.framework/jcPKCS11-2",
                  "/usr/local/lib/libjcPKCS11-2.dylib"]:
            if os.path.exists(p):
                return p
    print(f"❌ PKCS#11 библиотека JaCarta не найдена для {plat}")
    sys.exit(1)


def pkcs11(*args, timeout=30) -> bytes:
    mod = detect_module()
    cmd = ["pkcs11-tool", "--module", mod] + list(args)
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if r.returncode != 0:
        err = r.stderr.decode().strip()
        if err:
            raise RuntimeError(err)
    return r.stdout


def get_token_serial() -> str:
    """Получает серийный номер токена через pkcs11-tool -L."""
    out = pkcs11("-L")
    for line in out.decode().splitlines():
        line_lower = line.lower()
        if "serial" in line_lower and ("number" in line_lower or "num" in line_lower):
            serial = line.split(":")[-1].strip()
            if serial and serial != "00000000":
                return serial
    raise RuntimeError("Серийный номер не найден. Токен вставлен? pcscd запущен?")


def derive_keys(serial: str) -> tuple[str, str]:
    """Секретный ключ и публичный адрес от серийного номера токена."""
    secret_key = hashlib.sha256(f"rucoin_secret_{serial}".encode()).hexdigest()
    address_hash = hashlib.sha256(secret_key.encode()).hexdigest()[:40].upper()
    return secret_key, f"RUC{address_hash}"


def streebog_hash(data: bytes) -> bytes:
    tmp = "/tmp/_rucoin_block.bin"
    with open(tmp, "wb") as f:
        f.write(data)
    pkcs11_result = pkcs11("--slot", "0x1ffff", "--hash",
                           "--mechanism", "GOSTR3411-12-256",
                           "--input-file", tmp, timeout=120)
    raw = pkcs11_result
    if b"\n" in raw:
        raw = raw.rsplit(b"\n", 1)[-1]
    if len(raw) >= 32:
        return raw[:32]
    return raw.ljust(32, b"\x00")[:32]


def get_or_create_wallet() -> tuple[bytes, str]:
    """Возвращает (private_key_pem, address). Адрес берётся из токена."""
    # Читаем токен для адреса
    serial = get_token_serial()
    _, address = derive_keys(serial)

    # RSA ключ только для подписи транзакций (если понадобится)
    if os.path.exists(WALLET_FILE):
        with open(WALLET_FILE, "rb") as f:
            key = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        with open(WALLET_FILE, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()))
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()), address


# ═══ Блокчейн ═══

class Block:
    def __init__(self, index: int, txns: list, prev_hash: str, nonce: int = 0):
        self.index = index
        self.timestamp = int(time.time())
        self.txns = txns
        self.prev_hash = prev_hash
        self.nonce = nonce
        self.hash = ""

    def serialize(self) -> bytes:
        """Блок в байты для хэширования."""
        data = struct.pack(">IQ", self.index, self.timestamp)
        data += self.prev_hash.encode()
        data += json.dumps(self.txns, sort_keys=True).encode()
        data += struct.pack(">Q", self.nonce)
        return data

    def compute_hash(self) -> str:
        """Считает хэш блока через Стрибог на токене."""
        raw = self.serialize()
        h = streebog_hash(raw)
        return h.hex()

    def mine(self, difficulty: int):
        """Перебирает nonce пока хэш не начнётся с difficulty нулей."""
        target = "0" * difficulty
        start = time.time()
        hashes = 0
        while True:
            h = self.compute_hash()
            hashes += 1
            if h.startswith(target):
                self.hash = h
                elapsed = time.time() - start
                rate = hashes / elapsed if elapsed > 0 else 0
                return elapsed, rate
            self.nonce += 1

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": self.txns,
            "prev_hash": self.prev_hash,
            "nonce": self.nonce,
            "hash": self.hash,
        }


CHAIN_FILE = "rucoin_chain.json"


def reward_for_block(index: int) -> float:
    """Считает награду за блок с учётом халвинга.

    Награда уменьшается вдвое каждые HALVING_INTERVAL блоков.
    2048 → 1024 → 512 → ... → 0.5 → 0.25 → ... → 0.00000001

    Останавливается, когда награда становится меньше 1 сатоши.
    """
    epoch = index // HALVING_INTERVAL
    reward = INITIAL_REWARD >> epoch
    min_reward = SATOSHI
    if reward < min_reward:
        # дробная часть — используем float для sub-1 RUC
        reward = INITIAL_REWARD / (2 ** epoch)
        if reward < min_reward:
            return 0.0
    return float(reward)


def halving_epoch(index: int) -> int:
    return index // HALVING_INTERVAL


def total_mined(chain_len: int) -> int:
    """Сколько всего RUC добыто с учётом всех халвингов."""
    total = 0
    for i in range(chain_len):
        total += reward_for_block(i)
    return total


def load_chain() -> list:
    if os.path.exists(CHAIN_FILE):
        with open(CHAIN_FILE) as f:
            return json.load(f)
    return []


def save_chain(chain: list):
    with open(CHAIN_FILE, "w") as f:
        json.dump(chain, f, indent=2)


def show_halving_info(index: int):
    epoch = halving_epoch(index)
    reward = reward_for_block(index)
    next_halving = HALVING_INTERVAL - (index % HALVING_INTERVAL)
    print(f"   ── Эпоха #{epoch} · награда {reward} RUC"
          f" · следующий халвинг через {next_halving} блоков")
    total_mined_supply = total_mined(index)
    pct = (total_mined_supply / TOTAL_SUPPLY) * 100
    print(f"   ── Добыто: {total_mined_supply:.0f} / {TOTAL_SUPPLY} RUC ({pct:.2f}%)")


def main():
    print("═══════════════════════════════════════")
    print("  RuCoin — Proof-of-Streebog Miner")
    print(f"  Platform: {sys.platform}")
    print(f"  Эмиссия: {TOTAL_SUPPLY} RUC")
    print(f"  Старт: {INITIAL_REWARD} RUC/блок, халвинг каждые {HALVING_INTERVAL} блоков")
    print("═══════════════════════════════════════\n")

    try:
        mod = detect_module()
        print(f"✅ PKCS#11: {mod}")
    except SystemExit:
        print("❌ JaCarta библиотека не найдена.\n"
              "   Установи: https://www.aladdin-rd.ru/support/downloads/jacarta/")
        sys.exit(1)

    print("🚀 Проверяю Стрибог...")
    streebog_hash(b"rucoin_test")
    print("✅ Стрибог-256 работает (без пароля!)\n")

    raw_name = input("Имя воркера (Enter = Satoshi): ").strip() or "Satoshi"
    try:
        worker_name = codecs.decode(raw_name, 'unicode_escape')
    except Exception:
        worker_name = raw_name
    print(worker_name)

    print()
    pubkey, address = get_or_create_wallet()
    print(f"💳 Адрес: {address}")
    print(f"🔑 Ключ: {WALLET_FILE}\n")

    chain = load_chain()
    if chain:
        print(f"📦 Цепь: {len(chain)} блоков")
        start_index = chain[-1]["index"] + 1
        prev_hash = chain[-1]["hash"]
    else:
        print("📦 Цепь: новая")
        genesis_reward = reward_for_block(0)
        genesis = Block(0, [{"coinbase": address, "amount": genesis_reward}], "0" * 64)
        print(f"   Майню genesis block (награда: {genesis_reward} RUC)...")
        t, r = genesis.mine(DIFFICULTY)
        genesis.hash = genesis.compute_hash()
        chain.append(genesis.to_dict())
        save_chain(chain)
        print(f"   ✅ Genesis block намайнен ({t:.1f}s, {r:.2f} H/s)")
        start_index = 1
        prev_hash = genesis.hash

    show_halving_info(start_index)
    print(f"\n⛏️  Майнинг... сложность: {DIFFICULTY} нуля")
    block_num = start_index
    total_hashes = 0
    total_time = 0

    try:
        while True:
            txn_reward = reward_for_block(block_num)
            txn = [{"coinbase": address, "amount": txn_reward}]
            b = Block(block_num, txn, prev_hash)
            start_t = time.time()
            elapsed, rate = b.mine(DIFFICULTY)
            total_hashes += 1
            total_time += elapsed

            avg = total_hashes / total_time if total_time > 0 else 0
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")

            print(f"  [{ts}] Блок #{b.index} намайнен! "
                  f"{elapsed:.1f}s (среднее: ~{avg:.2f} H/s)  "
                  f"nonce: {b.nonce}  хэш: {b.hash[:16]}...  "
                  f"+{txn_reward} RUC")

            chain.append(b.to_dict())
            save_chain(chain)
            prev_hash = b.hash
            block_num += 1

            if block_num % HALVING_INTERVAL == 0:
                epoch = halving_epoch(block_num)
                print(f"\n═══ ХАЛВИНГ! Эпоха #{epoch} — награда теперь {reward_for_block(block_num)} RUC ═══\n")

    except KeyboardInterrupt:
        mined = total_mined(len(chain))
        print(f"\n\n⏹  Остановлен. Всего блоков: {len(chain)}")
        print(f"   Добыто: {mined:.2f} RUC / {TOTAL_SUPPLY} RUC ({mined/TOTAL_SUPPLY*100:.4f}%)")
        print(f"   Адрес: {address}")
        print(f"   Цепь сохранена в {CHAIN_FILE}")


if __name__ == "__main__":
    main()
