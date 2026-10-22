from collections.abc import Sequence

from app.core.exceptions import LLMError, LLMResponseError
from app.domain.claims import Claim
from app.domain.enums import EvidenceConsistency, EvidenceRelation, EvidenceStrength
from app.domain.schemas import Evidence, EvidenceAnalysis, Source
from app.services.evidence.prompts import build_analysis_request
from app.services.ports import LLMProvider


class EvidenceAnalysisService:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def analyze(
        self, claim: Claim, evidence: Sequence[Evidence], sources: Sequence[Source]
    ) -> EvidenceAnalysis:
        request = build_analysis_request(
            claim.source_reference or claim.claim_id,
            claim.normalized_text or claim.text,
            [item.model_dump(mode="json") for item in evidence],
            [
                {
                    "source_id": source.source_id,
                    "source_type": source.source_type.value,
                    "quality_score": source.quality_score,
                    "relevance_score": source.relevance_score,
                }
                for source in sources
            ],
        )
        try:
            return await self._provider.analyze_evidence(request)
        except (LLMError, LLMResponseError):
            return self._deterministic_fallback(claim, evidence)

    @staticmethod
    def _deterministic_fallback(claim: Claim, evidence: Sequence[Evidence]) -> EvidenceAnalysis:
        usable = [item for item in evidence if item.usable]
        supporting = [item for item in usable if item.relation is EvidenceRelation.SUPPORTS]
        contradicting = [item for item in usable if item.relation is EvidenceRelation.CONTRADICTS]
        if supporting and contradicting:
            consistency = EvidenceConsistency.CONFLICTING
        elif supporting or contradicting:
            consistency = EvidenceConsistency.CONSISTENT
        else:
            consistency = EvidenceConsistency.INSUFFICIENT
        strengths = {item.evidence_strength for item in usable}
        if EvidenceStrength.STRONG in strengths:
            overall = EvidenceStrength.STRONG
        elif EvidenceStrength.MODERATE in strengths:
            overall = EvidenceStrength.MODERATE
        elif EvidenceStrength.WEAK in strengths:
            overall = EvidenceStrength.WEAK
        else:
            overall = EvidenceStrength.UNKNOWN
        return EvidenceAnalysis(
            claim_id=claim.source_reference or claim.claim_id,
            supporting_evidence=[item.evidence_summary for item in supporting],
            contradicting_evidence=[item.evidence_summary for item in contradicting],
            overall_evidence_strength=overall,
            evidence_consistency=consistency,
            limitations=[
                "LLM-анализ недоступен; использована детерминированная классификация evidence."
            ],
            analysis_failed=False,
        )
