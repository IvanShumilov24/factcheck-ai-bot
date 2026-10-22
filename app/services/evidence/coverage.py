from collections.abc import Sequence

from app.domain.claims import Claim, ClaimScope
from app.domain.coverage import EvidenceCoverage
from app.domain.enums import EvidenceDirectness, EvidenceRelation
from app.domain.schemas import Evidence


class EvidenceCoverageService:
    def calculate(self, claim: Claim, evidence: Sequence[Evidence]) -> EvidenceCoverage:
        usable = [item for item in evidence if item.usable]
        direct = [item for item in usable if item.directness is EvidenceDirectness.DIRECT]
        indirect = [item for item in usable if item.directness is EvidenceDirectness.INDIRECT]
        not_relevant = [
            item for item in usable if item.directness is EvidenceDirectness.NOT_RELEVANT
        ]
        background = [item for item in usable if item.directness is EvidenceDirectness.BACKGROUND]
        relevant = [
            item
            for item in usable
            if item.directness
            not in {EvidenceDirectness.NOT_RELEVANT, EvidenceDirectness.BACKGROUND}
        ]
        uncovered = self._uncovered_components(claim, relevant)
        scope_mismatch = any(item.scope.value != "CLAIM_SPECIFIC" for item in relevant)
        if not relevant:
            level = "нет покрытия"
        elif direct and not uncovered and not scope_mismatch:
            level = "хорошее"
        elif direct or indirect:
            level = "ограниченное"
        else:
            level = "нет покрытия"
        return EvidenceCoverage(
            level=level,
            direct_count=len(direct),
            indirect_count=len(indirect),
            not_relevant_count=len(not_relevant),
            background_count=len(background),
            supporting_count=sum(item.relation is EvidenceRelation.SUPPORTS for item in relevant),
            contradicting_count=sum(
                item.relation is EvidenceRelation.CONTRADICTS for item in relevant
            ),
            independent_source_count=len({item.source_id for item in relevant}),
            uncovered_components=uncovered,
            scope_mismatch=scope_mismatch,
        )

    @staticmethod
    def _uncovered_components(claim: Claim, evidence: Sequence[Evidence]) -> list[str]:
        if claim.scope is not ClaimScope.COMPOSITE or not claim.components:
            return []
        searchable = " ".join(
            f"{item.evidence_summary} {item.evidence_text}".casefold() for item in evidence
        )
        return [
            component for component in claim.components if component.casefold() not in searchable
        ]

    @staticmethod
    def needs_second_pass(coverage: EvidenceCoverage) -> bool:
        return (
            coverage.direct_count == 0
            or coverage.level == "нет покрытия"
            or coverage.not_relevant_count > coverage.direct_count + coverage.indirect_count
            or bool(coverage.uncovered_components)
        )
