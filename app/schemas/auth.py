import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator


class UserRegister(BaseModel):
    email: str
    password: str
    full_name: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserLogin(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserRead"


class TokenRefresh(BaseModel):
    refresh_token: str


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    permissions: dict
    last_login_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    permissions: Optional[dict] = None


class PermissionsUpdate(BaseModel):
    permissions: dict
