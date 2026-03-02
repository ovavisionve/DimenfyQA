import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.client import Client
from app.schemas.client import ClientCreate, ClientRead, ClientUpdate

router = APIRouter()


@router.post("/", response_model=ClientRead, status_code=201)
async def create_client(data: ClientCreate, db: AsyncSession = Depends(get_db)):
    client = Client(
        name=data.name,
        business_type=data.business_type,
        ig_accounts=data.ig_accounts,
        settings=data.settings,
    )
    db.add(client)
    await db.flush()
    await db.refresh(client)
    return client


@router.get("/", response_model=list[ClientRead])
async def list_clients(
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Client)
    if is_active is not None:
        query = query.where(Client.is_active == is_active)
    query = query.order_by(Client.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{client_id}", response_model=ClientRead)
async def get_client(client_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.patch("/{client_id}", response_model=ClientRead)
async def update_client(
    client_id: uuid.UUID,
    data: ClientUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(client, field, value)

    await db.flush()
    await db.refresh(client)
    return client


@router.delete("/{client_id}", status_code=204)
async def delete_client(client_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Soft delete: deactivate instead of removing
    client.is_active = False
    await db.flush()
