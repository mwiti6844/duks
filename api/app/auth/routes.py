"""Auth routes: login (issue JWT) and me. The Next.js BFF stores the JWT in an
HTTP-only cookie and forwards it as a Bearer token."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.dto import UserDTO
from ..db.engine import get_session
from ..db.repositories import get_user_by_username
from ..db.seed import verify_password
from .deps import get_current_user
from .jwt import create_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: UserDTO


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest, request: Request, db: Session = Depends(get_session)
) -> LoginResponse:
    user = get_user_by_username(db, body.username.strip().lower())
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    token = create_token(
        request.app.state.settings.jwt_secret, user_id=user.id, username=user.username
    )
    return LoginResponse(token=token, user=UserDTO.model_validate(user))


@router.get("/me", response_model=UserDTO)
def me(user: UserDTO = Depends(get_current_user)) -> UserDTO:
    return user
