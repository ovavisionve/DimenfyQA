#!/usr/bin/env python3
"""Test residential proxy connectivity and Apify API token.

Run from your local machine:
    python scripts/test_proxies.py
"""

import os
import sys
import time

import requests

# All 25 residential proxies
PROXIES = [
    "69.4.94.146:8800",
    "206.214.93.54:8800",
    "69.4.94.129:8800",
    "173.232.7.156:8800",
    "69.4.94.131:8800",
    "196.51.94.171:8800",
    "173.232.7.48:8800",
    "173.232.7.9:8800",
    "38.154.99.70:8800",
    "206.214.93.170:8800",
    "196.51.94.240:8800",
    "206.214.93.167:8800",
    "196.51.86.23:8800",
    "38.154.99.85:8800",
    "196.51.94.33:8800",
    "196.51.86.193:8800",
    "173.232.7.67:8800",
    "196.51.86.253:8800",
    "38.154.99.82:8800",
    "38.154.99.67:8800",
    "206.214.93.192:8800",
    "69.4.94.147:8800",
    "196.51.86.168:8800",
    "206.214.93.238:8800",
    "196.51.94.101:8800",
]

CHECK_URL = "https://checkip.amazonaws.com"
TIMEOUT = 15


def test_proxy(proxy_addr: str, protocol: str = "http") -> dict:
    """Test a single proxy. Returns dict with result."""
    proxy_url = f"{protocol}://{proxy_addr}"
    proxies = {"http": proxy_url, "https": proxy_url}
    start = time.time()
    try:
        resp = requests.get(CHECK_URL, proxies=proxies, timeout=TIMEOUT)
        elapsed = time.time() - start
        ip = resp.text.strip()
        return {"proxy": proxy_addr, "status": "OK", "ip": ip, "time_ms": int(elapsed * 1000)}
    except requests.exceptions.ProxyError as e:
        return {"proxy": proxy_addr, "status": "PROXY_ERROR", "error": str(e)[:80]}
    except requests.exceptions.ConnectTimeout:
        return {"proxy": proxy_addr, "status": "TIMEOUT", "error": f">{TIMEOUT}s"}
    except Exception as e:
        return {"proxy": proxy_addr, "status": "ERROR", "error": f"{type(e).__name__}: {str(e)[:60]}"}


def test_apify_token(token: str) -> bool:
    """Test Apify API token."""
    try:
        resp = requests.get(
            "https://api.apify.com/v2/users/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            print(f"  Usuario: {data.get('username', 'N/A')}")
            print(f"  Plan:    {data.get('plan', {}).get('id', 'N/A')}")
            return True
        print(f"  Error: HTTP {resp.status_code}")
        return False
    except Exception as e:
        print(f"  Error: {e}")
        return False


def main():
    print("=" * 60)
    print("  TEST DE CONECTIVIDAD — Proxies + Apify")
    print("=" * 60)

    # 1. Test without proxy (get real IP)
    print("\n[1] Tu IP pública (sin proxy):")
    try:
        resp = requests.get(CHECK_URL, timeout=10)
        real_ip = resp.text.strip()
        print(f"  → {real_ip}")
    except Exception as e:
        real_ip = "unknown"
        print(f"  → Error: {e}")

    # 2. Test Apify token
    print("\n[2] Apify API Token:")
    token = os.getenv("APIFY_API_TOKEN", "")
    if not token:
        # Try reading from .env
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        if os.path.exists(env_path):
            for line in open(env_path):
                if line.startswith("APIFY_API_TOKEN="):
                    token = line.split("=", 1)[1].strip()
                    break
    if token:
        test_apify_token(token)
    else:
        print("  No APIFY_API_TOKEN found")

    # 3. Test proxies
    print(f"\n[3] Probando {len(PROXIES)} proxies residenciales...")
    print(f"    Protocolo: HTTP | Timeout: {TIMEOUT}s")
    print("-" * 60)

    ok_count = 0
    fail_count = 0
    results = []

    for i, proxy in enumerate(PROXIES, 1):
        result = test_proxy(proxy)
        results.append(result)

        if result["status"] == "OK":
            ok_count += 1
            marker = "✓"
            detail = f"IP={result['ip']}  ({result['time_ms']}ms)"
        else:
            fail_count += 1
            marker = "✗"
            detail = f"{result['status']}: {result.get('error', '')}"

        print(f"  [{i:2d}/25] {marker} {proxy:22s} → {detail}")

    # 4. Summary
    print("\n" + "=" * 60)
    print(f"  RESULTADO: {ok_count} OK / {fail_count} FALLOS de {len(PROXIES)} proxies")
    print("=" * 60)

    if ok_count == 0 and fail_count > 0:
        print("\n  ⚠ Ningún proxy funciona.")
        print("  Posibles causas:")
        print(f"  1. Tu IP pública ({real_ip}) no está whitelisted con el proveedor")
        print("  2. Los proxies son SOCKS5 en vez de HTTP — reintenta con: python scripts/test_proxies.py --socks5")
        print("  3. Los proxies requieren autenticación (usuario:contraseña)")

    if ok_count > 0:
        # Show working proxies for easy copy-paste to .env
        working = [r["proxy"] for r in results if r["status"] == "OK"]
        print(f"\n  Proxies funcionales para .env:")
        print(f"  PROXY_URL=http://{working[0]}")
        if len(working) > 1:
            print(f"\n  Para multi-cuenta, asigna 1 proxy por cuenta IG.")

    return 0 if ok_count > 0 else 1


if __name__ == "__main__":
    # Support --socks5 flag
    if "--socks5" in sys.argv:
        print("Modo SOCKS5 activado\n")
        # Override test function to use socks5
        _original_test = test_proxy
        test_proxy = lambda p: _original_test(p, protocol="socks5")

    sys.exit(main())
