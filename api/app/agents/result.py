"""AgentResult + generative-UI Component schemas with an allow-listed ComponentType enum.

Every component streamed to the client is validated against these Pydantic models.
Invalid payloads are dropped with an error trace, never streamed.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .actions import UIAction


class ComponentType(str, Enum):
    CAR_CARD = "car_card"
    CAR_CARD_LIST = "car_card_list"
    COMPARISON_TABLE = "comparison_table"
    FINANCING_CALCULATOR = "financing_calculator"
    AUCTION_COUNTDOWN = "auction_countdown"
    BID_CONFIRM_MODAL = "bid_confirm_modal"
    PRICE_VERDICT = "price_verdict"
    KNOWLEDGE_ANSWER = "knowledge_answer"
    LISTING_SUMMARY = "listing_summary"
    FOLLOW_UP_SUGGESTIONS = "follow_up_suggestions"


class Component(BaseModel):
    type: ComponentType
    props: dict[str, Any]


class _StrictProps(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CarProps(_StrictProps):
    id: str
    make: str
    model: str
    year: int = Field(ge=1900, le=2100)
    price_kes: int = Field(gt=0)
    mileage_km: int = Field(ge=0)
    transmission: str
    fuel: str
    location: str
    condition: str
    body_type: str
    image_url: str
    description: str | None = None


class CarCardListProps(_StrictProps):
    cars: list[CarProps]


class ComparisonTableProps(_StrictProps):
    cars: list[CarProps] = Field(min_length=2)


class FinancingCalculatorProps(_StrictProps):
    car: CarProps | None
    price_kes: int = Field(gt=0)
    deposit_kes: int = Field(ge=0)
    deposit_pct: float = Field(ge=0, le=100)
    financed_kes: int = Field(ge=0)
    term_months: int = Field(ge=1, le=120)
    annual_rate_pct: float = Field(ge=0, le=40)
    monthly_payment_kes: int = Field(ge=0)
    total_payable_kes: int = Field(ge=0)
    meets_min_deposit: bool
    min_deposit_kes: int = Field(ge=0)


class AuctionProps(_StrictProps):
    id: str
    make: str
    model: str
    year: int
    mileage_km: int = Field(ge=0)
    transmission: str
    location: str
    image_url: str
    current_bid_kes: int = Field(ge=0)
    min_increment_kes: int = Field(gt=0)
    min_next_bid_kes: int = Field(gt=0)
    ends_at: str


class AuctionCountdownProps(_StrictProps):
    auctions: list[AuctionProps]


class SignedProposalProps(_StrictProps):
    proposal_id: str
    user_id: str
    auction_id: str
    amount_kes: int = Field(gt=0)
    expires_at: int
    signature: str


class BidConfirmProps(_StrictProps):
    auction: AuctionProps
    amount_kes: int = Field(gt=0)
    meets_reserve: bool
    signed_proposal: SignedProposalProps


class SaleEvidence(_StrictProps):
    sale_id: str
    sold_price_kes: int = Field(gt=0)
    year: int
    mileage_km: int = Field(ge=0)


class PriceVerdictProps(_StrictProps):
    car: CarProps
    verdict: Literal["fair", "below_market", "above_market", "insufficient_data"]
    car_id: str
    asking_price_kes: int = Field(gt=0)
    comparable_median_kes: int | None = None
    comparable_low_kes: int | None = None
    comparable_high_kes: int | None = None
    delta_pct: float | None = None
    evidence: list[SaleEvidence]
    summary: str | None = None


class CitationProps(_StrictProps):
    source_id: str
    title: str
    score: float = Field(ge=-1, le=1)
    source_url: str | None = None


class KnowledgeAnswerProps(_StrictProps):
    answer: str = Field(min_length=1)
    citations: list[CitationProps] = Field(min_length=1)


class SignedListingDraftProps(_StrictProps):
    draft_id: str
    owner_id: str
    fields: dict[str, Any]
    expires_at: int
    signature: str


class ListingSummaryProps(_StrictProps):
    draft_id: str
    make: str
    model: str
    year: int = Field(ge=1900, le=2100)
    price_kes: int = Field(gt=0)
    mileage_km: int = Field(ge=0)
    transmission: str
    fuel: str
    condition: str
    body_type: str
    location: str
    image_url: str
    signed_draft: SignedListingDraftProps


class FollowUpSuggestionProps(_StrictProps):
    id: str
    label: str = Field(min_length=1, max_length=100)
    action: UIAction


class FollowUpSuggestionsProps(_StrictProps):
    suggestions: list[FollowUpSuggestionProps] = Field(min_length=1, max_length=4)


class Citation(BaseModel):
    source_id: str
    title: str
    score: float
    source_url: str | None = None


class TraceEntry(BaseModel):
    """Sanitized trace shown in the collapsible panel — no prompts / secrets / CoT."""
    kind: str  # "routing" | "tool" | "retrieval"
    label: str
    detail: dict[str, Any] = {}


class AgentResult(BaseModel):
    text: str = ""
    components: list[Component] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    trace: list[TraceEntry] = Field(default_factory=list)


_PROP_MODELS: dict[ComponentType, type[BaseModel]] = {
    ComponentType.CAR_CARD: CarProps,
    ComponentType.CAR_CARD_LIST: CarCardListProps,
    ComponentType.COMPARISON_TABLE: ComparisonTableProps,
    ComponentType.FINANCING_CALCULATOR: FinancingCalculatorProps,
    ComponentType.AUCTION_COUNTDOWN: AuctionCountdownProps,
    ComponentType.BID_CONFIRM_MODAL: BidConfirmProps,
    ComponentType.PRICE_VERDICT: PriceVerdictProps,
    ComponentType.KNOWLEDGE_ANSWER: KnowledgeAnswerProps,
    ComponentType.LISTING_SUMMARY: ListingSummaryProps,
    ComponentType.FOLLOW_UP_SUGGESTIONS: FollowUpSuggestionsProps,
}


def validate_component(type_: ComponentType, props: dict) -> Component | None:
    """Schema-gate a component. Returns None (caller drops + traces) on invalid props."""
    try:
        parsed = _PROP_MODELS[type_].model_validate(props)
        return Component(type=type_, props=parsed.model_dump(mode="json"))
    except ValidationError:
        return None


def validated_component(type_: str, props: dict) -> Component | None:
    """Validate both the allow-listed type and its exact props schema."""
    try:
        component_type = ComponentType(type_)
    except ValueError:
        return None
    return validate_component(component_type, props)
