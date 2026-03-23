"""
Quick test: connect to Instagram with instagrapi.
Usage: python scripts/test_ig_login.py
"""
import os
import sys

# Load .env
from pathlib import Path
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

from instagrapi import Client

USERNAME = os.getenv("IG_USERNAME", "")
PASSWORD = os.getenv("IG_PASSWORD", "")
PROXY = os.getenv("PROXY_URL", "")

if not USERNAME or not PASSWORD:
    print("ERROR: Set IG_USERNAME and IG_PASSWORD in .env or environment")
    print("  Supports username or email for login")
    sys.exit(1)

print(f"=== Instagram Login Test ===")
print(f"Username: {USERNAME}")
print(f"Proxy: {PROXY or '(none)'}")
print()

cl = Client()

# Set a realistic device profile (Samsung Galaxy S21)
cl.set_device({
    "app_version": "269.0.0.18.75",
    "android_version": 31,
    "android_release": "12",
    "dpi": "480dpi",
    "resolution": "1080x2400",
    "manufacturer": "Samsung",
    "device": "SM-G991B",
    "model": "samsung",
    "cpu": "qcom",
    "version_code": "314665256",
})

cl.set_user_agent(
    "Instagram 269.0.0.18.75 Android "
    "(31/12; 480dpi; 1080x2400; Samsung; SM-G991B; SM-G991B; samsung; en_US; 314665256)"
)

if PROXY:
    print(f"Setting proxy: {PROXY}")
    cl.set_proxy(PROXY)

cl.delay_range = [2, 5]

print("Attempting login...")
try:
    cl.login(USERNAME, PASSWORD)
    print(f"LOGIN SUCCESSFUL!")
    print()

    # Get basic account info
    info = cl.account_info()
    print(f"Account info:")
    print(f"  Full name: {info.full_name}")
    print(f"  Bio: {info.biography[:80] if info.biography else '(empty)'}")
    print(f"  Followers: {info.follower_count}")
    print(f"  Following: {info.following_count}")
    print(f"  Posts: {info.media_count}")
    print(f"  Is private: {info.is_private}")
    print()

    # Save session for reuse
    session_dir = Path("ig_sessions")
    session_dir.mkdir(exist_ok=True)
    session_file = session_dir / f"{USERNAME}_session.json"
    cl.dump_settings(session_file)
    print(f"Session saved to {session_file}")

except Exception as e:
    print(f"LOGIN FAILED: {type(e).__name__}: {e}")
    sys.exit(1)
