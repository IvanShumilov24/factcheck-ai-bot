import asyncio
import re
from collections.abc import Iterable

from pydantic import ValidationError

from app.config import Settings
from app.core.exceptions import LLMError, LLMResponseError
from app.domain.claims import Claim
from app.domain.enums import (
    ContentStatus,
    EvidenceDirectness,
    EvidenceRelation,
    EvidenceScope,
)
from app.domain.schemas import Evidence, Source
from app.services.evidence.prompts import build_evidence_request
from app.services.ports import LLMProvider


class EvidenceExtractionService:
    def __init__(self, provider: LLMProvider, config: Settings) -> None:
        self._provider = provider
        self._config = config

    async def extract(self, claim: Claim, sources: Iterable[Source]) -> list[Evidence]:
        eligible_sources = [
            source
            for source in sources
            if source.content_status is ContentStatus.CONTENT_EXTRACTED and source.excerpt.strip()
        ]
        semaphore = asyncio.Semaphore(max(1, self._config.evidence_parallelism))

        async def extract_source(source: Source) -> list[Evidence]:
            return await self._extract_source(claim, source, semaphore)

        batches = await asyncio.gather(*(extract_source(source) for source in eligible_sources))
        evidence = [item for batch in batches for item in batch]
        unique: list[Evidence] = []
        for item in evidence:
            if not self._is_duplicate(unique, item):
                unique.append(item)
        return unique

    async def _extract_source(
        self, claim: Claim, source: Source, semaphore: asyncio.Semaphore
    ) -> list[Evidence]:
        evidence: list[Evidence] = []
        for chunk in self._chunks(source.excerpt.strip()):
            try:
                async with semaphore:
                    response = await self._provider.extract_evidence(
                        build_evidence_request(
                            claim.source_reference or claim.claim_id,
                            claim.normalized_text or claim.text,
                            source.source_id or str(source.url),
                            source.title,
                            str(source.url),
                            source.source_type.value,
                            source.quality_score,
                            source.relevance_score,
                            chunk,
                        )
                    )
                for item in response.evidence:
                    directness, scope, limitations = self._apply_scope_guard(
                        claim.normalized_text or claim.text,
                        chunk,
                        item.directness,
                        item.scope,
                        item.limitations,
                    )
                    relation, limitations = self._apply_relation_guard(
                        claim.normalized_text or claim.text,
                        chunk,
                        item.evidence_summary,
                        item.relation,
                        limitations,
                    )
                    candidate = Evidence(
                        claim_id=claim.source_reference or claim.claim_id,
                        source_id=source.source_id or str(source.url),
                        source_url=source.url,
                        source_title=source.title,
                        evidence_text=item.evidence_text,
                        evidence_summary=item.evidence_summary,
                        relation=relation,
                        evidence_strength=item.evidence_strength,
                        directness=directness,
                        scope=scope,
                        usable=item.usable,
                        limitations=limitations,
                    )
                    if candidate.evidence_text and not self._is_duplicate(evidence, candidate):
                        evidence.append(candidate)
            except (LLMError, LLMResponseError, ValidationError, TypeError, KeyError):
                continue
        return evidence

    @staticmethod
    def _apply_relation_guard(
        claim_text: str,
        source_text: str,
        summary: str,
        relation: EvidenceRelation,
        limitations: list[str],
    ) -> tuple[EvidenceRelation, list[str]]:
        """Correct an LLM polarity error when a source explicitly denies transmission."""
        claim_key = claim_text.casefold()
        evidence_key = f"{source_text} {summary}".casefold()
        transmission_claim = any(
            marker in claim_key for marker in ("переда", "зараз", "transmi", "infection")
        ) and any(marker in claim_key for marker in ("вич", "hiv"))
        transmission_target = any(
            marker in evidence_key
            for marker in ("комар", "mosquito", "членистоног", "arthropod", "insect")
        )
        explicit_denial = any(
            marker in evidence_key
            for marker in (
                "не переда",
                "не зараж",
                "не подтвержд",
                "опроверга",
                "не работает",
                "не может",
                "не способен",
                "не выжива",
                "не размнож",
                "отсутстви",
                "не найдено",
                "not transmitted",
                "does not transmit",
                "cannot transmit",
                "do not transmit",
                "no transmission",
                "not support",
                "does not support",
                "no evidence",
                "not found",
                "cannot survive",
                "cannot replicate",
            )
        )
        if transmission_claim and transmission_target and explicit_denial:
            if relation is EvidenceRelation.SUPPORTS:
                return (
                    EvidenceRelation.CONTRADICTS,
                    list(
                        dict.fromkeys(
                            [
                                *limitations,
                                "Источник содержит явное отрицание передачи ВИЧ через этот путь.",
                            ]
                        )
                    ),
                )
        return relation, limitations

    def _chunks(self, text: str) -> list[str]:
        bounded = text[: self._config.max_evidence_text]
        size = self._config.evidence_chunk_size
        overlap = min(self._config.evidence_chunk_overlap, max(0, size - 1))
        chunks: list[str] = []
        start = 0
        while start < len(bounded) and len(chunks) < self._config.max_evidence_chunks:
            end = min(start + size, len(bounded))
            chunks.append(bounded[start:end])
            if end == len(bounded):
                break
            start = end - overlap
        return chunks

    @staticmethod
    def _is_duplicate(existing: list[Evidence], candidate: Evidence) -> bool:
        key = re.sub(r"\W+", " ", candidate.evidence_text.casefold()).strip()
        return any(
            key == re.sub(r"\W+", " ", item.evidence_text.casefold()).strip()
            and candidate.source_id == item.source_id
            for item in existing
        )

    @staticmethod
    def _apply_scope_guard(
        claim_text: str,
        source_text: str,
        directness: EvidenceDirectness,
        scope: EvidenceScope,
        limitations: list[str],
    ) -> tuple[EvidenceDirectness, EvidenceScope, list[str]]:
        """Prevent an excerpt from being treated as direct when key context is absent."""
        claim_key = claim_text.casefold()
        source_key = source_text.casefold()
        broad_alcohol_terms = ("alcohol", "alcoholic beverage", "алкогол", "спиртное")
        claim_mentions_broad_exposure = any(term in claim_key for term in broad_alcohol_terms)
        source_mentions_broad_exposure = any(term in source_key for term in broad_alcohol_terms)
        if source_mentions_broad_exposure and not claim_mentions_broad_exposure:
            return (
                EvidenceDirectness.INDIRECT,
                EvidenceScope.GENERAL_ALCOHOL,
                list(
                    dict.fromkeys(
                        [
                            *limitations,
                            ("Источник рассматривает алкоголь в целом, а не объект утверждения."),
                        ]
                    )
                ),
            )
        context_groups = (
            (
                ("на свежем воздухе", "на улице", "outdoor", "fresh air"),
                "контекст открытого воздуха",
            ),
            (("пассивн", "passive smoking"), "пассивное воздействие"),
            (("для детей", "дети", "children", "adolescen"), "возрастную группу детей"),
            (("для взрослых", "взросл", "adults"), "возрастную группу взрослых"),
            (("беремен", "pregnan"), "беременность"),
        )
        for markers, context_name in context_groups:
            claim_has_context = any(marker in claim_key for marker in markers)
            source_has_context = any(marker in source_key for marker in markers)
            if (
                claim_has_context
                and not source_has_context
                and directness is EvidenceDirectness.DIRECT
            ):
                return (
                    EvidenceDirectness.INDIRECT,
                    EvidenceScope.GENERAL_POPULATION,
                    list(
                        dict.fromkeys(
                            [
                                *limitations,
                                (
                                    f"Фрагмент не рассматривает {context_name}; "
                                    "связь с утверждением косвенная."
                                ),
                            ]
                        )
                    ),
                )
        return directness, scope, limitations
