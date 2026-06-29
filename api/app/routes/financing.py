"""POST /api/financing — recompute the financing plan (used by the interactive
calculator when the user drags deposit/term sliders)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from ..agents import tools
from ..auth.deps import get_current_user
from ..db.dto import UserDTO

router = APIRouter(prefix="/api", tags=["financing"])


class FinancingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    principal_kes: int = Field(gt=0)
    deposit_kes: int | None = None
    term_months: int = Field(default=48, ge=6, le=72)


@router.post("/financing")
def compute(
    body: FinancingRequest,
    _user: UserDTO = Depends(get_current_user),
) -> dict:
    return tools.compute_financing(
        principal_kes=body.principal_kes,
        deposit_kes=body.deposit_kes,
        term_months=body.term_months,
        annual_rate_pct=tools.DEFAULT_ANNUAL_RATE_PCT,
    )
