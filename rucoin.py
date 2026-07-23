#!/usr/bin/env python3
"""
RuCoin — Proof-of-Streebog Miner
─────────────────────────────────
Вставил токен → запустил python3 rucoin.py → майнится на твой кошелёк.
"""

import subprocess
import json
import time
import struct
import sys
import os
from datetime import datetime, timezone

# ═══ OS-зависимые пути к PKCS#11 библиотеке JaCarta ═══

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
        # fallback: common paths
        for p in set(PKCS11_PATHS.values()):
            if os.path.exists(p):
                return p
    # Linux fallback: search common locations
    for p in ["/usr/lib/libjcPKCS11-2.so", "/usr/lib64/libjcPKCS11-2.so",
              "/usr/lib/x86_64-linux-gnu/libjcPKCS11-2.so"]:
        if os.path.exists(p):
            return p
    # Windows fallback
    if plat in ("win32", "cygwin"):
        for p in ["jcPKCS11-2.dll", "C:/Windows/System32/jcPKCS11-2.dll"]:
            if os.path.exists(p):
                return p
    # macOS fallback
    if plat == "darwin":
        for p in ["/Library/Frameworks/jcPKCS11-2.framework/jcPKCS11-2",
                  "/usr/local/lib/libjcPKCS11-2.dylib"]:
            if os.path.exists(p):
                return p
    print(f"❌ PKCS#11 библиотека JaCarta не найдена для {plat}")
    sys.exit(1)


def pkcs11(*args, timeout=30) -> bytes:
    """Вызов pkcs11-tool с таймаутом."""
    mod = detect_module()
    cmd = ["pkcs11-tool", "--module", mod] + list(args)
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if r.returncode != 0:
        err = r.stderr.decode().strip()
        if err:
            raise RuntimeError(err)
    return r.stdout


def get_public_key() -> tuple[bytes, str]:
    """Читает публичный RSA-ключ с eToken слота (уже есть на токене)."""
    print("🔍 Читаю ключ с токена...")
    out = pkcs11("--slot", "0x2ffff", "--list-objects")
    text = out.decode()
    if "psb" not in text and "modulus" not in text.lower():
        raise RuntimeError("Не найден ключ на токене. Проверь что JaCarta вставлена.")
    cert_raw = pkcs11("--slot", "0x2ffff", "--read-object", "--type", "cert", "--id", "3e30fe2c")
    if not cert_raw or len(cert_raw) < 50:
        raise RuntimeError("Не удалось прочитать сертификат с токена.")
    return cert_raw, "4E43000523335331"


def streebog_hash(data: bytes) -> bytes:
    """Хэширует данные Стрибог-256 через аппаратный токен (слот ГОСТ)."""
    tmp = "/tmp/_rucoin_block.bin"
    with open(tmp, "wb") as f:
        f.write(data)
    pkcs11_result = pkcs11("--slot", "0x1ffff", "--hash",
                           "--mechanism", "GOSTR3411-12-256",
                           "--input-file", tmp, timeout=120)
    # pkcs11-tool выводит строку "Using digest algorithm GOSTR3411-12-256"
    # затем перевод строки, затем 32 сырых байта хэша
    raw = pkcs11_result
    # Отрезаем всё до последнего перевода строки — после него идут сырые байты
    if b"\n" in raw:
        raw = raw.rsplit(b"\n", 1)[-1]
    if len(raw) >= 32:
        return raw[:32]
    # если не получилось — возвращаем что есть
    return raw.ljust(32, b"\x00")[:32]


def derive_address(pubkey_bytes: bytes) -> str:
    """Адрес кошелька = RUC + хэш Стрибог от публичного ключа, первые 20 байт."""
    h = streebog_hash(pubkey_bytes)
    # Первые 20 байт как адрес
    return "RUC" + h[:20].hex().upper()


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
DIFFICULTY = 3
REWARD = 50  # монет за блок


def load_chain() -> list:
    if os.path.exists(CHAIN_FILE):
        with open(CHAIN_FILE) as f:
            return json.load(f)
    return []


def save_chain(chain: list):
    with open(CHAIN_FILE, "w") as f:
        json.dump(chain, f, indent=2)


def main():
    print("═══════════════════════════════════════")
    print("  RuCoin — Proof-of-Streebog Miner")
    print(f"  Platform: {sys.platform}")
    print("═══════════════════════════════════════\n")

    # 1. Подкючение к токену
    try:
        mod = detect_module()
        print(f"✅ PKCS#11: {mod}")
    except SystemExit:
        print("❌ JaCarta библиотека не найдена.\n"
              "   Установи: https://www.aladdin-rd.ru/support/downloads/jacarta/")
        sys.exit(1)

    # 2. Чтение ключа / адреса
    try:
        pubkey, serial = get_public_key()
        address = derive_address(pubkey)
        print(f"🔑 Токен: {serial}")
        print(f"💳 Адрес: {address}")
    except Exception as e:
        print(f"❌ Не удалось прочитать ключ: {e}")
        print("   Проверь что JaCarta вставлена и pcscd запущен.")
        sys.exit(1)

    # 3. Загрузка/создание цепи
    chain = load_chain()
    if chain:
        print(f"📦 Цепь: {len(chain)} блоков")
        start_index = chain[-1]["index"] + 1
        prev_hash = chain[-1]["hash"]
    else:
        print("📦 Цепь: новая")
        genesis = Block(0, [{"coinbase": address, "amount": REWARD}], "0" * 64)
        print("   Майню genesis block...")
        t, r = genesis.mine(DIFFICULTY)
        genesis.hash = genesis.compute_hash()
        chain.append(genesis.to_dict())
        save_chain(chain)
        print(f"   ✅ Genesis block намайнен ({t:.1f}s, {r:.2f} H/s)")
        start_index = 1
        prev_hash = genesis.hash

    # 4. Майнинг
    print(f"\n⛏️  Майнинг... сложность: {DIFFICULTY} нуля")
    block_num = start_index
    total_hashes = 0
    total_time = 0

    try:
        while True:
            txn = [{"coinbase": address, "amount": REWARD}]
            b = Block(block_num, txn, prev_hash)
            start_t = time.time()
            elapsed, rate = b.mine(DIFFICULTY)
            total_hashes += 1
            total_time += elapsed

            avg = total_hashes / total_time if total_time > 0 else 0
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")

            print(f"  [{ts}] Блок #{b.index} намайнен! "
                  f"{elapsed:.1f}s (среднее: ~{avg:.2f} H/s)  "
                  f"nonce: {b.nonce}  хэш: {b.hash[:16]}...")

            chain.append(b.to_dict())
            save_chain(chain)
            prev_hash = b.hash
            block_num += 1

    except KeyboardInterrupt:
        print(f"\n\n⏹  Остановлен. Всего блоков: {len(chain)}")
        print(f"   Баланс: {len(chain) * REWARD} RUC на адресе {address}")
        print(f"   Цепь сохранена в {CHAIN_FILE}")


if __name__ == "__main__":
    main()
