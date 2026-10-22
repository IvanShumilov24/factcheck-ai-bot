from app.bot.handlers import _content_hash
from app.domain.content import ContentInput, ContentType


def test_content_hash_ignores_delivery_metadata() -> None:
    first = _content_hash(
        ContentInput(source_type=ContentType.TEXT, text="  Один   текст\nс пробелами ")
    )
    second = _content_hash(
        ContentInput(source_type=ContentType.TEXT, text="Один текст с пробелами")
    )

    assert first == second


def test_content_hash_uses_image_bytes_not_telegram_file_id() -> None:
    first = _content_hash(
        ContentInput(
            source_type=ContentType.IMAGE, image_bytes=b"same", original_reference="file-1"
        )
    )
    second = _content_hash(
        ContentInput(
            source_type=ContentType.IMAGE, image_bytes=b"same", original_reference="file-2"
        )
    )

    assert first == second
