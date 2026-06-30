"""Durable owner-scoped listing draft, review and Cloudinary media endpoints."""
from __future__ import annotations

import hashlib
import json
import time
import httpx
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import listingsign
from ..auth.deps import get_current_user
from ..db import repositories as repo
from ..db.dto import UserDTO
from ..db.engine import get_session
from ..listing_pricing import price_guidance
from ..listing_validation import blocking_issues, completion, validate_listing

router = APIRouter(prefix="/api", tags=["listing-drafts"])


class DraftPatch(BaseModel):
    fields: dict = Field(default_factory=dict)


class ImageRegistration(BaseModel):
    public_id: str = Field(min_length=1, max_length=300)
    secure_url: str = Field(min_length=10, max_length=1_000)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    format: str
    bytes: int = Field(gt=0, le=10 * 1024 * 1024)


class DescriptionRequest(BaseModel):
    facts: str = Field(min_length=10, max_length=2_000)


class ImageOrder(BaseModel):
    image_ids: list[str] = Field(min_length=1, max_length=12)


def _payload(db: Session, row) -> dict:
    data = repo.listing_draft_payload(db, row)
    percent, missing = completion(data["fields"])
    return {**data, "progress": percent, "missing_fields": missing}


@router.get("/listing-drafts/active")
def active_draft(
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict | None:
    row = repo.latest_listing_draft(db, user.id)
    return _payload(db, row) if row else None


@router.patch("/listing-drafts/{draft_id}")
def patch_draft(
    draft_id: str,
    body: DraftPatch,
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    row = repo.get_listing_draft(db, draft_id, user.id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Draft not found")
    current = repo.listing_draft_payload(db, row)
    fields = {**current["fields"], **{
        key: value for key, value in body.fields.items()
        if key in listingsign.LISTING_FIELDS and value not in (None, "")
    }}
    issues = validate_listing(fields, image_count=len(current["images"]))
    guidance = price_guidance(db, fields)
    new_status = "ready_to_publish" if not blocking_issues(issues) else "collecting"
    row = repo.save_listing_draft(
        db, draft_id=row.id, owner_id=user.id, fields=fields, status=new_status,
        validation=issues, guidance=guidance, mode=row.mode,
        target_listing_id=row.target_listing_id, increment_revision=True,
    )
    data = _payload(db, row)
    return data


@router.post("/listing-drafts/{draft_id}/review")
def review_draft(
    draft_id: str,
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
    request: Request = None,
) -> dict:
    row = repo.get_listing_draft(db, draft_id, user.id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Draft not found")
    data = _payload(db, row)
    issues = validate_listing(data["fields"], image_count=len(data["images"]))
    if blocking_issues(issues):
        raise HTTPException(status.HTTP_409_CONFLICT, {"issues": issues})
    if row.status != "ready_to_publish" or json.loads(row.validation_json) != issues:
        row = repo.save_listing_draft(
            db, draft_id=row.id, owner_id=user.id, fields=data["fields"],
            status="ready_to_publish", validation=issues,
            guidance=price_guidance(db, data["fields"]), mode=row.mode,
            target_listing_id=row.target_listing_id,
        )
        data = _payload(db, row)
    signed = listingsign.make_signed_draft(
        request.app.state.settings.bid_signing_secret,
        listingsign.create_draft(
            owner_id=user.id, fields=data["fields"], draft_id=row.id,
            revision=row.revision, mode=row.mode,
            target_listing_id=row.target_listing_id,
            image_ids=[image["id"] for image in data["images"]],
        ),
    )
    return {**data, "signed_draft": signed}


@router.post("/listing-drafts/{draft_id}/description/polish")
def polish_description(
    draft_id: str,
    body: DescriptionRequest,
    request: Request,
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    if repo.get_listing_draft(db, draft_id, user.id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Draft not found")
    system = (
        "Rewrite the supplied vehicle facts into one concise marketplace description. "
        "Use only supplied facts. Do not invent condition, ownership, service history, "
        "features, guarantees, or mechanical claims."
    )
    polished = "".join(request.app.state.deps.llm.stream_text(
        system=system, user=body.facts, max_tokens=220
    )).strip()
    return {"original": body.facts, "polished": polished}


@router.post("/listings/{listing_id}/edit")
def start_edit(
    listing_id: str,
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    listing = repo.get_used_car(db, listing_id)
    if listing is None or listing.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    fields = {
        key: getattr(listing, key)
        for key in listingsign.LISTING_FIELDS
        if key != "image_url"
    }
    fields["image_url"] = listing.image_url
    draft_id = listingsign.new_draft_id()
    issues = validate_listing(fields, image_count=1 if listing.image_url else 0)
    row = repo.save_listing_draft(
        db, draft_id=draft_id, owner_id=user.id, fields=fields,
        status="ready_to_publish", validation=issues,
        guidance=price_guidance(db, fields), mode="edit",
        target_listing_id=listing.id,
    )
    return _payload(db, row)


@router.get("/media/cloudinary/signature")
def cloudinary_signature(
    request: Request,
    user: UserDTO = Depends(get_current_user),
) -> dict:
    settings = request.app.state.settings
    if not all((
        settings.cloudinary_cloud_name,
        settings.cloudinary_api_key,
        settings.cloudinary_api_secret,
    )):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Photo uploads are not configured")
    timestamp = int(time.time())
    folder = f"carduka/{user.id}"
    raw = f"folder={folder}&timestamp={timestamp}{settings.cloudinary_api_secret}"
    signature = hashlib.sha1(raw.encode()).hexdigest()
    return {
        "cloud_name": settings.cloudinary_cloud_name,
        "api_key": settings.cloudinary_api_key,
        "timestamp": timestamp,
        "folder": folder,
        "signature": signature,
    }


@router.post("/listing-drafts/{draft_id}/images")
def register_image(
    draft_id: str,
    body: ImageRegistration,
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    row = repo.get_listing_draft(db, draft_id, user.id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Draft not found")
    if len(repo.list_listing_images(db, draft_id, user.id)) >= 12:
        raise HTTPException(status.HTTP_409_CONFLICT, "A listing can have at most 12 photos")
    parsed = urlparse(body.secure_url)
    if parsed.scheme != "https" or parsed.netloc != "res.cloudinary.com":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Cloudinary URL")
    if body.format.lower() not in {"jpg", "jpeg", "png", "webp"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported photo format")
    expected_prefix = f"carduka/{user.id}/"
    if not body.public_id.startswith(expected_prefix):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Photo does not belong to this user")
    image = repo.add_listing_image(
        db, owner_id=user.id, draft_id=draft_id, public_id=body.public_id,
        secure_url=body.secure_url, width=body.width, height=body.height,
    )
    row.revision += 1
    fields = json.loads(row.fields_json)
    row.validation_json = json.dumps(validate_listing(
        fields, image_count=len(repo.list_listing_images(db, draft_id, user.id))
    ))
    db.commit()
    return repo.listing_image_payload(image)


@router.delete("/listing-drafts/{draft_id}/images/{image_id}")
def remove_image(
    draft_id: str,
    image_id: str,
    request: Request,
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    if repo.get_listing_draft(db, draft_id, user.id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Draft not found")
    image = repo.get_listing_image(db, image_id, user.id)
    if image is None or image.draft_id != draft_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    settings = request.app.state.settings
    if settings.cloudinary_cloud_name and settings.cloudinary_api_key \
            and settings.cloudinary_api_secret:
        timestamp = int(time.time())
        raw = f"public_id={image.cloudinary_public_id}&timestamp={timestamp}"
        signature = hashlib.sha1(f"{raw}{settings.cloudinary_api_secret}".encode()).hexdigest()
        try:
            httpx.post(
                f"https://api.cloudinary.com/v1_1/{settings.cloudinary_cloud_name}/image/destroy",
                data={
                    "public_id": image.cloudinary_public_id,
                    "timestamp": timestamp,
                    "api_key": settings.cloudinary_api_key,
                    "signature": signature,
                },
                timeout=10,
            )
        except httpx.HTTPError:
            pass  # metadata removal remains deterministic; Cloudinary cleanup can retry later.
    if not repo.delete_listing_image(db, image_id=image_id, owner_id=user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    row = repo.get_listing_draft(db, draft_id, user.id)
    row.revision += 1
    fields = json.loads(row.fields_json)
    row.validation_json = json.dumps(validate_listing(
        fields, image_count=len(repo.list_listing_images(db, draft_id, user.id))
    ))
    db.commit()
    return {"ok": True}


@router.put("/listing-drafts/{draft_id}/images/order")
def reorder_images(
    draft_id: str,
    body: ImageOrder,
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    row = repo.get_listing_draft(db, draft_id, user.id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Draft not found")
    images = repo.list_listing_images(db, draft_id, user.id)
    if set(body.image_ids) != {image.id for image in images}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Photo order does not match the draft")
    by_id = {image.id: image for image in images}
    for index, image_id in enumerate(body.image_ids):
        by_id[image_id].sort_order = index
    row.revision += 1
    db.commit()
    return {"images": [
        repo.listing_image_payload(by_id[image_id]) for image_id in body.image_ids
    ], "revision": row.revision}
