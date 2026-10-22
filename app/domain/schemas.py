from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.domain.claims import Claim
from app.domain.enums import (
    ContentStatus,
    EvidenceConsistency,
    EvidenceDirectness,
    EvidenceRelation,
    EvidenceScope,
    EvidenceStrength,
    Verdict,
)
from app.domain.search import AuthorityLevel, SourceType


class User(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: int | None = None
    telegram_id: int
    created_at: datetime | None = None


class CheckRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    input_type: str = Field(pattern="^(text|url|image)$")
    content: str = Field(min_length=1)
    user_id: int | None = None


class Source(BaseModel):
    source_id: str = ""
    title: str
    url: HttpUrl
    domain: str
    source_type: SourceType = SourceType.UNKNOWN
    authority_level: AuthorityLevel = AuthorityLevel.UNKNOWN
    search_queries: list[str] = Field(default_factory=list)
    excerpt: str = ""
    snippet: str = ""
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    relevance_score: float = Field(default=0.0, ge=0, le=1)
    quality_score: float = Field(default=0.0, ge=0, le=1)
    credibility_score: float = Field(default=0.0, ge=0, le=1)
    metadata: dict[str, object] = Field(default_factory=dict)
    content_status: ContentStatus = ContentStatus.CONTENT_EXTRACTED
    fetch_error: str | None = None


class Evidence(BaseModel):
    claim_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_url: HttpUrl
    source_title: str
    evidence_text: str = ""
    evidence_summary: str = ""
    relation: EvidenceRelation
    evidence_strength: EvidenceStrength = EvidenceStrength.UNKNOWN
    directness: EvidenceDirectness = EvidenceDirectness.DIRECT
    scope: EvidenceScope = EvidenceScope.UNKNOWN
    usable: bool = True
    limitations: list[str] = Field(default_factory=list)


class EvidenceAnalysis(BaseModel):
    claim_id: str
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    neutral_evidence: list[str] = Field(default_factory=list)
    overall_evidence_strength: EvidenceStrength = EvidenceStrength.UNKNOWN
    evidence_consistency: EvidenceConsistency = EvidenceConsistency.INSUFFICIENT
    limitations: list[str] = Field(default_factory=list)
    conflict_detected: bool = False
    analysis_failed: bool = False


class VerdictResult(BaseModel):
    claim_id: str
    status: Verdict
    confidence: float = Field(ge=0, le=1)
    short_reason: str
    detailed_reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class FactCheckResult(BaseModel):
    claim: Claim
    verdict: Verdict
    confidence: int = Field(ge=0, le=100)
    explanation: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
