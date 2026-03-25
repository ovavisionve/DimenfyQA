from fastapi import APIRouter, UploadFile, File, Query, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import csv
import io
import uuid
from datetime import datetime, timezone

from app.database import get_db
from app.models.lead import Lead
from app.models.campaign import Campaign

router = APIRouter()


@router.post("/upload-csv")
async def upload_csv(
    file: UploadFile = File(...),
    campaign_id: uuid.UUID = Query(..., description="Campaign to import leads into"),
    db: AsyncSession = Depends(get_db),
):
    """Import leads from a CSV file into a campaign.

    CSV columns:
    - ig_username (required)
    - ig_full_name (optional)
    - biography (optional)
    - follower_count (optional)
    """
    # Validate file type
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    # Fetch campaign and validate it exists
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    client_id = campaign.client_id

    # Read and decode CSV content
    try:
        content = await file.read()
        text = content.decode("utf-8-sig")  # utf-8-sig handles BOM from Excel
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text))

    # Validate that ig_username column exists
    if not reader.fieldnames or "ig_username" not in reader.fieldnames:
        raise HTTPException(
            status_code=400,
            detail="CSV must contain an 'ig_username' column",
        )

    # Fetch existing usernames for this client to skip duplicates
    existing_result = await db.execute(
        select(Lead.ig_username).where(Lead.client_id == client_id)
    )
    existing_usernames = {row[0].lower() for row in existing_result.all()}

    imported_count = 0
    skipped_count = 0
    errors: list[dict] = []

    for row_num, row in enumerate(reader, start=2):  # start=2 because row 1 is header
        username = (row.get("ig_username") or "").strip().lstrip("@").lower()

        # Validate username present
        if not username:
            errors.append({"row": row_num, "error": "Missing ig_username"})
            continue

        # Skip duplicates
        if username in existing_usernames:
            skipped_count += 1
            continue

        # Parse optional follower_count
        follower_count = None
        raw_followers = (row.get("follower_count") or "").strip()
        if raw_followers:
            try:
                follower_count = int(raw_followers)
            except ValueError:
                errors.append({"row": row_num, "error": f"Invalid follower_count: {raw_followers}"})
                continue

        lead = Lead(
            id=uuid.uuid4(),
            campaign_id=campaign_id,
            client_id=client_id,
            ig_username=username,
            ig_full_name=(row.get("ig_full_name") or "").strip() or None,
            ig_bio=(row.get("biography") or "").strip() or None,
            ig_follower_count=follower_count,
            status="scraped",
            scraped_at=datetime.now(timezone.utc),
        )
        db.add(lead)
        existing_usernames.add(username)
        imported_count += 1

    # Flush to catch any DB-level constraint violations
    try:
        await db.flush()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    return {
        "imported_count": imported_count,
        "skipped_count": skipped_count,
        "errors": errors,
    }
