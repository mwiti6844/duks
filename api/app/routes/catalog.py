"""Catalog endpoints for hydration: cars, single car, auctions."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db.dto import AuctionDTO, UsedCarDTO, UserDTO
from ..db.engine import get_session
from ..db import repositories as repo

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/cars", response_model=list[UsedCarDTO])
def list_cars(
    make: str | None = None,
    model: str | None = None,
    max_price_kes: int | None = None,
    _user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[UsedCarDTO]:
    return repo.search_used_cars(db, make=make, model=model, max_price_kes=max_price_kes)


@router.get("/cars/{car_id}", response_model=UsedCarDTO | None)
def get_car(
    car_id: str,
    _user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> UsedCarDTO | None:
    return repo.get_used_car(db, car_id)


@router.get("/auctions", response_model=list[AuctionDTO])
def list_auctions(
    _user: UserDTO = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[AuctionDTO]:
    return repo.list_auctions(db)
