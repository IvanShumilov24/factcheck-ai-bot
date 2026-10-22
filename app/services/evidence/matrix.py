from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.claims import Claim
from app.domain.enums import (
    EvidenceDirectness,
    EvidenceRelation,
    EvidenceScope,
    EvidenceStrength,
)
from app.domain.schemas import Evidence, Source


@dataclass(frozen=True)
class EvidenceMatrixRow:
    """A normalized, source-aware evidence row used by deterministic verdict rules."""

    evidence: Evidence
    source_quality: float
    relevance: float
    scope_match: bool
    population_match: bool
    outcome_match: bool
    exposure_match: bool
    independence_group: str

    @property
    def usable(self) -> bool:
        return self.evidence.usable and self.evidence.relation is not EvidenceRelation.NEUTRAL

    @property
    def direct(self) -> bool:
        return self.evidence.directness is EvidenceDirectness.DIRECT and self.scope_match

    @property
    def strong_enough(self) -> bool:
        return self.evidence.evidence_strength in {
            EvidenceStrength.STRONG,
            EvidenceStrength.MODERATE,
        }


class EvidenceMatrixService:
    def build(
        self, claim: Claim | None, evidence: Sequence[Evidence], sources: Sequence[Source]
    ) -> list[EvidenceMatrixRow]:
        source_by_id = {source.source_id: source for source in sources}
        rows: list[EvidenceMatrixRow] = []
        seen: set[tuple[str, str]] = set()
        for item in evidence:
            source = source_by_id.get(item.source_id)
            source_key = item.source_id or str(item.source_url)
            key = (source_key, " ".join(item.evidence_text.casefold().split()))
            if key in seen:
                continue
            seen.add(key)
            scope_match = item.directness is EvidenceDirectness.DIRECT and item.scope not in {
                EvidenceScope.GENERAL_ALCOHOL,
            }
            if (
                claim is not None
                and claim.scope.value == "NARROW"
                and item.scope is EvidenceScope.GENERAL_POPULATION
            ):
                scope_match = False
            rows.append(
                EvidenceMatrixRow(
                    evidence=item,
                    source_quality=source.quality_score if source else 0.0,
                    relevance=source.relevance_score if source else 0.0,
                    scope_match=scope_match,
                    population_match=item.scope is not EvidenceScope.UNKNOWN,
                    outcome_match=item.directness is not EvidenceDirectness.NOT_RELEVANT,
                    exposure_match=item.scope is not EvidenceScope.GENERAL_ALCOHOL,
                    independence_group=(source.domain if source else source_key),
                )
            )
        return rows
