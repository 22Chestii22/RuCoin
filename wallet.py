#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RuCoin Wallet — Local Key Derivation
Reads JaCarta token via PKCS#11, derives Secret Key and Public Address.
"""

import json
import hashlib
import os
import sys
import subprocess

CHAIN_FILE = "rucoin_chain.json"
PKCS11_LIB = "/usr/lib/libjcPKCS11-2.so"


def get_token_serial() -> str:
    if not os.path.exists(PKCS11_LIB):
        sys.exit(f"error: PKCS#11 library not found at {PKCS11_LIB}")

    try:
        out = subprocess.check_output(
            ["pkcs11-tool", "--module", PKCS11_LIB, "-L"],
            stderr=subprocess.STDOUT, text=True, timeout=10
        )
    except subprocess.CalledProcessError as e:
        sys.exit(f"error: pkcs11-tool failed:\n{e.output}")
    except FileNotFoundError:
        sys.exit("error: pkcs11-tool not found. Install opensc package.")

    for line in out.splitlines():
        line_lower = line.lower()
        if "serial" in line_lower and ("number" in line_lower or "num" in line_lower):
            serial = line.split(":")[-1].strip()
            if serial and serial != "00000000":
                return serial

    sys.exit("error: token serial number not found. Check if token is inserted and pcscd is running.")


def derive_keys(serial: str) -> tuple[str, str]:
    secret_key = hashlib.sha256(f"rucoin_secret_{serial}".encode()).hexdigest()
    address_hash = hashlib.sha256(secret_key.encode()).hexdigest()[:40].upper()
    address = f"RUC{address_hash}"
    return secret_key, address


def load_chain() -> list:
    if os.path.exists(CHAIN_FILE):
        try:
            with open(CHAIN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def compute_balance(chain: list, address: str) -> float:
    balance = 0.0
    for block in chain:
        for tx in block.get("transactions", []):
            if tx.get("to") == address:
                balance += float(tx.get("amount", 0))
            if tx.get("from") == address:
                balance -= float(tx.get("amount", 0))
    return max(0.0, balance)


def main():
    print("○ RuCoin / Wallet")
    print("Reading JaCarta token...")

    serial = get_token_serial()
    secret_key, address = derive_keys(serial)

    chain = load_chain()
    balance = compute_balance(chain, address)

    print(f"\n[+] Token detected: {serial}")
    print(f"[+] Secret Key : {secret_key}")
    print(f"[+] Address    : {address}")
    print(f"[+] Balance    : {balance:.4f} RUC")
    print(f"\n[>] Web Wallet: https://rucoin.vercel.app/wallet\n")


if __name__ == "__main__":
    main()
