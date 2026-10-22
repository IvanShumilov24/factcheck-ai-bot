import re

from app.config import Settings
from app.core.exceptions import ContentTooLargeError, InvalidInputError
from app.domain.content import ContentInput, ContentType, ExtractedContent


class TextContentExtractor:
    def __init__(self, config: Settings) -> None:
        self._config = config

    async def extract(self, content: ContentInput) -> ExtractedContent:
        if content.source_type is not ContentType.TEXT or content.text is None:
            raise InvalidInputError("Text content is required")
        if len(content.text) > self._config.max_text_length:
            raise ContentTooLargeError("Text exceeds the configured limit")
        normalized = re.sub(r"\s+", " ", content.text).strip()
        if not normalized:
            raise InvalidInputError("Text must not be empty")
        return ExtractedContent(
            source_type=ContentType.TEXT,
            original_reference=content.text,
            extracted_text=normalized,
            extraction_method="text_normalization",
            metadata={"original_length": len(content.text)},
        )
