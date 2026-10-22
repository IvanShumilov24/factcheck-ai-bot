from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.domain.claims import ClaimExtractionResponse
from app.domain.content import ContentInput, ExtractedContent
from app.domain.evidence import EvidenceExtractionResponse
from app.domain.schemas import CheckRequest, EvidenceAnalysis, FactCheckResult
from app.domain.search import SearchQueryResponse, SearchResult


@dataclass(frozen=True)
class ClaimExtractionRequest:
    text: str
    source_type: str
    title: str | None
    system_prompt: str


@dataclass(frozen=True)
class SearchQueryRequest:
    claim_text: str
    claim_id: str
    strategies: list[str]
    system_prompt: str
    claim_scope: str = "UNKNOWN"


@dataclass(frozen=True)
class EvidenceExtractionRequest:
    claim_id: str
    claim_text: str
    source_id: str
    source_title: str
    source_url: str
    source_type: str
    source_quality: float
    source_relevance: float
    source_text: str
    system_prompt: str


@dataclass(frozen=True)
class EvidenceAnalysisRequest:
    claim_id: str
    claim_text: str
    evidence: list[dict[str, object]]
    source_metadata: list[dict[str, object]]
    system_prompt: str


class LLMProvider(Protocol):
    async def extract_claims(self, request: ClaimExtractionRequest) -> ClaimExtractionResponse: ...

    async def generate_search_queries(self, request: SearchQueryRequest) -> SearchQueryResponse: ...

    async def extract_evidence(
        self, request: EvidenceExtractionRequest
    ) -> EvidenceExtractionResponse: ...

    async def analyze_evidence(self, request: EvidenceAnalysisRequest) -> EvidenceAnalysis: ...


class SearchProvider(Protocol):
    async def search(self, query: str, limit: int = 5) -> list[SearchResult]: ...


class ContentExtractor(Protocol):
    async def extract(self, content: ContentInput) -> ExtractedContent: ...


class OCRProvider(Protocol):
    async def recognize(self, image: bytes) -> str: ...


class FactCheckService(Protocol):
    async def check(self, request: CheckRequest) -> Sequence[FactCheckResult]: ...
