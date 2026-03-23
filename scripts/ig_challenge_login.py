"""
Instagram login with challenge (verification code) support.
Usage: python scripts/ig_challenge_login.py
"""
import sys
from instagrapi import Client


def challenge_code_handler(username, choice):
    """Called when Instagram sends a verification code."""
    code = input(f"Enter the verification code sent to you: ")
    return code


cl = Client()
cl.delay_range = [2, 5]
cl.challenge_code_handler = challenge_code_handler

USERNAME = "orlandodimenfy"
PASSWORD = "Apolo0501."

print(f"=== Instagram Login with Challenge Support ===")
print(f"Username: {USERNAME}")
print()
print("Attempting login...")

try:
    cl.login(USERNAME, PASSWORD)
    print()
    print("LOGIN SUCCESSFUL!")
    info = cl.account_info()
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
    print(f"LOGIN FAILED: {type(e).__name__}: {e}")
    sys.exit(1)
