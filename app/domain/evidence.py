from pydantic import BaseModel, Field

from app.domain.enums import (
    EvidenceConsistency,
    EvidenceDirectness,
    EvidenceRelation,
    EvidenceScope,
    EvidenceStrength,
    Verdict,
)


class EvidenceCandidate(BaseModel):
    evidence_text: str = ""
    evidence_summary: str = ""
    relation: EvidenceRelation
    evidence_strength: EvidenceStrength = EvidenceStrength.UNKNOWN
    directness: EvidenceDirectness = EvidenceDirectness.NOT_RELEVANT
    scope: EvidenceScope = EvidenceScope.UNKNOWN
    usable: bool = True
    limitations: list[str] = Field(default_factory=list)


class EvidenceExtractionResponse(BaseModel):
    evidence: list[EvidenceCandidate] = Field(default_factory=list)


class EvidenceAnalysisResponse(BaseModel):
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    neutral_evidence: list[str] = Field(default_factory=list)
    overall_evidence_strength: EvidenceStrength = EvidenceStrength.UNKNOWN
    evidence_consistency: EvidenceConsistency = EvidenceConsistency.INSUFFICIENT
    limitations: list[str] = Field(default_factory=list)
    conflict_detected: bool = False
    analysis_failed: bool = False


class VerdictCandidate(BaseModel):
    status: Verdict
    confidence: float = Field(ge=0, le=1)
    short_reason: str
    detailed_reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
