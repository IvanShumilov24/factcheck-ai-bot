import pytest

from app.config import Settings
from app.core.exceptions import ContentTooLargeError, OCRError
from app.domain.content import ContentInput, ContentType
from app.services.content import ContentPreparationService
from app.services.extraction.text import TextContentExtractor
from app.services.extraction.url import UrlContentExtractor
from app.services.ocr.provider import MockOCRProvider


@pytest.mark.asyncio
async def test_mock_ocr_prepares_extracted_content() -> None:
    config = Settings()
    service = ContentPreparationService(
        TextContentExtractor(config),
        UrlContentExtractor(config),
        MockOCRProvider(config, "Текст с изображения"),
    )
    result = await service.prepare(
        ContentInput(source_type=ContentType.IMAGE, image_bytes=b"fake-image")
    )
    assert result.extracted_text == "Текст с изображения"
    assert result.extraction_method == "ocr"


@pytest.mark.asyncio
async def test_mock_ocr_errors_without_text() -> None:
    with pytest.raises(OCRError):
        await MockOCRProvider(Settings()).recognize(b"fake-image")


@pytest.mark.asyncio
async def test_mock_ocr_enforces_image_limit() -> None:
    with pytest.raises(ContentTooLargeError):
        await MockOCRProvider(Settings(MAX_IMAGE_SIZE=2), "text").recognize(b"123")
