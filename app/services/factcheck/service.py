from collections.abc import Sequence

from pydantic import HttpUrl, TypeAdapter

from app.domain.content import ContentInput, ContentType
from app.domain.enums import Verdict as VerdictStatus
from app.domain.schemas import CheckRequest, FactCheckResult
from app.repositories.checks import ClaimCheckResult
from app.services.content import ContentPreparationService
from app.services.pipeline import FactCheckPipeline
from app.services.ports import FactCheckService as FactCheckServicePort


class BasicFactCheckService(FactCheckServicePort):
    """Compatibility adapter around the production fact-checking pipeline."""

    def __init__(
        self, pipeline: FactCheckPipeline, content_service: ContentPreparationService
    ) -> None:
        self._pipeline = pipeline
        self._content_service = content_service

    async def check(self, request: CheckRequest) -> Sequence[FactCheckResult]:
        content = ContentInput(
            source_type=ContentType(request.input_type.upper()),
            text=request.content if request.input_type == "text" else None,
            url=(
                TypeAdapter(HttpUrl).validate_python(request.content)
                if request.input_type == "url"
                else None
            ),
        )
        prepared = await self._content_service.prepare(content)
        results, _, _ = await self._pipeline.run(prepared, _ignore_progress)
        return [_to_fact_check_result(result) for result in results]


async def _ignore_progress(_: str) -> None:
    return None


def _to_fact_check_result(result: ClaimCheckResult) -> FactCheckResult:
    verdict = result.verdict
    explanation = " ".join(
        part
        for part in (verdict.supported_summary, verdict.unresolved_summary, verdict.detailed_reason)
        if part
    )
    return FactCheckResult(
        claim=result.claim,
        verdict=VerdictStatus(verdict.status),
        confidence=round(verdict.confidence * 100),
        explanation=explanation,
        evidence=list(result.evidence),
    )
