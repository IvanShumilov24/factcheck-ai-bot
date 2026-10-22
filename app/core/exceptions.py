class ApplicationError(Exception):
    """Base class for expected, user-facing application failures."""


class InvalidInputError(ApplicationError):
    pass


class ContentTooLargeError(ApplicationError):
    pass


class UnsupportedContentError(ApplicationError):
    pass


class UrlFetchError(ApplicationError):
    pass


class BlockedContentError(UrlFetchError):
    pass


class CaptchaDetectedError(BlockedContentError):
    pass


class EmptyContentError(UrlFetchError):
    pass


class ExtractionError(ApplicationError):
    pass


class OCRError(ApplicationError):
    pass


class LLMError(ApplicationError, RuntimeError):
    pass


class LLMTimeoutError(LLMError):
    pass


class LLMResponseError(LLMError):
    pass


class SearchError(ApplicationError):
    pass


class SearchTimeoutError(SearchError):
    pass


class SearchRateLimitError(SearchError):
    pass
