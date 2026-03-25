import hashlib
import hmac
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AuditLog, User, UserRole

logger = logging.getLogger(__name__)

# JWT-like token using HMAC-SHA256 (no external dependency needed)
_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", secrets.token_hex(32))
_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))  # 8 hours
_REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

# Bcrypt-like password hashing using hashlib (no external dep)
_HASH_ITERATIONS = 260_000
_HASH_ALGORITHM = "sha256"


def _hash_password(password: str) -> str:
    """Hash password with PBKDF2-HMAC-SHA256."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac(_HASH_ALGORITHM, password.encode(), salt, _HASH_ITERATIONS)
    return f"{salt.hex()}:{key.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored hash."""
    try:
        salt_hex, key_hex = stored_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
        actual_key = hashlib.pbkdf2_hmac(_HASH_ALGORITHM, password.encode(), salt, _HASH_ITERATIONS)
        return hmac.compare_digest(expected_key, actual_key)
    except (ValueError, AttributeError):
        return False


def _create_token(user_id: str, email: str, role: str, expires_minutes: int) -> str:
    """Create a simple signed token: base64(payload):signature."""
    import base64
    import json

    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": (datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)).isoformat(),
        "jti": secrets.token_hex(8),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode().rstrip("=")
    signature = hmac.new(_SECRET_KEY.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def decode_token(token: str) -> Optional[dict]:
    """Decode and verify a token. Returns payload dict or None."""
    import base64
    import json

    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None

        payload_b64, signature = parts
        # Re-pad base64
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        expected_sig = hmac.new(_SECRET_KEY.encode(), payload_bytes, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            return None

        payload = json.loads(payload_bytes)

        # Check expiration
        exp = datetime.fromisoformat(payload["exp"])
        if datetime.now(timezone.utc) > exp:
            return None

        return payload
    except Exception:
        return None


async def register_user(
    db: AsyncSession, email: str, password: str, full_name: str, role: str = UserRole.VIEWER
) -> User:
    """Register a new user."""
    # Check if email exists
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise ValueError("Email already registered")

    user = User(
        email=email.lower().strip(),
        password_hash=_hash_password(password),
        full_name=full_name.strip(),
        role=role,
    )
    db.add(user)
    await db.flush()

    logger.info("User registered: %s (%s)", email, role)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    """Authenticate user by email/password. Returns user or None."""
    result = await db.execute(select(User).where(User.email == email.lower().strip()))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        return None

    if not _verify_password(password, user.password_hash):
        return None

    # Update last login
    await db.execute(
        update(User).where(User.id == user.id).values(last_login_at=datetime.now(timezone.utc))
    )

    return user


def create_access_token(user: User) -> str:
    return _create_token(str(user.id), user.email, user.role, _ACCESS_TOKEN_EXPIRE_MINUTES)


def create_refresh_token(user: User) -> str:
    return _create_token(str(user.id), user.email, user.role, _REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60)


async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    return result.scalar_one_or_none()


async def log_audit(
    db: AsyncSession,
    action: str,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """Record an audit log entry."""
    entry = AuditLog(
        user_id=uuid.UUID(user_id) if user_id else None,
        user_email=user_email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)


async def list_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())


async def update_user_role(db: AsyncSession, user_id: str, new_role: str) -> Optional[User]:
    if new_role not in (UserRole.ADMIN, UserRole.MANAGER, UserRole.VIEWER):
        raise ValueError(f"Invalid role: {new_role}")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        return None

    user.role = new_role
    await db.flush()
    return user


async def update_user_permissions(db: AsyncSession, user_id: str, permissions: dict) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        return None

    user.permissions = permissions
    await db.flush()
    return user
