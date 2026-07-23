#!/usr/bin/env python3
"""
RuCoin — Proof-of-Streebog Miner
─────────────────────────────────
Вставил токен → python3 rucoin.py → майнишь на свой кошелёк.

Эмиссия: 256 000 000 RUC
Награда: 2048 RUC/блок, халвинг каждые 62 500 блоков
Стрибог-256 на аппаратном токене JaCarta (без пароля!)

Режимы:
  --solo    Соло-майнинг (по умолчанию)
  --pool    Пул-майнинг через HTTP/JSON API
  --worker  Имя воркера (обязательно для пула)
"""

import argparse
import subprocess
import json
import time
import struct
import sys
import os
import codecs
import hashlib
from datetime import datetime, timezone
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

try:
    import requests
except ImportError:
    requests = None

# ═══ Параметры эмиссии ═══

INITIAL_REWARD = 2048        # RUC (2¹¹)
HALVING_INTERVAL = 62500
TOTAL_SUPPLY = 256_000_000
SATOSHI = 0.00000001

DIFFICULTY = 3
WALLET_FILE = "rucoin_wallet.pem"
CHAIN_FILE = "rucoin_chain.json"
POOL_URL = "https://rucoin.vercel.app/api/pool"

PKCS11_PATHS = {
    "linux":  "/usr/lib/libjcPKCS11-2.so",
    "linux2": "/usr/lib/libjcPKCS11-2.so",
    "win32":  "C:/Windows/System32/jcPKCS11-2.dll",
    "cygwin": "jcPKCS11-2.dll",
    "darwin": "/Library/Frameworks/jcPKCS11-2.framework/jcPKCS11-2",
}


def parse_args():
    p = argparse.ArgumentParser(description="RuCoin Streebog Miner")
    p.add_argument("--solo", action="store_true", help="Соло-майнинг (по умолчанию)")
    p.add_argument("--pool", action="store_true", help="Пул-майнинг через HTTP API")
    p.add_argument("--worker", type=str, default="", help="Имя воркера (обязательно для пула)")
    p.add_argument("--pool-url", type=str, default=POOL_URL, help="URL пула")
    p.add_argument("--stats", action="store_true", help="Показать статистику сети и выйти")
    return p.parse_args()


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
    out = pkcs11("-L")
    for line in out.decode().splitlines():
        line_lower = line.lower()
        if "serial" in line_lower and ("number" in line_lower or "num" in line_lower):
            serial = line.split(":")[-1].strip()
            if serial and serial != "00000000":
                return serial
    raise RuntimeError("Серийный номер не найден. Токен вставлен? pcscd запущен?")


def derive_keys(serial: str) -> tuple[str, str]:
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
    serial = get_token_serial()
    _, address = derive_keys(serial)

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
        data = struct.pack(">IQ", self.index, self.timestamp)
        data += self.prev_hash.encode()
        data += json.dumps(self.txns, sort_keys=True).encode()
        data += struct.pack(">Q", self.nonce)
        return data

    def compute_hash(self) -> str:
        raw = self.serialize()
        h = streebog_hash(raw)
        return h.hex()

    def mine(self, difficulty: int):
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


# ═══ Pool API (HTTP/JSON) ═══

def pool_get_job(pool_url: str, worker: str) -> dict:
    """Получает job от пула: height, prev_hash, difficulty, target."""
    if requests is None:
        return {"error": "requests library not installed (pip install requests)"}
    try:
        r = requests.post(f"{pool_url}/job", json={"worker": worker}, timeout=10)
        if r.ok:
            return r.json()
        return {"error": f"HTTP {r.status_code}: {r.text}"}
    except Exception as e:
        return {"error": str(e)}


def pool_submit_share(pool_url: str, worker: str, block: dict, address: str) -> dict:
    """Отправляет найденный блок/шер в пул."""
    if requests is None:
        return {"error": "requests library not installed"}
    try:
        r = requests.post(f"{pool_url}/submit", json={
            "worker": worker,
            "block": block,
            "address": address
        }, timeout=10)
        if r.ok:
            return r.json()
        return {"error": f"HTTP {r.status_code}: {r.text}"}
    except Exception as e:
        return {"error": str(e)}


def pool_get_stats(pool_url: str) -> dict:
    """Получает статистику пула для веб-страницы."""
    if requests is None:
        return {"error": "requests library not installed"}
    try:
        r = requests.get(f"{pool_url}/stats", timeout=5)
        if r.ok:
            return r.json()
        return {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}


# ═══ Блокчейн ═══
    epoch = index // HALVING_INTERVAL
    reward = INITIAL_REWARD >> epoch
    min_reward = SATOSHI
    if reward < min_reward:
        reward = INITIAL_REWARD / (2 ** epoch)
        if reward < min_reward:
            return 0.0
    return float(reward)


def halving_epoch(index: int) -> int:
    return index // HALVING_INTERVAL


def total_mined(chain_len: int) -> int:
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


# ═══ Пул-майнинг ═══

def pool_submit_share(pool_url: str, worker: str, block_data: dict, address: str) -> dict:
    """Отправляет найденный блок/шер на пул."""
    if requests is None:
        raise RuntimeError("requests не установлен: pip install requests")
    payload = {
        "worker": worker,
        "address": address,
        "block": block_data,
        "timestamp": int(time.time()),
    }
    try:
        r = requests.post(f"{pool_url}/submit", json=payload, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def pool_get_job(pool_url: str, worker: str) -> dict:
    """Получает задание от пула (текущая высота, prev_hash, difficulty)."""
    if requests is None:
        raise RuntimeError("requests не установлен")
    try:
        r = requests.get(f"{pool_url}/job", params={"worker": worker}, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def pool_get_stats(pool_url: str) -> dict:
    if requests is None:
        return {"error": "requests not installed"}
    try:
        r = requests.get(f"{pool_url}/stats", timeout=5)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def print_network_stats():
    """Показывает статистику сети (для флага --stats)."""
    chain = load_chain()
    if not chain:
        print("Сеть пуста (нет блоков)")
        return

    height = len(chain) - 1
    last_block = chain[-1]
    reward = reward_for_block(height)
    epoch = halving_epoch(height)
    next_halving = HALVING_INTERVAL - (height % HALVING_INTERVAL)
    total = total_mined(len(chain))

    # Оценка network hashrate по последним 10 блокам
    hashrate = 0.0
    if len(chain) >= 2:
        recent = chain[-10:]
        if len(recent) >= 2:
            time_diff = recent[-1]["timestamp"] - recent[0]["timestamp"]
            blocks = len(recent)
            if time_diff > 0:
                # hash rate = blocks * 2^DIFFICULTY / time
                hashrate = (blocks * (2 ** DIFFICULTY)) / time_diff
            else:
                hashrate = 0
        else:
            hashrate = 0
    else:
        hashrate = 0

    print("═══ RuCoin Network Stats ═══")
    print(f"Chain height     : {height}")
    print(f"Current reward   : {reward} RUC")
    print(f"Halving epoch    : #{epoch}")
    print(f"Next halving in  : {next_halving} blocks")
    print(f"Total mined      : {total:.2f} / {TOTAL_SUPPLY} RUC ({(total/TOTAL_SUPPLY)*100:.2f}%)")
    print(f"Difficulty       : {DIFFICULTY} leading zeros")
    print(f"Network hashrate : ~{hashrate:.2f} H/s (estimate)")
    print("═══════════════════════════")


# ═══ Main ═══

def main():
    args = parse_args()

    if args.stats:
        print_network_stats()
        return

    # Режим: по умолчанию соло, если указан --pool — пул
    mode = "pool" if args.pool else "solo"

    if mode == "pool" and not args.worker:
        print("❌ Для пул-майнинга укажите --worker ВАШ_НИК")
        sys.exit(1)

    if not args.worker:
        raw = input("Имя воркера (Enter = Satoshi): ").strip() or "Satoshi"
        try:
            worker = codecs.decode(raw, 'unicode_escape')
        except Exception:
            worker = raw
    else:
        worker = args.worker

    print("═══════════════════════════════════════")
    print("  RuCoin — Proof-of-Streebog Miner")
    print(f"  Platform: {sys.platform}")
    print(f"  Mode      : {'Pool' if mode == 'pool' else 'Solo'}")
    print(f"  Worker    : {worker}")
    print(f"  Emission  : {TOTAL_SUPPLY} RUC")
    print(f"  Start     : {INITIAL_REWARD} RUC/block, halving every {HALVING_INTERVAL} blocks")
    print("═══════════════════════════════════════\n")

    try:
        mod = detect_module()
        print(f"✅ PKCS#11: {mod}")
    except SystemExit:
        print("❌ JaCarta library not found.\n   Get it: https://www.aladdin-rd.ru/support/downloads/jacarta/")
        sys.exit(1)

    print("🚀 Checking Streebog...")
    streebog_hash(b"rucoin_test")
    print("✅ Streebog-256 works (no PIN!)\n")

    _, address = get_or_create_wallet()
    print(f"💳 Address: {address}")
    print(f"🔑 Key file: {WALLET_FILE}\n")

    chain = load_chain()
    if chain:
        print(f"📦 Chain: {len(chain)} blocks")
        start_index = chain[-1]["index"] + 1
        prev_hash = chain[-1]["hash"]
    else:
        print("📦 Chain: new")
        genesis_reward = reward_for_block(0)
        genesis = Block(0, [{"coinbase": address, "amount": genesis_reward}], "0" * 64)
        print(f"   Mining genesis block (reward: {genesis_reward} RUC)...")
        t, r = genesis.mine(DIFFICULTY)
        genesis.hash = genesis.compute_hash()
        chain.append(genesis.to_dict())
        save_chain(chain)
        print(f"   ✅ Genesis mined ({t:.1f}s, {r:.2f} H/s)")
        start_index = 1
        prev_hash = genesis.hash

    show_halving_info(start_index)
    print(f"\n⛏️  Mining... difficulty: {DIFFICULTY} leading zeros")
    if mode == "pool":
        print(f"   Pool: {args.pool_url}")
    block_num = start_index
    total_hashes = 0
    total_time = 0.0

    # Для пула: пробуем получить job при старте
    pool_job = None
    if mode == "pool":
        print("   Fetching pool job...")
        job = pool_get_job(args.pool_url, worker)
        if "error" not in job:
            pool_job = job
            print(f"   ✅ Pool job: height={job.get('height')}, diff={job.get('difficulty')}")
        else:
            print(f"   ⚠️  Pool unavailable: {job.get('error')}, falling back to solo logic")

    try:
        while True:
            txn_reward = reward_for_block(block_num)
            txn = [{"coinbase": address, "amount": txn_reward}]

            # Для пула используем prev_hash из job'а, если есть
            current_prev = prev_hash
            current_diff = DIFFICULTY
            if mode == "pool" and pool_job:
                current_prev = pool_job.get("prev_hash", prev_hash)
                current_diff = pool_job.get("difficulty", DIFFICULTY)

            b = Block(block_num, txn, current_prev)
            start_t = time.time()
            elapsed, rate = b.mine(current_diff)
            total_hashes += 1
            total_time += elapsed

            avg = total_hashes / total_time if total_time > 0 else 0
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")

            print(f"  [{ts}] Block #{b.index} mined! "
                  f"{elapsed:.1f}s (avg: ~{avg:.2f} H/s)  "
                  f"nonce: {b.nonce}  hash: {b.hash[:16]}...  "
                  f"+{txn_reward} RUC")

            # Сохраняем локально
            chain.append(b.to_dict())
            save_chain(chain)
            prev_hash = b.hash
            block_num += 1

            # Если пул — отправляем шер/блок
            if mode == "pool":
                result = pool_submit_share(args.pool_url, worker, b.to_dict(), address)
                if "error" in result:
                    print(f"   ⚠️  Pool submit error: {result['error']}")
                elif result.get("accepted"):
                    print(f"   ✅ Pool accepted share! Payout: {result.get('payout', 'pending')} RUC")
                else:
                    print(f"   ℹ️  Pool response: {result}")

            # Каждые 10 блоков обновляем job от пула
            if mode == "pool" and block_num % 10 == 0:
                job = pool_get_job(args.pool_url, worker)
                if "error" not in job:
                    pool_job = job

            if block_num % HALVING_INTERVAL == 0:
                epoch = halving_epoch(block_num)
                print(f"\n═══ HALVING! Epoch #{epoch} — reward now {reward_for_block(block_num)} RUC ═══\n")

    except KeyboardInterrupt:
        mined = total_mined(len(chain))
        print(f"\n\n⏹  Stopped. Total blocks: {len(chain)}")
        print(f"   Mined: {mined:.2f} RUC / {TOTAL_SUPPLY} RUC ({mined/TOTAL_SUPPLY*100:.4f}%)")
        print(f"   Address: {address}")
        print(f"   Chain saved to {CHAIN_FILE}")


if __name__ == "__main__":
    main()