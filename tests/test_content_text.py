import pytest

from app.config import Settings
from app.core.exceptions import ContentTooLargeError, InvalidInputError
from app.domain.content import ContentInput, ContentType
from app.services.extraction.text import TextContentExtractor


@pytest.mark.asyncio
async def test_text_is_normalized_without_changing_content() -> None:
    result = await TextContentExtractor(Settings()).extract(
        ContentInput(source_type=ContentType.TEXT, text="  Текст   с\nпробелами  ")
    )
    assert result.extracted_text == "Текст с пробелами"
    assert result.original_reference == "Текст   с\nпробелами"


@pytest.mark.asyncio
async def test_empty_text_is_rejected() -> None:
    with pytest.raises(InvalidInputError):
        await TextContentExtractor(Settings()).extract(
            ContentInput(source_type=ContentType.TEXT, text="   ")
        )


@pytest.mark.asyncio
async def test_large_text_is_rejected() -> None:
    config = Settings(MAX_TEXT_LENGTH=3)
    with pytest.raises(ContentTooLargeError):
        await TextContentExtractor(config).extract(
            ContentInput(source_type=ContentType.TEXT, text="long")
        )
