"""Durable, owner-scoped conversation thread APIs."""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import repositories as repo
from ..db.dto import UserDTO
from ..db.engine import get_session

router = APIRouter(prefix="/api/threads", tags=["threads"])


class CreateThreadRequest(BaseModel):
    title: str | None = Field(default=None, max_length=100)


class UpdateThreadRequest(BaseModel):
    title: str | None = Field(default=None, max_length=100)
    archived: bool | None = None


def _thread_payload(thread) -> dict:
    payload = thread.model_dump(mode="json")
    payload["context"] = json.loads(payload.pop("context_json") or "{}")
    return payload


def _hydrated_messages(db: Session, messages: list, user_id: str) -> list[dict]:
    """Refresh mutable action state while retaining the original UI snapshot."""
    output = []
    for message in messages:
        payload = message.model_dump(mode="json")
        for block in payload["content"]:
            if block.get("type") != "component":
                continue
            props = block.get("props", {})
            if block.get("component_type") == "bid_confirm_modal":
                signed = props.get("signed_proposal", {})
                proposal_id = signed.get("proposal_id")
                bid = repo.get_bid_by_proposal(db, proposal_id) if proposal_id else None
                if bid and bid.user_id == user_id:
                    props["action_status"] = "confirmed"
                    props["receipt"] = bid.model_dump(mode="json")
                elif int(signed.get("expires_at", 0) or 0) < int(time.time()):
                    props["action_status"] = "expired"
            elif block.get("component_type") == "listing_summary":
                draft_id = props.get("draft_id")
                revision = int(props.get("revision", 0) or 0)
                mutation = (
                    repo.get_listing_mutation(db, draft_id, revision)
                    if draft_id and revision else None
                )
                if mutation and mutation.owner_id == user_id:
                    props["action_status"] = "published"
                    props["receipt"] = {
                        "listing_id": mutation.listing_id,
                        "created": False,
                        "operation": mutation.operation,
                    }
        output.append(payload)
    return output


@router.post("", status_code=status.HTTP_201_CREATED)
def create_thread(
    body: CreateThreadRequest,
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    return _thread_payload(repo.create_conversation_thread(
        db, user_id=user.id, title=body.title
    ))


@router.get("")
def list_threads(
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    items, next_cursor = repo.list_conversation_threads(
        db, user_id=user.id, limit=limit, offset=cursor
    )
    return {
        "items": [_thread_payload(item) for item in items],
        "next_cursor": next_cursor,
    }


@router.get("/{thread_id}")
def get_thread(
    thread_id: str,
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    thread = repo.get_conversation_thread(db, thread_id=thread_id, user_id=user.id)
    if thread is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    messages = repo.list_conversation_messages(
        db, thread_id=thread_id, user_id=user.id
    ) or []
    return {
        **_thread_payload(thread),
        "messages": _hydrated_messages(db, messages, user.id),
    }


@router.patch("/{thread_id}")
def update_thread(
    thread_id: str,
    body: UpdateThreadRequest,
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    thread = repo.update_conversation_thread(
        db,
        thread_id=thread_id,
        user_id=user.id,
        title=body.title,
        title_locked=True if body.title is not None else None,
        status=("archived" if body.archived else "active")
        if body.archived is not None else None,
    )
    if thread is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return _thread_payload(thread)


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_thread(
    thread_id: str,
    user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    if not repo.delete_conversation_thread(db, thread_id=thread_id, user_id=user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return None
