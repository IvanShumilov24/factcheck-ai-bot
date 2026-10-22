from pydantic import BaseModel, Field

from app.domain.enums import Verdict as VerdictStatus


class Verdict(BaseModel):
    """A conservative system conclusion; confidence is confidence in the conclusion."""

    claim_id: str
    status: VerdictStatus
    confidence: float = Field(ge=0, le=1)
    short_reason: str
    detailed_reason: str
    supported_summary: str = ""
    unresolved_summary: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
