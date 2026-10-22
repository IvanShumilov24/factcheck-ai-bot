from urllib.parse import urlparse

from app.domain.search import AuthorityLevel, SourceType


class SourceClassifier:
    """Objective, extendable domain/title rules; no LLM authority claims."""

    _official_domains = {
        "who.int",
        "cdc.gov",
        "nih.gov",
        "ncbi.nlm.nih.gov",
        "nhs.uk",
        "fda.gov",
        "ema.europa.eu",
        "gov.uk",
        "minzdrav.gov.ru",
    }
    _guideline_domains = {"nice.org.uk", "who.int", "cdc.gov", "nhs.uk"}
    _research_domains = {
        "pubmed.ncbi.nlm.nih.gov",
        "pmc.ncbi.nlm.nih.gov",
        "cochranelibrary.com",
    }
    _social_domains = {"facebook.com", "instagram.com", "tiktok.com", "x.com", "twitter.com"}

    def classify(self, url: str, title: str = "") -> tuple[SourceType, AuthorityLevel]:
        domain = (urlparse(url).hostname or "").lower().removeprefix("www.")
        title_key = title.casefold()
        if self._matches(domain, self._social_domains):
            return SourceType.SOCIAL, AuthorityLevel.LOW
        if self._matches(domain, self._guideline_domains) or "guideline" in title_key:
            return SourceType.GUIDELINE, AuthorityLevel.HIGH
        if self._matches(domain, self._research_domains):
            if "systematic review" in title_key or "систематический обзор" in title_key:
                return SourceType.SYSTEMATIC_REVIEW, AuthorityLevel.HIGH
            if "meta-analysis" in title_key or "meta analysis" in title_key:
                return SourceType.META_ANALYSIS, AuthorityLevel.HIGH
            return SourceType.PEER_REVIEWED_STUDY, AuthorityLevel.HIGH
        if self._matches(domain, self._official_domains):
            return SourceType.OFFICIAL, AuthorityLevel.HIGH
        if any(term in title_key for term in ("systematic review", "мета-анализ")):
            return SourceType.SYSTEMATIC_REVIEW, AuthorityLevel.MEDIUM
        if any(term in title_key for term in ("news", "новости")):
            return SourceType.NEWS, AuthorityLevel.LOW
        return SourceType.UNKNOWN, AuthorityLevel.UNKNOWN

    @staticmethod
    def _matches(domain: str, known: set[str]) -> bool:
        return any(domain == item or domain.endswith(f".{item}") for item in known)
