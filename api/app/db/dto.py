"""Pydantic DTOs returned at the repository boundary. ORM objects never escape the db layer."""
from __future__ import annotations

from datetime import datetime
from pydantic import Field

from pydantic import BaseModel, ConfigDict


class UserDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    full_name: str
    location: str
    profile_context: str | None = None


class UserMemoryDTO(BaseModel):
    user_id: str
    budget_kes: int | None = None
    preferred_makes: list[str] = Field(default_factory=list)
    preferred_body_types: list[str] = Field(default_factory=list)


class UsedCarDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    make: str
    model: str
    year: int
    price_kes: int
    mileage_km: int
    transmission: str
    fuel: str
    location: str
    condition: str
    body_type: str
    image_url: str
    description: str | None = None
    status: str
    sold_price_kes: int | None = None
    sold_at: datetime | None = None
    owner_id: str | None = None
    version: int = 1
    published_at: datetime | None = None
    updated_at: datetime | None = None


class AuctionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    make: str
    model: str
    year: int
    mileage_km: int
    transmission: str
    location: str
    image_url: str
    reserve_price_kes: int
    current_bid_kes: int
    min_increment_kes: int
    ends_at: datetime


class BidDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    proposal_id: str
    user_id: str
    auction_id: str
    amount_kes: int
    created_at: datetime


class FinancingDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    car_id: str
    principal_kes: int
    deposit_kes: int
    term_months: int
    annual_rate_pct: float
    monthly_payment_kes: int
    approved: bool
    created_at: datetime
