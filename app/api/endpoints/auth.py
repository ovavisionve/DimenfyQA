import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.auth import (
    PermissionsUpdate,
    TokenRefresh,
    TokenResponse,
    UserLogin,
    UserRead,
    UserRegister,
    UserUpdate,
)
from app.services.auth_service import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_user_by_id,
    list_users,
    log_audit,
    register_user,
    update_user_permissions,
    update_user_role,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    """Extract and validate the current user from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = auth_header[7:]
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = await get_user_by_id(db, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user


def require_role(*roles):
    """Dependency factory: require user to have one of the specified roles."""
    async def _check(request: Request, db: AsyncSession = Depends(get_db)):
        user = await get_current_user(request, db)
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return _check


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: UserRegister, request: Request, db: AsyncSession = Depends(get_db)):
    """Register a new user. First user becomes admin."""
    try:
        # Check if this is the first user — make them admin
        existing = await list_users(db)
        role = "admin" if len(existing) == 0 else "viewer"

        user = await register_user(db, body.email, body.password, body.full_name, role=role)
        access_token = create_access_token(user)
        refresh_token = create_refresh_token(user)

        await log_audit(
            db, action="user.register", user_id=str(user.id), user_email=user.email,
            ip_address=request.client.host if request.client else None,
        )
        await db.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserRead.model_validate(user),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return tokens."""
    user = await authenticate_user(db, body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user)

    await log_audit(
        db, action="user.login", user_id=str(user.id), user_email=user.email,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserRead.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: TokenRefresh, db: AsyncSession = Depends(get_db)):
    """Get new access token using refresh token."""
    payload = decode_token(body.refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = await get_user_by_id(db, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return TokenResponse(
        access_token=create_access_token(user),
        refresh_token=create_refresh_token(user),
        user=UserRead.model_validate(user),
    )


@router.get("/me", response_model=UserRead)
async def get_me(request: Request, db: AsyncSession = Depends(get_db)):
    """Get current user profile."""
    user = await get_current_user(request, db)
    return UserRead.model_validate(user)


@router.get("/users", response_model=list[UserRead])
async def get_users(request: Request, db: AsyncSession = Depends(get_db)):
    """List all users (admin only)."""
    user = await get_current_user(request, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    users = await list_users(db)
    return [UserRead.model_validate(u) for u in users]


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: str, body: UserUpdate, request: Request, db: AsyncSession = Depends(get_db)
):
    """Update user (admin only)."""
    current = await get_current_user(request, db)
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    target = await get_user_by_id(db, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if body.role is not None:
        target = await update_user_role(db, user_id, body.role)
    if body.permissions is not None:
        target = await update_user_permissions(db, user_id, body.permissions)
    if body.full_name is not None:
        target.full_name = body.full_name
    if body.is_active is not None:
        target.is_active = body.is_active

    await log_audit(
        db, action="user.update", user_id=str(current.id), user_email=current.email,
        resource_type="user", resource_id=user_id,
        details=body.model_dump(exclude_none=True),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()

    return UserRead.model_validate(target)
