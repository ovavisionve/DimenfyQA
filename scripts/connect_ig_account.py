"""
Interactive Instagram account connector with challenge (2FA code) support.

Usage (inside the api container):
    docker compose exec -it api python scripts/connect_ig_account.py

What it does:
  1. Logs in to Instagram via instagrapi
  2. If Instagram sends a verification code (email/SMS), prompts you to enter it
  3. Saves the session to ig_sessions/<username>_session.json
  4. The platform's dm_sender_service picks up the session automatically on next use
"""

import sys
import json
import time
from getpass import getpass
from pathlib import Path

try:
    from instagrapi import Client
    from instagrapi.exceptions import (
        ChallengeRequired,
        BadPassword,
        ReloginAttemptExceeded,
        TwoFactorRequired,
        LoginRequired,
    )
except ImportError:
    print("ERROR: instagrapi not installed. Run this inside the api container.")
    print("  docker compose exec -it api python scripts/connect_ig_account.py")
    sys.exit(1)


SESSION_DIR = Path("ig_sessions")
SESSION_DIR.mkdir(exist_ok=True)

DEVICE = {
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
}
USER_AGENT = (
    "Instagram 269.0.0.18.75 Android "
    "(31/12; 480dpi; 1080x2400; Samsung; SM-G991B; SM-G991B; samsung; en_US; 314665256)"
)


def build_client() -> Client:
    cl = Client()
    cl.set_device(DEVICE)
    cl.set_user_agent(USER_AGENT)
    cl.delay_range = [2, 5]
    return cl


def resolve_challenge(cl: Client) -> bool:
    """Handle Instagram challenge (email/SMS verification code)."""
    print()
    print("Instagram requires verification.")

    last = cl.last_json or {}
    challenge_info = last.get("challenge", {})
    api_path = challenge_info.get("api_path", "")

    if not api_path:
        print(f"No challenge path found. Last response: {json.dumps(last, indent=2)[:500]}")
        return False

    print(f"Challenge path: {api_path}")

    # Step 1: Get available verification methods
    try:
        resp = cl.private.get(
            f"https://i.instagram.com{api_path}",
            headers=cl.base_headers,
        )
        data = resp.json() if hasattr(resp, "json") else {}
        print(f"Challenge info: {json.dumps(data, indent=2)[:400]}")
    except Exception as e:
        print(f"(Could not fetch challenge info: {e})")
        data = {}

    # Step 2: Request code — try email (1) first, fall back to SMS (0)
    choice = "1"  # 1 = email
    if "step_data" in data:
        step = data.get("step_data", {})
        if step.get("phone_number") and not step.get("email"):
            choice = "0"  # SMS only
            print("Will send code via SMS")
        else:
            print("Will send code via email")
    else:
        print("Requesting code via email (choice=1) ...")

    try:
        resp = cl.private.post(
            f"https://i.instagram.com{api_path}",
            data={"choice": choice},
            headers=cl.base_headers,
        )
        print(f"Code request response: {resp.text[:200]}")
    except Exception as e:
        print(f"(Code request error: {e} — code may have been sent anyway)")

    # Step 3: Ask user for the code
    print()
    code = input("Enter the verification code you received: ").strip()
    if not code:
        print("No code entered. Aborting.")
        return False

    # Step 4: Submit the code
    try:
        resp = cl.private.post(
            f"https://i.instagram.com{api_path}",
            data={"security_code": code},
            headers=cl.base_headers,
        )
        result = resp.json() if hasattr(resp, "json") else {}
        print(f"Code submission response: {json.dumps(result, indent=2)[:400]}")

        if result.get("status") == "ok" or result.get("logged_in_user"):
            print("Challenge resolved successfully!")
            return True
        else:
            print("Challenge resolution may have failed. Trying to continue...")
            return True  # Sometimes the response is non-standard but login works

    except Exception as e:
        print(f"Code submission error: {e}")
        return False


def save_session(cl: Client, username: str):
    session_file = SESSION_DIR / f"{username}_session.json"
    cl.dump_settings(session_file)
    print(f"\nSession saved to {session_file}")
    print("The platform will use this session automatically for DM sending.")


def main():
    print("=" * 55)
    print("  Instagram Account Connector — IG DM Engine")
    print("=" * 55)
    print()

    username = input("Instagram username: ").strip()
    if not username:
        print("Username required.")
        sys.exit(1)

    password = getpass("Password: ")
    if not password:
        print("Password required.")
        sys.exit(1)

    proxy = input("Proxy (leave empty for none) [format: http://user:pass@host:port]: ").strip()

    print()
    print(f"Connecting @{username}...")

    # Check for existing session
    session_file = SESSION_DIR / f"{username}_session.json"
    if session_file.exists():
        print(f"Found existing session at {session_file} — will try to restore it first.")

    cl = build_client()
    if proxy:
        cl.set_proxy(proxy)
        print(f"Using proxy: {proxy}")

    # Attempt 1: restore or fresh login
    try:
        if session_file.exists():
            try:
                cl.load_settings(session_file)
                cl.login(username, password)
                print("Session restored successfully!")
                save_session(cl, username)
                _print_account_info(cl)
                return
            except (LoginRequired, Exception) as e:
                print(f"Session restore failed ({type(e).__name__}), doing fresh login...")
                session_file.unlink(missing_ok=True)
                cl = build_client()
                if proxy:
                    cl.set_proxy(proxy)

        cl.login(username, password)
        print("LOGIN SUCCESSFUL!")
        save_session(cl, username)
        _print_account_info(cl)

    except ChallengeRequired:
        print()
        print("Instagram sent a verification challenge.")
        if resolve_challenge(cl):
            time.sleep(2)
            # Retry login after challenge
            try:
                cl.login(username, password)
            except Exception:
                pass  # Sometimes login state is already set after challenge
            try:
                save_session(cl, username)
                _print_account_info(cl)
            except Exception as e:
                print(f"(Could not verify account info: {e})")
                # Save session anyway — it might still work
                save_session(cl, username)
        else:
            print("Could not resolve challenge. Try again or contact Instagram support.")
            sys.exit(1)

    except TwoFactorRequired:
        print()
        print("Two-factor authentication required.")
        code = input("Enter your 2FA code (TOTP/authenticator app): ").strip()
        try:
            cl.login(username, password, verification_code=code)
            print("2FA login successful!")
            save_session(cl, username)
            _print_account_info(cl)
        except Exception as e:
            print(f"2FA login failed: {e}")
            sys.exit(1)

    except BadPassword:
        print("ERROR: Wrong password.")
        sys.exit(1)

    except ReloginAttemptExceeded:
        print("ERROR: Too many login attempts. Wait before retrying.")
        sys.exit(1)

    except Exception as e:
        print(f"LOGIN FAILED: {type(e).__name__}: {e}")
        sys.exit(1)


def _print_account_info(cl: Client):
    try:
        info = cl.account_info()
        print()
        print("Account info:")
        print(f"  Username  : @{info.username}")
        print(f"  Full name : {info.full_name}")
        print(f"  Followers : {info.follower_count:,}")
        print(f"  Following : {info.following_count:,}")
        print(f"  Posts     : {info.media_count}")
        print(f"  Private   : {info.is_private}")
    except Exception as e:
        print(f"(Could not fetch account info: {e})")

    print()
    print("Next steps:")
    print("  1. Go to Settings → 'Cuentas y Proxies' in the dashboard")
    print("  2. Add the account there if not already listed")
    print("  3. Start a campaign and click 'Enviar DMs'")


if __name__ == "__main__":
    main()
