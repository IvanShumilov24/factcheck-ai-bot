from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.domain.content import ContentType
from app.domain.enums import ClaimType


class Checkability(StrEnum):
    CHECKABLE = "CHECKABLE"
    PARTIALLY_CHECKABLE = "PARTIALLY_CHECKABLE"
    NOT_CHECKABLE = "NOT_CHECKABLE"


class Importance(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ClaimScope(StrEnum):
    GENERAL = "GENERAL"
    NARROW = "NARROW"
    COMPOSITE = "COMPOSITE"
    COMPARATIVE = "COMPARATIVE"
    UNKNOWN = "UNKNOWN"


class ClaimCategory(StrEnum):
    """Reasoning category used to choose evidence and safety rules."""

    FACTUAL = "FACTUAL"
    CAUSAL = "CAUSAL"
    SAFETY = "SAFETY"
    TRANSMISSION = "TRANSMISSION"
    TREATMENT = "TREATMENT"
    PREVENTION = "PREVENTION"
    NUTRITION = "NUTRITION"
    RISK = "RISK"
    RECOMMENDATION_REQUEST = "RECOMMENDATION_REQUEST"
    COMPOUND = "COMPOUND"
    UNKNOWN = "UNKNOWN"


class ClaimExtractionCandidate(BaseModel):
    """Strict structured response item returned by an LLM provider."""

    text: str = Field(min_length=1)
    normalized_text: str = Field(min_length=1)
    claim_type: ClaimType
    context_before: str = ""
    context_after: str = ""
    checkability: Checkability
    importance: Importance
    confidence: float = Field(ge=0, le=1)
    scope: ClaimScope = ClaimScope.UNKNOWN
    components: list[str] = Field(default_factory=list)
    category: ClaimCategory = ClaimCategory.UNKNOWN


class ClaimExtractionResponse(BaseModel):
    claims: list[ClaimExtractionCandidate] = Field(default_factory=list)


class Claim(BaseModel):
    """A standalone unit that can later be checked against sources."""

    claim_id: str = ""
    text: str = Field(min_length=1)
    normalized_text: str = ""
    claim_type: ClaimType
    context_before: str = ""
    context_after: str = ""
    checkability: Checkability = Checkability.CHECKABLE
    importance: Importance = Importance.MEDIUM
    confidence: float = Field(default=0, ge=0, le=1)
    scope: ClaimScope = ClaimScope.UNKNOWN
    components: list[str] = Field(default_factory=list)
    category: ClaimCategory = ClaimCategory.UNKNOWN
    source_type: ContentType = ContentType.TEXT
    source_reference: str = ""
    source_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
