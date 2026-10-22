from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ContentType(StrEnum):
    TEXT = "TEXT"
    URL = "URL"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"


class ContentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_type: ContentType
    text: str | None = None
    url: HttpUrl | None = None
    image_bytes: bytes | None = None
    original_reference: str | None = None


class ExtractedContent(BaseModel):
    source_type: ContentType
    original_reference: str
    extracted_text: str = ""
    title: str | None = None
    source_url: HttpUrl | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    extraction_method: str
    warnings: list[str] = Field(default_factory=list)
