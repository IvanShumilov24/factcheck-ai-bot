from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class SearchStrategy(StrEnum):
    PRIMARY = "PRIMARY"
    NEUTRAL = "NEUTRAL"
    COUNTER = "COUNTER"
    AUTHORITATIVE = "AUTHORITATIVE"
    RESEARCH = "RESEARCH"
    GENERAL = "GENERAL"
    EVIDENCE_RESEARCH = "EVIDENCE_RESEARCH"
    GUIDELINES = "GUIDELINES"
    SAFETY_RISKS = "SAFETY_RISKS"


class SourceType(StrEnum):
    OFFICIAL = "OFFICIAL"
    GUIDELINE = "GUIDELINE"
    SYSTEMATIC_REVIEW = "SYSTEMATIC_REVIEW"
    META_ANALYSIS = "META_ANALYSIS"
    PEER_REVIEWED_STUDY = "PEER_REVIEWED_STUDY"
    MEDICAL_PUBLICATION = "MEDICAL_PUBLICATION"
    NEWS = "NEWS"
    BLOG = "BLOG"
    COMMERCIAL = "COMMERCIAL"
    SOCIAL = "SOCIAL"
    UNKNOWN = "UNKNOWN"


class AuthorityLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class SearchQuery(BaseModel):
    query: str = Field(min_length=3)
    claim_id: str
    purpose: SearchStrategy
    priority: int = Field(ge=1, le=10)


class SearchQueryResponse(BaseModel):
    queries: list[SearchQuery] = Field(default_factory=list)


class SearchResult(BaseModel):
    title: str
    url: HttpUrl
    snippet: str = ""
    domain: str
    published_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    relevance_score: float = Field(default=0.5, ge=0, le=1)
