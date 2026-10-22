import asyncio
import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import cast

from pydantic import ValidationError

from app.config import Settings
from app.core.exceptions import ApplicationError
from app.domain.claims import Claim
from app.domain.content import ExtractedContent
from app.domain.schemas import Source
from app.repositories.checks import ClaimCheckResult
from app.services.claims.service import ClaimExtractionService
from app.services.content import ContentPreparationService
from app.services.evidence import EvidenceAnalysisService, EvidenceExtractionService, VerdictService
from app.services.evidence.coverage import EvidenceCoverageService
from app.services.report import format_claim_report
from app.services.search.service import SourceSearchService

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[str], Awaitable[None]]


class FactCheckPipeline:
    def __init__(
        self,
        content_service: ContentPreparationService,
        claim_service: ClaimExtractionService,
        search_service: SourceSearchService,
        evidence_service: EvidenceExtractionService,
        analysis_service: EvidenceAnalysisService,
        verdict_service: VerdictService,
        config: Settings | None = None,
    ) -> None:
        self._content = content_service
        self._claims = claim_service
        self._search = search_service
        self._evidence = evidence_service
        self._analysis = analysis_service
        self._verdict = verdict_service
        self._config = config or Settings()
        self._coverage = EvidenceCoverageService()

    async def run(
        self, content: ExtractedContent, progress: ProgressCallback
    ) -> tuple[list[ClaimCheckResult], list[str], int]:
        started = perf_counter()
        await progress("🔎 Анализирую утверждения…")
        claims = await self._claims.extract(content)
        if not claims:
            return [], [], 0
        results: list[ClaimCheckResult] = []
        reports: list[str] = []
        source_count = 0
        last_error: ApplicationError | None = None

        async def process_claim(
            index: int, claim: Claim
        ) -> tuple[ClaimCheckResult | None, str | None, int, ApplicationError | None]:
            claim_started = perf_counter()
            claim_source_count = 0
            await progress(f"📚 Ищу источники ({index}/{len(claims)})…")
            try:
                sources = await self._search.search_claim(claim)
                claim_source_count += len(sources)
                await progress(f"🧾 Проверяю доказательства ({index}/{len(claims)})…")
                evidence = await self._evidence.extract(claim, sources)
                coverage = self._coverage.calculate(claim, evidence)
                if self._config.search_max_passes > 1 and self._coverage.needs_second_pass(
                    coverage
                ):
                    extra_sources = await self._search.search_claim(claim, pass_number=2)
                    sources = self._merge_sources(sources, extra_sources)
                    claim_source_count += len(extra_sources)
                    evidence = await self._evidence.extract(claim, sources)
                    coverage = self._coverage.calculate(claim, evidence)
                    logger.info(
                        "evidence_second_pass claim_id=%s coverage=%s direct=%d indirect=%d",
                        claim.claim_id,
                        coverage.level,
                        coverage.direct_count,
                        coverage.indirect_count,
                    )
                analysis = await self._analysis.analyze(claim, evidence, sources)
                await progress(f"🧠 Формирую результат ({index}/{len(claims)})…")
                verdict = self._verdict.build(
                    claim.source_reference or claim.claim_id, evidence, analysis, sources, claim
                )
                result = ClaimCheckResult(
                    claim=claim,
                    sources=sources,
                    evidence=evidence,
                    analysis=analysis,
                    verdict=verdict,
                )
                report = format_claim_report(claim.text, verdict, evidence, sources)
                logger.info(
                    "evidence_coverage claim_id=%s level=%s direct=%d indirect=%d "
                    "not_relevant=%d contradictions=%d independent_sources=%d",
                    claim.claim_id,
                    coverage.level,
                    coverage.direct_count,
                    coverage.indirect_count,
                    coverage.not_relevant_count,
                    coverage.contradicting_count,
                    coverage.independent_source_count,
                )
                logger.info(
                    "pipeline_claim_finished claim_id=%s duration_ms=%.0f",
                    claim.claim_id,
                    (perf_counter() - claim_started) * 1000,
                )
                return result, report, claim_source_count, None
            except (ValidationError, ApplicationError) as exc:
                logger.warning(
                    "pipeline_claim_failed claim_id=%s error=%s", claim.claim_id, type(exc).__name__
                )
                logger.info(
                    "pipeline_claim_finished claim_id=%s duration_ms=%.0f",
                    claim.claim_id,
                    (perf_counter() - claim_started) * 1000,
                )
                return None, None, 0, exc if isinstance(exc, ApplicationError) else None

        parallelism = max(1, self._config.claim_parallelism)
        semaphore = asyncio.Semaphore(parallelism)

        async def bounded_process(
            index: int, claim: Claim
        ) -> tuple[ClaimCheckResult | None, str | None, int, ApplicationError | None]:
            async with semaphore:
                return await process_claim(index, claim)

        processed = await asyncio.gather(
            *(bounded_process(index, claim) for index, claim in enumerate(claims, start=1))
        )
        for result, report, count, error in processed:
            source_count += count
            if result is not None and report is not None:
                results.append(result)
                reports.append(report)
            if error is not None:
                last_error = error
        logger.info(
            "pipeline_finished claims=%d sources=%d duration_ms=%.0f",
            len(results),
            source_count,
            (perf_counter() - started) * 1000,
        )
        if not results and last_error is not None:
            raise last_error
        return results, reports, source_count

    @staticmethod
    def _merge_sources(first: list[Source], second: list[Source]) -> list[Source]:
        merged: dict[str, Source] = {item.source_id: item for item in first}
        for source in second:
            current = merged.get(source.source_id)
            if current is None:
                merged[source.source_id] = source
                continue
            merged[source.source_id] = current.model_copy(
                update={
                    "search_queries": list(
                        dict.fromkeys(current.search_queries + source.search_queries)
                    ),
                    "metadata": {
                        **current.metadata,
                        "query_purposes": list(
                            dict.fromkeys(
                                cast(list[str], current.metadata.get("query_purposes", []))
                                + cast(list[str], source.metadata.get("query_purposes", []))
                            )
                        ),
                    },
                }
            )
        return list(merged.values())
