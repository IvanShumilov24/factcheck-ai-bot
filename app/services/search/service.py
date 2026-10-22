import asyncio
import logging
from collections.abc import Iterable
from typing import cast

from pydantic import ValidationError

from app.config import Settings
from app.core.exceptions import (
    ApplicationError,
    CaptchaDetectedError,
    EmptyContentError,
    LLMError,
    LLMResponseError,
    SearchError,
    UnsupportedContentError,
)
from app.domain.claims import Claim
from app.domain.content import ContentInput, ContentType
from app.domain.enums import ContentStatus
from app.domain.schemas import Source
from app.domain.search import SearchQuery, SearchQueryResponse, SearchResult, SearchStrategy
from app.services.extraction.url import UrlContentExtractor
from app.services.ports import LLMProvider, SearchProvider
from app.services.search.normalizer import SourceNormalizer
from app.services.search.prompts import build_query_request
from app.services.search.ranker import SourceRanker
from app.services.search.strategy import choose_strategies

logger = logging.getLogger(__name__)


class SearchQueryGenerator:
    def __init__(self, provider: LLMProvider, config: Settings | None = None) -> None:
        self._provider = provider
        self._config = config or Settings()

    async def generate(self, claim: Claim) -> list[SearchQuery]:
        strategies = choose_strategies(claim)
        try:
            response = await self._provider.generate_search_queries(
                build_query_request(claim, strategies)
            )
            queries = SearchQueryResponse.model_validate(response).queries
        except (AttributeError, TypeError, ValidationError, LLMError, LLMResponseError):
            queries = []
        return self._complete_query_set(claim, queries, strategies)

    def _complete_query_set(
        self,
        claim: Claim,
        queries: list[SearchQuery],
        strategies: list[SearchStrategy],
    ) -> list[SearchQuery]:
        by_purpose = {query.purpose: query for query in queries}
        transmission_claim = claim.category.value == "TRANSMISSION" or any(
            term in (claim.normalized_text or claim.text).casefold()
            for term in ("передав", "зараз", "transmi", "infection")
        )
        required_purposes = (
            {SearchStrategy.COUNTER, SearchStrategy.AUTHORITATIVE} if transmission_claim else set()
        )
        if len(queries) >= 2 and required_purposes.issubset(by_purpose):
            return sorted(queries, key=lambda item: item.priority)[
                : self._config.search_max_queries_per_claim
            ]
        claim_text = claim.text.strip()
        normalized_text = claim.normalized_text or claim.text
        fallback = {
            "PRIMARY": claim_text.strip(),
            "NEUTRAL": f"{claim_text} evidence health effects",
            "COUNTER": f"{normalized_text} not transmitted no evidence risks null findings",
            "AUTHORITATIVE": f"{normalized_text} WHO CDC official guidance",
            "RESEARCH": f"{normalized_text} systematic review meta-analysis study",
        }
        if transmission_claim:
            fallback["COUNTER"] = "ВИЧ не передаётся через укусы комаров CDC WHO"
            fallback["AUTHORITATIVE"] = "HIV transmission mosquito bites CDC WHO official"
        for priority, strategy in enumerate(strategies, start=1):
            if strategy in by_purpose or strategy.value not in fallback:
                continue
            by_purpose[strategy] = SearchQuery(
                query=fallback[strategy.value],
                claim_id=claim.source_reference or claim.claim_id,
                purpose=strategy,
                priority=priority,
            )
        return sorted(by_purpose.values(), key=lambda item: item.priority)[
            : self._config.search_max_queries_per_claim
        ]


class SourceSearchService:
    def __init__(
        self,
        query_generator: SearchQueryGenerator,
        provider: SearchProvider,
        config: Settings,
        normalizer: SourceNormalizer | None = None,
        ranker: SourceRanker | None = None,
        content_extractor: UrlContentExtractor | None = None,
    ) -> None:
        self._queries = query_generator
        self._provider = provider
        self._config = config
        self._normalizer = normalizer or SourceNormalizer()
        self._ranker = ranker or SourceRanker()
        self._content_extractor = content_extractor

    async def search_claim(self, claim: Claim, pass_number: int = 1) -> list[Source]:
        queries = await self._queries.generate(claim)
        if pass_number > 1:
            queries = [
                query
                for query in queries
                if query.purpose.value
                in {"COUNTER", "AUTHORITATIVE", "RESEARCH", "EVIDENCE_RESEARCH", "GUIDELINES"}
            ]
        normalized: list[Source] = []
        ordered_queries = sorted(queries, key=lambda item: item.priority)[
            : self._config.search_max_queries_per_claim
        ]
        early_stop_reason = "none"
        parallelism = max(1, self._config.search_parallelism)
        for start in range(0, len(ordered_queries), parallelism):
            batch = ordered_queries[start : start + parallelism]
            authoritative_index = next(
                (
                    index
                    for index, query in enumerate(batch)
                    if query.purpose.value == "AUTHORITATIVE"
                ),
                None,
            )
            if authoritative_index is not None:
                batch = batch[: authoritative_index + 1]
            results_by_query = await asyncio.gather(*(self._search_one(query) for query in batch))
            for query, results in zip(batch, results_by_query, strict=True):
                normalized.extend(
                    self._normalizer.normalize(item, query.query, query.purpose.value)
                    for item in results
                )
            current_candidates = self._deduplicate(normalized)
            if (
                any(query.purpose.value == "AUTHORITATIVE" for query in batch)
                and len(current_candidates) >= self._config.search_early_stop_min_sources
                and len({item.domain for item in current_candidates}) >= 2
            ):
                early_stop_reason = "sufficient_authoritative_candidate_pool"
                break
        deduplicated = self._deduplicate(normalized)
        ranked = self._ranker.rank(deduplicated)[: self._config.search_max_unique_sources]
        selected = self._select_sources(ranked)
        logger.info(
            "search_finished claim_id=%s pass=%d generated_queries=%d unique_sources=%d "
            "duplicates=%d domains=%d selected=%d",
            claim.claim_id,
            pass_number,
            len(queries),
            len(deduplicated),
            len(normalized) - len(deduplicated),
            len({item.domain for item in deduplicated}),
            len(selected),
        )
        if early_stop_reason != "none":
            logger.info(
                "search_early_stop claim_id=%s pass=%d reason=%s",
                claim.claim_id,
                pass_number,
                early_stop_reason,
            )
        return await self._enrich_top_sources(selected)

    async def _search_one(self, query: SearchQuery) -> list[SearchResult]:
        try:
            return await self._provider.search(
                query.query, limit=self._config.search_results_per_query
            )
        except SearchError:
            return []

    def _deduplicate(self, sources: Iterable[Source]) -> list[Source]:
        by_url: dict[str, Source] = {}
        by_document: dict[str, str] = {}
        for source in sources:
            key = self._normalizer.canonical_url(str(source.url))
            document_key = self._document_key(source)
            existing_key = by_document.get(document_key)
            if existing_key is not None and existing_key != key:
                current = by_url[existing_key]
                by_url[existing_key] = current.model_copy(
                    update={
                        "search_queries": list(
                            dict.fromkeys(current.search_queries + source.search_queries)
                        ),
                        "relevance_score": max(current.relevance_score, source.relevance_score),
                        "metadata": self._merge_metadata(current, source),
                    }
                )
                continue
            if key not in by_url:
                by_url[key] = source
                by_document[document_key] = key
                continue
            current = by_url[key]
            by_url[key] = current.model_copy(
                update={
                    "search_queries": list(
                        dict.fromkeys(current.search_queries + source.search_queries)
                    ),
                    "relevance_score": max(current.relevance_score, source.relevance_score),
                    "metadata": self._merge_metadata(current, source),
                }
            )
        return list(by_url.values())

    @staticmethod
    def _document_key(source: Source) -> str:
        title = " ".join(source.title.casefold().split())
        return f"{title[:240]}|{source.source_type.value}"

    def _select_sources(self, ranked: list[Source]) -> list[Source]:
        selected: list[Source] = []
        domain_counts: dict[str, int] = {}
        for source in ranked:
            count = domain_counts.get(source.domain, 0)
            if count >= self._config.search_max_sources_per_domain and source.quality_score < 0.9:
                continue
            selected.append(source)
            domain_counts[source.domain] = count + 1
            if len(selected) >= self._config.top_sources_per_claim:
                break
        return selected

    @staticmethod
    def _merge_metadata(current: Source, incoming: Source) -> dict[str, object]:
        purposes = cast(list[str], current.metadata.get("query_purposes", []))
        purposes = list(purposes)
        purposes.extend(cast(list[str], incoming.metadata.get("query_purposes", [])))
        return {**current.metadata, "query_purposes": list(dict.fromkeys(purposes))}

    async def _enrich_top_sources(self, sources: list[Source]) -> list[Source]:
        if self._content_extractor is None:
            return sources
        semaphore = asyncio.Semaphore(max(1, self._config.source_fetch_parallelism))

        async def enrich(source: Source) -> Source:
            async with semaphore:
                return await self._enrich_one_source(source)

        return list(await asyncio.gather(*(enrich(source) for source in sources)))

    async def _enrich_one_source(self, source: Source) -> Source:
        if self._content_extractor is None:
            return source
        try:
            content = await self._content_extractor.extract(
                ContentInput(source_type=ContentType.URL, url=source.url)
            )
        except CaptchaDetectedError as exc:
            return source.model_copy(
                update={"content_status": ContentStatus.CAPTCHA, "fetch_error": str(exc)}
            )
        except EmptyContentError as exc:
            return source.model_copy(
                update={"content_status": ContentStatus.EMPTY, "fetch_error": str(exc)}
            )
        except UnsupportedContentError as exc:
            return source.model_copy(
                update={"content_status": ContentStatus.UNSUPPORTED, "fetch_error": str(exc)}
            )
        except ApplicationError as exc:
            return source.model_copy(
                update={"content_status": ContentStatus.ERROR, "fetch_error": str(exc)}
            )
        return source.model_copy(
            update={
                "title": content.title or source.title,
                "excerpt": content.extracted_text[:4000],
                "content_status": ContentStatus.CONTENT_EXTRACTED,
                "fetch_error": None,
                "metadata": {
                    **source.metadata,
                    "content_extraction_method": content.extraction_method,
                },
            }
        )
