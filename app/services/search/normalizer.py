import hashlib
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.domain.enums import ContentStatus
from app.domain.schemas import Source
from app.domain.search import AuthorityLevel, SearchResult, SourceType
from app.services.search.classifier import SourceClassifier


class SourceNormalizer:
    def __init__(self, classifier: SourceClassifier | None = None) -> None:
        self._classifier = classifier or SourceClassifier()

    def normalize(self, result: SearchResult, query: str, query_purpose: str = "GENERAL") -> Source:
        source_type, authority = self._classifier.classify(str(result.url), result.title)
        quality = self._quality_score(source_type, authority)
        return Source(
            source_id=hashlib.sha256(self.canonical_url(str(result.url)).encode()).hexdigest()[:16],
            title=result.title.strip() or str(result.url),
            url=result.url,
            domain=result.domain.lower(),
            source_type=source_type,
            authority_level=authority,
            search_queries=[query],
            snippet=result.snippet,
            published_at=result.published_at,
            retrieved_at=datetime.now(UTC),
            relevance_score=self._relevance_score(result, query),
            quality_score=quality,
            credibility_score=quality,
            metadata={
                **result.metadata,
                "query_purposes": [query_purpose],
            },
            content_status=ContentStatus.NOT_FETCHED,
        )

    @staticmethod
    def canonical_url(value: str) -> str:
        parts = urlsplit(value)
        query = [
            (key, val) for key, val in parse_qsl(parts.query) if not key.lower().startswith("utm_")
        ]
        path = parts.path.rstrip("/") or "/"
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))

    @classmethod
    def _quality_score(cls, source_type: SourceType, authority: AuthorityLevel) -> float:
        scores = {
            "OFFICIAL": 1.0,
            "GUIDELINE": 1.0,
            "SYSTEMATIC_REVIEW": 0.95,
            "META_ANALYSIS": 0.95,
            "PEER_REVIEWED_STUDY": 0.85,
            "MEDICAL_PUBLICATION": 0.75,
            "NEWS": 0.5,
            "BLOG": 0.3,
            "COMMERCIAL": 0.2,
            "SOCIAL": 0.1,
            "UNKNOWN": 0.2,
        }
        base = scores.get(source_type.value, 0.2)
        if authority is AuthorityLevel.HIGH:
            return min(1.0, base)
        if authority is AuthorityLevel.MEDIUM:
            return min(1.0, base * 0.85)
        if authority is AuthorityLevel.LOW:
            return min(1.0, base * 0.65)
        return min(1.0, base * 0.5)

    @staticmethod
    def _relevance_score(result: SearchResult, query: str) -> float:
        query_terms = {term.casefold() for term in query.split() if len(term) > 2}
        document_terms = {
            term.casefold() for term in f"{result.title} {result.snippet}".split() if len(term) > 2
        }
        lexical = len(query_terms & document_terms) / max(len(query_terms), 1)
        return round(min(1.0, 0.2 + 0.6 * lexical + 0.2 * result.relevance_score), 3)
