"""
Instagram login with challenge (verification code) support.
Usage: docker compose exec -it api python scripts/ig_challenge_login.py
"""
import sys
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired


USERNAME = "orlandodimenfy"
PASSWORD = "Apolo0501."

print(f"=== Instagram Login with Challenge Support ===")
print(f"Username: {USERNAME}")
print()

cl = Client()
cl.delay_range = [2, 5]

print("Attempting login...")
try:
    cl.login(USERNAME, PASSWORD)
    print("LOGIN SUCCESSFUL (no challenge needed)!")
except ChallengeRequired:
    print("Challenge required! Resolving...")
    print()

    try:
        # Get challenge info
        api_path = cl.last_json.get("challenge", {}).get("api_path")
        if not api_path:
            print("ERROR: No challenge API path found")
            print(f"Last JSON: {cl.last_json}")
            sys.exit(1)

        print(f"Challenge API path: {api_path}")

        # Request the challenge (sends code via email/sms)
        cl.challenge_resolve(cl.last_json)
    except Exception as e2:
        print(f"Challenge resolve error (expected): {type(e2).__name__}")

    # Try to get challenge choices
    try:
        resp = cl.private.get(
            f"https://i.instagram.com{api_path}",
            headers=cl.base_headers,
        )
        print(f"Challenge response: {resp.text[:500]}")
    except Exception as e3:
        print(f"GET challenge info: {e3}")

    # Select email verification (choice 1)
    try:
        resp = cl.private.post(
            f"https://i.instagram.com{api_path}",
            data={"choice": "1"},  # 1 = email, 0 = SMS
            headers=cl.base_headers,
        )
        print(f"Code sent! Response: {resp.text[:300]}")
    except Exception as e4:
        print(f"Send code error: {e4}")

    print()
    code = input("Enter the verification code from your email: ").strip()

    # Submit the code
    try:
        resp = cl.private.post(
            f"https://i.instagram.com{api_path}",
            data={"security_code": code},
            headers=cl.base_headers,
        )
        print(f"Code submit response: {resp.text[:500]}")

        # Try login again after challenge
        print()
        print("Retrying login after challenge...")
        cl.login(USERNAME, PASSWORD)
        print("LOGIN SUCCESSFUL!")
    except Exception as e5:
        print(f"Error after code: {type(e5).__name__}: {e5}")
        sys.exit(1)

except Exception as e:
    print(f"LOGIN FAILED: {type(e).__name__}: {e}")
    sys.exit(1)

# Show account info
try:
    info = cl.account_info()
    print()
    print(f"  Username: @{info.username}")
    print(f"  Full name: {info.full_name}")
    print(f"  Followers: {info.follower_count}")
    print(f"  Following: {info.following_count}")
    print()

    # Save session
    from pathlib import Path
    session_dir = Path("ig_sessions")
    session_dir.mkdir(exist_ok=True)
    session_file = session_dir / f"{USERNAME}_session.json"
    cl.dump_settings(session_file)
    print(f"Session saved to {session_file}")
except Exception as e:
    print(f"Could not get account info: {e}")
