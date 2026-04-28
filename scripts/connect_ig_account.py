"""
Two-phase Instagram login connector with challenge support.

Phase 1 — attempt login, request verification code:
    python scripts/connect_ig_account.py phase1 <username> <password>

Phase 2 — submit verification code, save session:
    python scripts/connect_ig_account.py phase2 <username> <code>
"""

import sys
import json
import time
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
    print("ERROR: instagrapi not installed. Run inside the api container:")
    print("  docker compose exec -it api python scripts/connect_ig_account.py phase1 USER PASS")
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


def save_session(cl: Client, username: str):
    session_file = SESSION_DIR / f"{username}_session.json"
    cl.dump_settings(session_file)
    print(f"\n✓ Session saved: {session_file}")
    print("  The platform will use this session automatically for DM sending.")


def print_account_info(cl: Client):
    try:
        info = cl.account_info()
        print(f"\n  @{info.username} — {info.full_name}")
        print(f"  Followers: {info.follower_count:,}  |  Following: {info.following_count:,}")
        print(f"  Private: {info.is_private}")
    except Exception as e:
        print(f"  (Could not fetch account info: {e})")


# ---------------------------------------------------------------------------
# Phase 1: attempt login, trigger challenge, request code
# ---------------------------------------------------------------------------

def phase1(username: str, password: str):
    print(f"\n=== Phase 1: Login @{username} ===")

    # Restore existing session first if available
    session_file = SESSION_DIR / f"{username}_session.json"
    cl = build_client()

    if session_file.exists():
        print(f"Existing session found — trying to restore...")
        try:
            cl.load_settings(session_file)
            cl.login(username, password)
            print("LOGIN RESTORED — no challenge needed!")
            save_session(cl, username)
            print_account_info(cl)
            return
        except Exception as e:
            print(f"Session restore failed ({type(e).__name__}), doing fresh login...")
            session_file.unlink(missing_ok=True)
            cl = build_client()

    try:
        cl.login(username, password)
        print("LOGIN SUCCESSFUL — no challenge needed!")
        save_session(cl, username)
        print_account_info(cl)

    except ChallengeRequired:
        print("\n⚠ Instagram requires verification.")

        # Save full client state (cookies, device, tokens) for phase 2
        state_file = SESSION_DIR / f".challenge_{username}.json"
        cl.dump_settings(state_file)

        last = cl.last_json or {}
        challenge = last.get("challenge", {})
        api_path = challenge.get("api_path", "")

        # Save api_path + password for phase 2
        meta_file = SESSION_DIR / f".challenge_{username}_meta.json"
        meta_file.write_text(json.dumps({
            "api_path": api_path,
            "password": password,
            "last_json": last,
        }))

        print(f"  Challenge path: {api_path}")

        if not api_path:
            print("\nERROR: No challenge api_path. Full response:")
            print(json.dumps(last, indent=2)[:800])
            sys.exit(1)

        # Fetch challenge info (may show email/phone options)
        try:
            resp = cl.private.get(
                f"https://i.instagram.com{api_path}",
                headers=cl.base_headers,
            )
            info = resp.json() if hasattr(resp, "json") else {}
            step = info.get("step_data", {})
            if step.get("contact_point"):
                print(f"  Contact: {step['contact_point']}")
            elif step.get("email"):
                print(f"  Email: {step['email']}")
            elif step.get("phone_number"):
                print(f"  Phone: {step['phone_number']}")
        except Exception as e:
            print(f"  (Could not fetch challenge details: {e})")
            info = {}

        # Determine delivery method
        step = info.get("step_data", {}) if "info" in dir() else {}
        choice = "0" if step.get("phone_number") and not step.get("email") else "1"
        method = "SMS" if choice == "0" else "email"

        print(f"\nRequesting verification code via {method}...")
        try:
            resp = cl.private.post(
                f"https://i.instagram.com{api_path}",
                data={"choice": choice},
                headers=cl.base_headers,
            )
            print(f"  Response: {resp.text[:200]}")
        except Exception as e:
            print(f"  (Request error — code may have been sent anyway: {e})")

        print()
        print("=" * 50)
        print(f"  Check your {method} for the Instagram code.")
        print(f"  Then run:")
        print(f"    docker compose exec api python scripts/connect_ig_account.py phase2 {username} <CODE>")
        print("=" * 50)

    except TwoFactorRequired:
        print("\n⚠ Two-factor authentication required.")
        print("Run phase2 with your TOTP/authenticator code:")
        print(f"  docker compose exec api python scripts/connect_ig_account.py phase2 {username} <2FA_CODE> --2fa")
        # Save state for phase2
        state_file = SESSION_DIR / f".challenge_{username}.json"
        cl.dump_settings(state_file)
        meta_file = SESSION_DIR / f".challenge_{username}_meta.json"
        meta_file.write_text(json.dumps({"api_path": "", "password": password, "mode": "2fa"}))

    except BadPassword:
        print("\nERROR: Incorrect password.")
        sys.exit(1)

    except ReloginAttemptExceeded:
        print("\nERROR: Too many login attempts. Wait a while and try again.")
        sys.exit(1)

    except Exception as e:
        print(f"\nLOGIN FAILED: {type(e).__name__}: {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Phase 2: submit code, complete login, save session
# ---------------------------------------------------------------------------

def phase2(username: str, code: str, is_2fa: bool = False):
    print(f"\n=== Phase 2: Submit code for @{username} ===")

    state_file = SESSION_DIR / f".challenge_{username}.json"
    meta_file = SESSION_DIR / f".challenge_{username}_meta.json"

    if not state_file.exists():
        print("ERROR: No challenge state found. Run phase1 first.")
        sys.exit(1)

    meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    password = meta.get("password", "")
    api_path = meta.get("api_path", "")
    mode = meta.get("mode", "challenge")

    cl = build_client()
    cl.load_settings(state_file)

    if is_2fa or mode == "2fa":
        # 2FA login
        try:
            cl.login(username, password, verification_code=code)
            print("2FA LOGIN SUCCESSFUL!")
            save_session(cl, username)
            print_account_info(cl)
            _cleanup_challenge_files(username)
        except Exception as e:
            print(f"2FA failed: {type(e).__name__}: {e}")
            sys.exit(1)
        return

    if not api_path:
        print("ERROR: No challenge api_path in saved state.")
        sys.exit(1)

    print(f"Submitting code '{code}' to {api_path}...")

    try:
        resp = cl.private.post(
            f"https://i.instagram.com{api_path}",
            data={"security_code": code.strip()},
            headers=cl.base_headers,
        )
        result = resp.json() if hasattr(resp, "json") else {}
        print(f"Response: {json.dumps(result, indent=2)[:400]}")
    except Exception as e:
        print(f"Code submission error: {type(e).__name__}: {e}")
        sys.exit(1)

    # Check result
    logged_in = (
        result.get("logged_in_user")
        or result.get("status") == "ok"
        or "user_id" in result
    )

    if not logged_in and result.get("action") == "close":
        logged_in = True  # Instagram sometimes returns {"action":"close","status":"ok"}

    if logged_in:
        print("\n✓ Challenge resolved!")
    else:
        print("\nWarning: unexpected response, attempting login anyway...")

    # Attempt to finalize session
    time.sleep(1)
    try:
        cl.login(username, password)
    except ChallengeRequired:
        print("Still getting challenge — code may be wrong or expired.")
        sys.exit(1)
    except LoginRequired:
        pass  # Normal after challenge resolution
    except Exception:
        pass  # Try to save session anyway

    save_session(cl, username)
    print_account_info(cl)
    _cleanup_challenge_files(username)


def _cleanup_challenge_files(username: str):
    for f in [
        SESSION_DIR / f".challenge_{username}.json",
        SESSION_DIR / f".challenge_{username}_meta.json",
    ]:
        f.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        sys.exit(0)

    cmd = args[0].lower()

    if cmd == "phase1":
        if len(args) < 3:
            print("Usage: phase1 <username> <password>")
            sys.exit(1)
        phase1(args[1], args[2])

    elif cmd == "phase2":
        if len(args) < 3:
            print("Usage: phase2 <username> <code> [--2fa]")
            sys.exit(1)
        is_2fa = "--2fa" in args
        phase2(args[1], args[2], is_2fa)

    else:
        print(f"Unknown command: {cmd}")
        print("Use: phase1 <user> <pass>  OR  phase2 <user> <code>")
        sys.exit(1)
