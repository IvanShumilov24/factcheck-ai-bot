from app.core.exceptions import InvalidInputError, UnsupportedContentError
from app.domain.content import ContentInput, ContentType, ExtractedContent
from app.services.extraction.text import TextContentExtractor
from app.services.extraction.url import UrlContentExtractor
from app.services.ocr.provider import MockOCRProvider


class ContentPreparationService:
    def __init__(
        self,
        text_extractor: TextContentExtractor,
        url_extractor: UrlContentExtractor,
        ocr_provider: MockOCRProvider,
    ) -> None:
        self._text = text_extractor
        self._url = url_extractor
        self._ocr = ocr_provider

    async def prepare(self, content: ContentInput) -> ExtractedContent:
        if content.source_type is ContentType.TEXT:
            return await self._text.extract(content)
        if content.source_type is ContentType.URL:
            return await self._url.extract(content)
        if content.source_type is ContentType.IMAGE:
            if content.image_bytes is None:
                raise InvalidInputError("Image bytes are required")
            text = await self._ocr.recognize(content.image_bytes)
            return ExtractedContent(
                source_type=ContentType.IMAGE,
                original_reference=content.original_reference or "telegram:image",
                extracted_text=text,
                extraction_method="ocr",
            )
        raise UnsupportedContentError("Video processing is not implemented yet")
