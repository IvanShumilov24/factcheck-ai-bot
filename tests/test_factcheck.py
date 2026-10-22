from app.domain.claims import Checkability, Claim, Importance
from app.domain.content import ContentType, ExtractedContent
from app.domain.enums import ClaimType, Verdict
from app.domain.schemas import CheckRequest, EvidenceAnalysis
from app.domain.verdict import Verdict as VerdictModel
from app.repositories.checks import ClaimCheckResult
from app.services.factcheck.service import BasicFactCheckService


class FakeContent:
    async def prepare(self, content):
        return ExtractedContent(
            source_type=content.source_type,
            original_reference="test",
            extracted_text=content.text or "",
            extraction_method="test",
        )


class FakePipeline:
    async def run(self, content, progress):
        await progress("ignored")
        claim = Claim(
            claim_id="claim-1",
            text=content.extracted_text,
            claim_type=ClaimType.MEDICAL_CLAIM,
            checkability=Checkability.CHECKABLE,
            importance=Importance.MEDIUM,
            source_type=ContentType.TEXT,
        )
        verdict = VerdictModel(
            claim_id="claim-1",
            status=Verdict.CONFIRMED,
            confidence=0.84,
            short_reason="Подтверждено.",
            detailed_reason="Есть прямые данные.",
        )
        return [
            ClaimCheckResult(
                claim=claim,
                sources=[],
                evidence=[],
                analysis=EvidenceAnalysis(claim_id="claim-1"),
                verdict=verdict,
            )
        ], ["report"], 0


async def test_factcheck_service_adapts_pipeline_result() -> None:
    service = BasicFactCheckService(FakePipeline(), FakeContent())

    results = await service.check(CheckRequest(input_type="text", content="Claim"))

    assert len(results) == 1
    assert results[0].claim.text == "Claim"
    assert results[0].verdict is Verdict.CONFIRMED
    assert results[0].confidence == 84
