from collections.abc import Sequence

from app.domain.claims import Claim, ClaimScope
from app.domain.enums import (
    ContentStatus,
    EvidenceConsistency,
    EvidenceDirectness,
    EvidenceRelation,
)
from app.domain.enums import Verdict as VerdictStatus
from app.domain.schemas import Evidence, EvidenceAnalysis, Source
from app.domain.verdict import Verdict
from app.services.evidence.matrix import EvidenceMatrixRow, EvidenceMatrixService
from app.services.evidence.safety import MedicalSafetyValidator


class VerdictService:
    """Converts weighted evidence analysis into a conservative user-facing verdict."""

    def build(
        self,
        claim_id: str,
        evidence: Sequence[Evidence],
        analysis: EvidenceAnalysis,
        sources: Sequence[Source],
        claim: Claim | None = None,
    ) -> Verdict:
        rows = EvidenceMatrixService().build(claim, evidence, sources)
        usable_rows = [
            row
            for row in rows
            if row.evidence.usable
            and row.evidence.relation is not EvidenceRelation.NEUTRAL
            and row.evidence.directness
            not in {EvidenceDirectness.NOT_RELEVANT, EvidenceDirectness.BACKGROUND}
        ]
        usable = [row.evidence for row in usable_rows]
        relevant = list(usable)
        supporting_rows = [
            row for row in usable_rows if row.evidence.relation is EvidenceRelation.SUPPORTS
        ]
        contradicting_rows = [
            row for row in usable_rows if row.evidence.relation is EvidenceRelation.CONTRADICTS
        ]
        direct_support = [row.evidence for row in supporting_rows if row.direct]
        direct_contradicting = [row.evidence for row in contradicting_rows if row.direct]
        strong_support = self._has_quality_support([row for row in supporting_rows if row.direct])
        strong_contradiction = self._has_quality_support(
            [row for row in contradicting_rows if row.direct]
        )
        if not usable or not relevant:
            status = VerdictStatus.INSUFFICIENT_EVIDENCE
        elif strong_support and strong_contradiction:
            status = VerdictStatus.CONFLICTING_EVIDENCE
        elif strong_contradiction:
            status = VerdictStatus.CONTRADICTED
        elif strong_support:
            status = VerdictStatus.CONFIRMED
        elif claim is not None and claim.scope is ClaimScope.COMPOSITE and direct_support:
            status = VerdictStatus.PARTIALLY_CONFIRMED
        elif direct_contradicting:
            status = VerdictStatus.NOT_SUPPORTED
        else:
            status = VerdictStatus.INSUFFICIENT_EVIDENCE
        relevant_ids = [self._evidence_id(item) for item in relevant]
        limitations = list(
            dict.fromkeys([*analysis.limitations, *self._availability_limits(sources)])
        )
        candidate = Verdict(
            claim_id=claim_id,
            status=status,
            confidence=self._confidence(status, analysis, relevant),
            short_reason=self._short_reason(status, relevant),
            detailed_reason=self._detailed_reason(status, analysis, relevant),
            supported_summary=self._supported_summary(status, relevant),
            unresolved_summary=self._unresolved_summary(status, relevant, claim),
            evidence_ids=relevant_ids,
            source_ids=list(dict.fromkeys(item.source_id for item in relevant)),
            limitations=limitations,
        )
        return MedicalSafetyValidator().validate(candidate, claim, rows, analysis, sources)

    @staticmethod
    def _availability_limits(sources: Sequence[Source]) -> list[str]:
        return [
            f"Источник найден, но его содержимое недоступно для анализа: {source.title}."
            for source in sources
            if source.content_status is not ContentStatus.CONTENT_EXTRACTED
        ]

    @staticmethod
    def _supported_summary(status: VerdictStatus, evidence: Sequence[Evidence]) -> str:
        supporting = [item for item in evidence if item.relation is EvidenceRelation.SUPPORTS]
        if status is VerdictStatus.INSUFFICIENT_EVIDENCE and not supporting:
            return "Найден только общий или недостаточный контекст; подтверждение не получено."
        if supporting and all(
            item.directness is EvidenceDirectness.INDIRECT for item in supporting
        ):
            summary = next(
                (item.evidence_summary for item in supporting if item.evidence_summary),
                "найдена косвенная связь с утверждением",
            )
            return f"Косвенно поддерживается: {summary}"
        if supporting:
            return "Найдено подтверждение части или основного смысла утверждения."
        return "Поддерживающих данных не найдено."

    @staticmethod
    def _unresolved_summary(
        status: VerdictStatus, evidence: Sequence[Evidence], claim: Claim | None
    ) -> str:
        if claim is not None and claim.scope is ClaimScope.COMPOSITE:
            return "Не все самостоятельные части составного утверждения подтверждены отдельно."
        if any(item.directness is EvidenceDirectness.INDIRECT for item in evidence):
            return "Прямой ответ на всю исходную формулировку найденными фрагментами не установлен."
        if status is VerdictStatus.INSUFFICIENT_EVIDENCE:
            return "Данных недостаточно, чтобы сделать обоснованный вывод по исходной формулировке."
        return "Дополнительные эффекты и условия, не рассмотренные источниками, не установлены."

    @staticmethod
    def _has_quality_support(items: Sequence[EvidenceMatrixRow]) -> bool:
        return any(
            item.source_quality >= 0.75 and item.relevance >= 0.5 and item.strong_enough
            for item in items
        )

    @staticmethod
    def _evidence_id(item: Evidence) -> str:
        return f"{item.source_id}:{hash(item.evidence_text)}"

    @staticmethod
    def _confidence(
        status: VerdictStatus, analysis: EvidenceAnalysis, evidence: Sequence[Evidence]
    ) -> float:
        if not evidence:
            return 0.2
        base = {
            VerdictStatus.CONFIRMED: 0.9,
            VerdictStatus.CONTRADICTED: 0.9,
            VerdictStatus.CONFLICTING_EVIDENCE: 0.7,
            VerdictStatus.PARTIALLY_CONFIRMED: 0.65,
            VerdictStatus.NOT_SUPPORTED: 0.55,
            VerdictStatus.INSUFFICIENT_EVIDENCE: 0.3,
        }[status]
        if analysis.evidence_consistency is EvidenceConsistency.INSUFFICIENT:
            base -= 0.15
        if all(item.directness is not EvidenceDirectness.DIRECT for item in evidence):
            base = min(base, 0.45)
        return max(0.0, min(1.0, base))

    @staticmethod
    def _short_reason(status: VerdictStatus, evidence: Sequence[Evidence]) -> str:
        summary = next(
            (item.evidence_summary.strip() for item in evidence if item.evidence_summary.strip()),
            "",
        )
        if status is VerdictStatus.CONFIRMED and summary:
            return f"Доступные медицинские данные подтверждают утверждение: {summary}"
        if status in {VerdictStatus.NOT_SUPPORTED, VerdictStatus.CONTRADICTED} and summary:
            return f"Доступные медицинские данные не подтверждают утверждение: {summary}"
        return {
            VerdictStatus.CONFIRMED: "Утверждение подтверждается качественными прямыми данными.",
            VerdictStatus.PARTIALLY_CONFIRMED: "Подтверждена только часть составного утверждения.",
            VerdictStatus.NOT_SUPPORTED: "Утверждение не подтверждается доступными данными.",
            VerdictStatus.CONTRADICTED: "Доступные прямые данные противоречат утверждению.",
            VerdictStatus.INSUFFICIENT_EVIDENCE: (
                "Найденные данные не дают достаточного прямого ответа на исходную формулировку."
            ),
            VerdictStatus.CONFLICTING_EVIDENCE: (
                "Качественные данные дают противоречивые результаты."
            ),
        }[status]

    @classmethod
    def _detailed_reason(
        cls, status: VerdictStatus, analysis: EvidenceAnalysis, evidence: Sequence[Evidence]
    ) -> str:
        direct = sum(item.directness is EvidenceDirectness.DIRECT for item in evidence)
        indirect = len(evidence) - direct
        reason = f"Использовано доказательств: {len(evidence)}. "
        reason += f"Прямых: {direct}, косвенных: {indirect}."
        if analysis.conflict_detected:
            reason += " Зафиксирован конфликт между источниками."
        if analysis.limitations:
            reason += " Ограничения анализа перечислены ниже."
        return reason
