import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ClientCreate(BaseModel):
    name: str
    business_type: Optional[str] = None
    ig_accounts: list = []
    settings: dict = {}


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    business_type: Optional[str] = None
    ig_accounts: Optional[list] = None
    settings: Optional[dict] = None
    is_active: Optional[bool] = None


class ClientRead(BaseModel):
    id: uuid.UUID
    name: str
    business_type: Optional[str]
    ig_accounts: list
    settings: dict
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
