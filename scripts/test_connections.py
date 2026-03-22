"""
Test script: Verify proxy connectivity and Instagram account login.
No database required — tests proxies and IG credentials directly.
"""
import requests
import time
import sys

# 10 IG accounts with their assigned Webshare proxies
ACCOUNTS = [
    {"username": "obapivs3", "password": "r0k9JXOrnT", "proxy": "http://fddwhmln:tye1hvbkhnz5@31.59.20.176:6754"},
    {"username": "km5x79y1", "password": "GGusv44OX5", "proxy": "http://fddwhmln:tye1hvbkhnz5@23.95.150.145:6114"},
    {"username": "ybbhqmuk", "password": "SU7JyJvyfA", "proxy": "http://fddwhmln:tye1hvbkhnz5@198.23.239.134:6540"},
    {"username": "kalnesf8", "password": "52SBilB8G8", "proxy": "http://fddwhmln:tye1hvbkhnz5@45.38.107.97:6014"},
    {"username": "on1eojge", "password": "nBBJfEtMXy", "proxy": "http://fddwhmln:tye1hvbkhnz5@107.172.163.27:6543"},
    {"username": "ioq1gstnf", "password": "xY7sZB4kzt", "proxy": "http://fddwhmln:tye1hvbkhnz5@198.105.121.200:6462"},
    {"username": "ln7cx7qv", "password": "4qU1UEC6uJh", "proxy": "http://fddwhmln:tye1hvbkhnz5@64.137.96.74:6641"},
    {"username": "f0tmjwuy", "password": "0faoBBhCECzF", "proxy": "http://fddwhmln:tye1hvbkhnz5@216.10.27.159:6837"},
    {"username": "jofiqzge", "password": "HhvqXtokbMz", "proxy": "http://fddwhmln:tye1hvbkhnz5@142.111.67.146:5611"},
    {"username": "usnsmcty", "password": "mXq2rD1oqv9Y", "proxy": "http://fddwhmln:tye1hvbkhnz5@191.96.254.138:6185"},
]


def test_proxy(account: dict) -> dict:
    """Test proxy connectivity by hitting httpbin."""
    proxy_url = account["proxy"]
    proxies = {"http": proxy_url, "https": proxy_url}
    try:
        resp = requests.get("http://httpbin.org/ip", proxies=proxies, timeout=15)
        if resp.status_code == 200:
            ip = resp.json().get("origin", "unknown")
            return {"status": "OK", "ip": ip}
        return {"status": "FAIL", "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "FAIL", "error": str(e)[:80]}


def test_ig_login(account: dict) -> dict:
    """Test Instagram login via instagrapi."""
    try:
        from instagrapi import Client
        cl = Client()

        # Set proxy
        cl.set_proxy(account["proxy"])

        # Set realistic device
        cl.set_device({
            "app_version": "269.0.0.18.75",
            "android_version": 33,
            "android_release": "13",
            "dpi": "560dpi",
            "resolution": "1440x3200",
            "manufacturer": "Samsung",
            "device": "SM-S908B",
            "model": "samsung",
        })

        cl.delay_range = [2, 5]
        cl.login(account["username"], account["password"])
        user_id = cl.user_id
        return {"status": "OK", "user_id": str(user_id)}
    except Exception as e:
        return {"status": "FAIL", "error": str(e)[:120]}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "proxy"

    if mode == "proxy":
        print("=" * 60)
        print("TESTING PROXY CONNECTIVITY")
        print("=" * 60)
        ok = 0
        for i, acc in enumerate(ACCOUNTS, 1):
            result = test_proxy(acc)
            status_icon = "✓" if result["status"] == "OK" else "✗"
            detail = result.get("ip", result.get("error", ""))
            print(f"  [{i:2d}] {acc['username']:12s} → {status_icon} {result['status']}  (IP: {detail})")
            if result["status"] == "OK":
                ok += 1
        print(f"\nResult: {ok}/10 proxies working")

    elif mode == "login":
        print("=" * 60)
        print("TESTING INSTAGRAM LOGIN (1 account only)")
        print("=" * 60)
        # Only test first account to avoid triggering Instagram
        acc = ACCOUNTS[0]
        print(f"  Testing {acc['username']}...")
        result = test_ig_login(acc)
        status_icon = "✓" if result["status"] == "OK" else "✗"
        detail = result.get("user_id", result.get("error", ""))
        print(f"  {status_icon} {result['status']}: {detail}")

    else:
        print("Usage: python test_connections.py [proxy|login]")


if __name__ == "__main__":
    main()
