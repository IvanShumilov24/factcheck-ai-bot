import pytest

from app.config import Settings
from app.core.exceptions import LLMError
from app.domain.claims import Checkability, Claim, ClaimScope, Importance
from app.domain.content import ContentType
from app.domain.enums import (
    ClaimType,
    EvidenceDirectness,
    EvidenceRelation,
    EvidenceScope,
    EvidenceStrength,
)
from app.domain.schemas import Evidence, Source
from app.domain.search import AuthorityLevel, SearchResult, SearchStrategy, SourceType
from app.services.evidence.coverage import EvidenceCoverageService
from app.services.search.service import SearchQueryGenerator, SourceSearchService


def make_claim(
    text: str = "Прогулки полезны",
    *,
    scope: ClaimScope = ClaimScope.NARROW,
    components: list[str] | None = None,
) -> Claim:
    return Claim(
        claim_id="claim-8",
        source_reference="claim-8",
        text=text,
        normalized_text=text.casefold(),
        claim_type=ClaimType.MEDICAL_CLAIM,
        checkability=Checkability.CHECKABLE,
        importance=Importance.HIGH,
        confidence=0.9,
        scope=scope,
        components=components or [],
        source_type=ContentType.TEXT,
    )


class FailingQueryProvider:
    async def generate_search_queries(self, request: object) -> object:
        del request
        raise LLMError("temporary failure")


class ExpandedQueryProvider:
    async def generate_search_queries(self, request: object) -> object:
        del request
        return {
            "queries": [
                {
                    "query": purpose.lower(),
                    "claim_id": "claim-8",
                    "purpose": purpose,
                    "priority": priority,
                }
                for priority, purpose in enumerate(
                    ["PRIMARY", "NEUTRAL", "COUNTER", "AUTHORITATIVE", "RESEARCH"], 1
                )
            ]
        }


class CountingSearchProvider:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        del limit
        self.queries.append(query)
        index = len(self.queries)
        return [
            SearchResult(
                title=f"Источник {index}",
                url=f"https://domain{index}.example/article",
                domain=f"domain{index}.example",
                snippet="relevant evidence",
            )
        ]


@pytest.mark.asyncio
async def test_query_expansion_has_bounded_directions() -> None:
    queries = await SearchQueryGenerator(
        FailingQueryProvider(), Settings(SEARCH_MAX_QUERIES_PER_CLAIM=5)
    ).generate(make_claim())

    assert len(queries) == 5
    assert [query.purpose for query in queries] == [
        SearchStrategy.PRIMARY,
        SearchStrategy.NEUTRAL,
        SearchStrategy.COUNTER,
        SearchStrategy.AUTHORITATIVE,
        SearchStrategy.RESEARCH,
    ]
    assert queries[0].query == "Прогулки полезны"


@pytest.mark.asyncio
async def test_search_early_stopping_is_bounded_and_logged_by_behavior() -> None:
    provider = CountingSearchProvider()
    config = Settings(
        SEARCH_MAX_QUERIES_PER_CLAIM=5,
        SEARCH_EARLY_STOP_MIN_SOURCES=4,
        TOP_SOURCES_PER_CLAIM=5,
    )
    service = SourceSearchService(
        SearchQueryGenerator(ExpandedQueryProvider(), config), provider, config
    )

    await service.search_claim(make_claim())

    assert provider.queries == ["primary", "neutral", "counter", "authoritative"]


def test_source_selection_keeps_domains_but_does_not_drop_authority() -> None:
    service = SourceSearchService.__new__(SourceSearchService)
    service._config = Settings(
        SEARCH_MAX_SOURCES_PER_DOMAIN=1,
        TOP_SOURCES_PER_CLAIM=3,
    )
    sources = [
        Source(
            source_id=str(index),
            title=f"Источник {index}",
            url=f"https://example.com/{index}",
            domain="example.com",
            source_type=SourceType.UNKNOWN,
            authority_level=AuthorityLevel.UNKNOWN,
            quality_score=0.3,
            relevance_score=0.9,
        )
        for index in range(3)
    ]
    sources.append(
        Source(
            source_id="official",
            title="Официальный источник",
            url="https://who.int/guideline",
            domain="who.int",
            source_type=SourceType.GUIDELINE,
            authority_level=AuthorityLevel.HIGH,
            quality_score=1.0,
            relevance_score=0.6,
        )
    )

    selected = service._select_sources(sources)

    assert "official" in {item.source_id for item in selected}
    assert len([item for item in selected if item.domain == "example.com"]) == 1


def make_evidence(
    source_id: str,
    directness: EvidenceDirectness,
    relation: EvidenceRelation = EvidenceRelation.SUPPORTS,
    scope: EvidenceScope = EvidenceScope.CLAIM_SPECIFIC,
    text: str = "Полезный результат",
) -> Evidence:
    return Evidence(
        claim_id="claim-8",
        source_id=source_id,
        source_url="https://example.com/source",
        source_title="Источник",
        evidence_text=text,
        evidence_summary=text,
        relation=relation,
        evidence_strength=EvidenceStrength.MODERATE,
        directness=directness,
        scope=scope,
        usable=True,
    )


def test_coverage_separates_direct_indirect_and_contradicting_evidence() -> None:
    coverage = EvidenceCoverageService().calculate(
        make_claim(),
        [
            make_evidence("direct", EvidenceDirectness.DIRECT),
            make_evidence("indirect", EvidenceDirectness.INDIRECT),
            make_evidence("contra", EvidenceDirectness.DIRECT, EvidenceRelation.CONTRADICTS),
        ],
    )

    assert coverage.level == "хорошее"
    assert coverage.direct_count == 2
    assert coverage.indirect_count == 1
    assert coverage.contradicting_count == 1
    assert coverage.independent_source_count == 3


def test_only_indirect_evidence_has_limited_coverage() -> None:
    coverage = EvidenceCoverageService().calculate(
        make_claim(), [make_evidence("source", EvidenceDirectness.INDIRECT)]
    )

    assert coverage.level == "ограниченное"
    assert EvidenceCoverageService.needs_second_pass(coverage) is True


def test_composite_claim_reports_uncovered_component() -> None:
    claim = make_claim(
        "Прогулки полезны и улучшают сон",
        scope=ClaimScope.COMPOSITE,
        components=["Прогулки полезны", "улучшают сон"],
    )
    coverage = EvidenceCoverageService().calculate(
        claim,
        [make_evidence("source", EvidenceDirectness.DIRECT, text="Прогулки полезны")],
    )

    assert coverage.uncovered_components == ["улучшают сон"]
    assert coverage.level == "ограниченное"


def test_not_relevant_and_background_do_not_count_as_coverage() -> None:
    coverage = EvidenceCoverageService().calculate(
        make_claim(),
        [
            make_evidence("one", EvidenceDirectness.NOT_RELEVANT),
            make_evidence("two", EvidenceDirectness.BACKGROUND),
        ],
    )

    assert coverage.level == "нет покрытия"
    assert coverage.not_relevant_count == 1
    assert coverage.background_count == 1


def test_smoking_regression_keeps_passive_smoke_outside_direct_coverage() -> None:
    claim = make_claim("Курить вредно")
    evidence = make_evidence(
        "passive",
        EvidenceDirectness.INDIRECT,
        scope=EvidenceScope.GENERAL_POPULATION,
        text="Пассивное курение повышает риск для некурящих",
    )

    coverage = EvidenceCoverageService().calculate(claim, [evidence])

    assert coverage.direct_count == 0
    assert coverage.indirect_count == 1
    assert coverage.level == "ограниченное"


def test_fresh_air_regression_does_not_promote_general_activity_to_direct() -> None:
    claim = make_claim("Гулять на свежем воздухе полезно")
    evidence = make_evidence(
        "activity",
        EvidenceDirectness.INDIRECT,
        scope=EvidenceScope.GENERAL_POPULATION,
        text="Регулярная физическая активность полезна для здоровья",
    )

    coverage = EvidenceCoverageService().calculate(claim, [evidence])

    assert coverage.direct_count == 0
    assert coverage.scope_mismatch is True
    assert coverage.level == "ограниченное"
