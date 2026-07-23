#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RuCoin Wallet — читает JaCarta токен, показывает адрес и баланс.
Адрес = SHA256(serial_number) — одинаковый везде.
"""

import json
import hashlib
import os
import sys
import subprocess
from pathlib import Path

CHAIN_FILE = "rucoin_chain.json"
PKCS11_LIB = "/usr/lib/libjcPKCS11-2.so"


def get_token_serial() -> str:
    """Читает серийный номер токена через pkcs11-tool."""
    if not os.path.exists(PKCS11_LIB):
        sys.exit(f"❌ PKCS#11 библиотека не найдена: {PKCS11_LIB}\n"
                 f"   Скачай с aladdin-rd.ru → /usr/lib/")

    try:
        out = subprocess.check_output(
            ["pkcs11-tool", "--module", PKCS11_LIB, "-L"],
            stderr=subprocess.STDOUT, text=True, timeout=10
        )
    except subprocess.CalledProcessError as e:
        sys.exit(f"❌ Ошибка pkcs11-tool:\n{e.output}")
    except FileNotFoundError:
        sys.exit("❌ pkcs11-tool не установлен: sudo pacman -S opensc")

    # Ищем серийный номер в выводе
    for line in out.splitlines():
        if "Serial number" in line or "serial number" in line.lower():
            serial = line.split(":")[-1].strip()
            if serial and serial != "00000000":
                return serial

    sys.exit("❌ Серийный номер не найден. Токен вставлен? pcscd запущен?")


def serial_to_address(serial: str) -> str:
    """Адрес = SHA256(serial) → RUC + 40 hex chars."""
    h = hashlib.sha256(serial.encode()).hexdigest()[:40].upper()
    return f"RUC{h}"


def load_chain() -> list:
    if os.path.exists(CHAIN_FILE):
        with open(CHAIN_FILE) as f:
            return json.load(f)
    return []


def compute_balance(chain: list, address: str) -> float:
    balance = 0.0
    for block in chain:
        for tx in block.get("transactions", []):
            if tx.get("to") == address:
                balance += tx.get("amount", 0)
            if tx.get("from") == address:
                balance -= tx.get("amount", 0)
    return max(0.0, balance)


def main():
    print("═══ RuCoin Wallet ═══")
    print("Читаю токен...")

    serial = get_token_serial()
    address = serial_to_address(serial)

    print(f"\n🔑 Серийный номер: {serial}")
    print(f"📬 Адрес:          {address}")

    chain = load_chain()
    balance = compute_balance(chain, address)
    print(f"💰 Баланс:         {balance:.4f} RUC")

    print("\n💡 Введи этот адрес в браузере: https://rucoin.vercel.app/wallet")


if __name__ == "__main__":
    main()