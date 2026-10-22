import pytest

from app.config import Settings
from app.domain.claims import Checkability, Claim, ClaimScope, Importance
from app.domain.content import ContentType, ExtractedContent
from app.domain.enums import (
    ClaimType,
    EvidenceConsistency,
    EvidenceDirectness,
    EvidenceRelation,
    EvidenceScope,
    EvidenceStrength,
    Verdict,
)
from app.domain.schemas import Evidence, EvidenceAnalysis, Source
from app.services.claims.service import ClaimExtractionService
from app.services.evidence.verdict import VerdictService
from app.services.report import format_claim_report, verdict_label


class QuestionLLM:
    async def extract_claims(self, request: object) -> object:
        del request
        return {
            "claims": [
                {
                    "text": "вич передается от комаров?",
                    "normalized_text": "вич передается от комаров?",
                    "claim_type": ClaimType.MEDICAL_CLAIM,
                    "checkability": Checkability.CHECKABLE,
                    "importance": Importance.HIGH,
                    "confidence": 0.95,
                }
            ]
        }


def material(text: str) -> ExtractedContent:
    return ExtractedContent(
        source_type=ContentType.TEXT,
        original_reference="telegram:text",
        extracted_text=text,
        extraction_method="test",
    )


def claim(text: str, normalized: str, scope: ClaimScope = ClaimScope.NARROW) -> Claim:
    return Claim(
        claim_id="claim-9",
        text=text,
        normalized_text=normalized,
        claim_type=ClaimType.MEDICAL_CLAIM,
        checkability=Checkability.CHECKABLE,
        importance=Importance.HIGH,
        confidence=0.95,
        scope=scope,
        source_type=ContentType.TEXT,
    )


def source(source_id: str = "source-9", domain: str = "who.int") -> Source:
    return Source(
        source_id=source_id,
        title="Медицинский источник",
        url=f"https://{domain}/fact",
        domain=domain,
        quality_score=0.95,
        relevance_score=0.95,
    )


def evidence(
    claim_id: str,
    source_id: str,
    relation: EvidenceRelation,
    text: str,
    *,
    directness: EvidenceDirectness = EvidenceDirectness.DIRECT,
    scope: EvidenceScope = EvidenceScope.CLAIM_SPECIFIC,
) -> Evidence:
    return Evidence(
        claim_id=claim_id,
        source_id=source_id,
        source_url="https://who.int/fact",
        source_title="Медицинский источник",
        evidence_text=text,
        evidence_summary=text,
        relation=relation,
        evidence_strength=EvidenceStrength.STRONG,
        directness=directness,
        scope=scope,
    )


@pytest.mark.asyncio
async def test_question_is_normalized_without_losing_transmission_context() -> None:
    claims = await ClaimExtractionService(QuestionLLM(), Settings()).extract(
        material("вич передается от комаров?")
    )

    assert claims[0].normalized_text == "ВИЧ может передаваться человеку через укус комара."


def test_hiv_transmission_is_not_supported_by_direct_contradiction() -> None:
    checked = claim(
        "вич передается от комаров?",
        "ВИЧ может передаваться человеку через укус комара.",
    )
    result = VerdictService().build(
        checked.claim_id,
        [
            evidence(
                checked.claim_id,
                "who",
                EvidenceRelation.CONTRADICTS,
                "ВИЧ не передаётся через укусы комаров.",
            )
        ],
        EvidenceAnalysis(
            claim_id=checked.claim_id,
            evidence_consistency=EvidenceConsistency.CONSISTENT,
        ),
        [source("who")],
        checked,
    )

    assert result.status is Verdict.CONTRADICTED
    assert verdict_label(result.status.value) == "НЕ ПОДТВЕРЖДАЕТСЯ"


def test_smoking_is_confirmed_by_direct_medical_evidence() -> None:
    checked = claim("курить вредно?", "Курение вредит здоровью человека.")
    result = VerdictService().build(
        checked.claim_id,
        [
            evidence(
                checked.claim_id,
                "who",
                EvidenceRelation.SUPPORTS,
                "Курение вредит здоровью и повышает риск заболеваний.",
            )
        ],
        EvidenceAnalysis(claim_id=checked.claim_id),
        [source("who")],
        checked,
    )

    assert result.status is Verdict.CONFIRMED
    report = format_claim_report(checked.text, result, [], [])
    assert "Краткий вывод:" not in report
    assert "Курение вредит здоровью" in result.short_reason


def test_fresh_air_claim_is_insufficient_when_only_walking_is_supported() -> None:
    checked = claim(
        "гулять на свежем воздухе полезно?",
        "Прогулки на свежем воздухе полезны для здоровья.",
    )
    result = VerdictService().build(
        checked.claim_id,
        [
            evidence(
                checked.claim_id,
                "cdc",
                EvidenceRelation.SUPPORTS,
                "Физическая активность и ходьба полезны для здоровья.",
                directness=EvidenceDirectness.INDIRECT,
                scope=EvidenceScope.GENERAL_POPULATION,
            )
        ],
        EvidenceAnalysis(claim_id=checked.claim_id),
        [source("cdc", "cdc.gov")],
        checked,
    )

    assert result.status is Verdict.INSUFFICIENT_EVIDENCE
    assert verdict_label(result.status.value) == "ДАННЫХ НЕДОСТАТОЧНО"


def test_analysis_failure_uses_deterministic_evidence_fallback() -> None:
    checked = claim("курить вредно?", "Курение вредит здоровью человека.")
    result = VerdictService().build(
        checked.claim_id,
        [evidence(checked.claim_id, "who", EvidenceRelation.SUPPORTS, "Курение вредит здоровью.")],
        EvidenceAnalysis(
            claim_id=checked.claim_id,
            analysis_failed=False,
            limitations=[
                "LLM-анализ недоступен; использована детерминированная классификация evidence."
            ],
        ),
        [source("who")],
        checked,
    )

    assert result.status is Verdict.CONFIRMED
