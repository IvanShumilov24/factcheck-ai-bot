from collections.abc import Sequence

from app.domain.claims import Claim, ClaimScope
from app.domain.enums import EvidenceRelation, Verdict
from app.domain.schemas import EvidenceAnalysis, Source
from app.domain.verdict import Verdict as VerdictResult
from app.services.evidence.matrix import EvidenceMatrixRow


class MedicalSafetyValidator:
    """Prevents a candidate verdict from exceeding the available evidence."""

    def validate(
        self,
        candidate: VerdictResult,
        claim: Claim | None,
        rows: Sequence[EvidenceMatrixRow],
        analysis: EvidenceAnalysis,
        sources: Sequence[Source],
    ) -> VerdictResult:
        usable = [row for row in rows if row.usable]
        direct_support = [
            row
            for row in usable
            if row.direct and row.evidence.relation is EvidenceRelation.SUPPORTS
        ]
        direct_contradiction = [
            row
            for row in usable
            if row.direct and row.evidence.relation is EvidenceRelation.CONTRADICTS
        ]
        limitations = list(candidate.limitations)
        status = candidate.status
        if not usable:
            status = Verdict.INSUFFICIENT_EVIDENCE
            limitations.append("Доступных релевантных доказательств недостаточно.")
        elif analysis.analysis_failed and status is Verdict.CONFIRMED:
            status = (
                Verdict.PARTIALLY_CONFIRMED
                if claim and claim.scope is ClaimScope.COMPOSITE
                else Verdict.INSUFFICIENT_EVIDENCE
            )
            limitations.append(
                "Анализ доказательств не завершён; сильный положительный вывод запрещён."
            )
        elif status is Verdict.CONFIRMED and not direct_support:
            status = (
                Verdict.PARTIALLY_CONFIRMED
                if claim and claim.scope is ClaimScope.COMPOSITE
                else Verdict.INSUFFICIENT_EVIDENCE
            )
            limitations.append("Для исходной формулировки нет достаточного прямого доказательства.")
        elif status is Verdict.CONTRADICTED and not direct_contradiction:
            status = Verdict.INSUFFICIENT_EVIDENCE
            limitations.append("Опровержение относится к более общему или иному контексту.")
        if (
            claim
            and claim.scope is not ClaimScope.COMPOSITE
            and status is Verdict.PARTIALLY_CONFIRMED
        ):
            if not direct_support and not direct_contradiction:
                status = Verdict.INSUFFICIENT_EVIDENCE
        if status is not candidate.status:
            return candidate.model_copy(
                update={
                    "status": status,
                    "confidence": min(candidate.confidence, 0.45),
                    "short_reason": self._reason(status),
                    "limitations": list(dict.fromkeys(limitations)),
                }
            )
        return candidate.model_copy(update={"limitations": list(dict.fromkeys(limitations))})

    @staticmethod
    def _reason(status: Verdict) -> str:
        return {
            Verdict.CONFIRMED: "Утверждение подтверждается качественными прямыми данными.",
            Verdict.PARTIALLY_CONFIRMED: "Подтверждена только часть составного утверждения.",
            Verdict.NOT_SUPPORTED: "Утверждение не подтверждается доступными данными.",
            Verdict.CONTRADICTED: "Доступные прямые данные противоречат утверждению.",
            Verdict.INSUFFICIENT_EVIDENCE: "Данных недостаточно для прямого вывода.",
            Verdict.CONFLICTING_EVIDENCE: "Качественные данные дают противоречивые результаты.",
        }[status]
