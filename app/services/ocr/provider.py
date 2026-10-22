from app.config import Settings
from app.core.exceptions import ContentTooLargeError, OCRError


class MockOCRProvider:
    """Replaceable local provider for tests and development demos."""

    def __init__(self, config: Settings, text: str = "") -> None:
        self._config = config
        self._text = text

    async def recognize(self, image: bytes) -> str:
        if len(image) > self._config.max_image_size:
            raise ContentTooLargeError("Image exceeds the configured limit")
        if not image:
            raise OCRError("Image is empty")
        if not self._text.strip():
            raise OCRError("No text recognized in image")
        return self._text.strip()
