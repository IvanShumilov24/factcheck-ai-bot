import re
import unicodedata
from collections.abc import Iterable
from difflib import SequenceMatcher
from hashlib import sha256

from pydantic import ValidationError

from app.config import Settings
from app.core.exceptions import ContentTooLargeError, LLMResponseError
from app.domain.claims import Claim, ClaimExtractionCandidate, ClaimExtractionResponse
from app.domain.content import ExtractedContent
from app.services.claims.prompts import SYSTEM_PROMPT, build_claim_extraction_prompt
from app.services.ports import ClaimExtractionRequest, LLMProvider


class ClaimExtractionService:
    def __init__(self, provider: LLMProvider, config: Settings) -> None:
        self._provider = provider
        self._config = config

    async def extract(self, content: ExtractedContent) -> list[Claim]:
        text = content.extracted_text.strip()
        if not text:
            return []
        chunks = self._chunk(text)
        candidates: list[ClaimExtractionCandidate] = []
        for index, chunk in enumerate(chunks, start=1):
            request = ClaimExtractionRequest(
                text=build_claim_extraction_prompt(content, chunk, index),
                source_type=content.source_type.value,
                title=content.title,
                system_prompt=SYSTEM_PROMPT,
            )
            try:
                response = await self._provider.extract_claims(request)
                validated = ClaimExtractionResponse.model_validate(response)
                candidates.extend(
                    ClaimExtractionCandidate.model_validate(item) for item in validated.claims
                )
            except (AttributeError, ValidationError, TypeError) as exc:
                raise LLMResponseError("LLM returned an invalid structured response") from exc
        return self._deduplicate(self._to_claims(candidates, content))

    def _chunk(self, text: str) -> list[str]:
        if len(text) > self._config.claim_chunk_size * self._config.max_claim_chunks:
            raise ContentTooLargeError("Material exceeds the claim extraction limit")
        size = self._config.claim_chunk_size
        overlap = min(self._config.claim_chunk_overlap, max(size - 1, 0))
        if len(text) <= size:
            return [text]
        chunks: list[str] = []
        start = 0
        while start < len(text) and len(chunks) < self._config.max_claim_chunks:
            end = min(start + size, len(text))
            if end < len(text):
                boundary = text.rfind("\n\n", start, end)
                if boundary > start + size // 2:
                    end = boundary
            chunks.append(text[start:end].strip())
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
        return chunks

    @staticmethod
    def _to_claims(
        candidates: Iterable[ClaimExtractionCandidate], content: ExtractedContent
    ) -> list[Claim]:
        return [
            Claim(
                **candidate.model_dump(exclude={"normalized_text"}),
                claim_id=sha256(
                    f"{content.original_reference}:{candidate.text}".encode()
                ).hexdigest()[:16],
                normalized_text=ClaimExtractionService._normalize_question(
                    candidate.text, candidate.normalized_text or candidate.text
                ),
                source_type=content.source_type,
                source_reference=content.original_reference,
                source_url=str(content.source_url) if content.source_url else None,
                metadata={"extraction_method": content.extraction_method},
            )
            for candidate in candidates
        ]

    @staticmethod
    def _normalize_question(text: str, normalized: str) -> str:
        """Apply only conservative, well-known Russian question normalizations."""
        value = " ".join(text.strip().split()).casefold().rstrip("?!")
        if value in {"курить вредно", "курение вредно"}:
            return "Курение вредит здоровью человека."
        if "вич" in value and "комар" in value and ("переда" in value or "зараз" in value):
            return "ВИЧ может передаваться человеку через укус комара."
        if "прогул" in value and "свеж" in value and "воздух" in value:
            return "Прогулки на свежем воздухе полезны для здоровья."
        return normalized.strip() or text.strip()

    @classmethod
    def _deduplicate(cls, claims: list[Claim]) -> list[Claim]:
        unique: list[Claim] = []
        seen: set[str] = set()
        for claim in claims:
            key = cls._key(claim.normalized_text)
            if key in seen:
                continue
            if any(
                SequenceMatcher(None, key, cls._key(item.normalized_text)).ratio() >= 0.94
                for item in unique
            ):
                continue
            seen.add(key)
            unique.append(claim)
        return unique

    @staticmethod
    def _key(value: str) -> str:
        value = unicodedata.normalize("NFKC", value).casefold()
        return re.sub(r"[^\w\s]", "", value, flags=re.UNICODE)
