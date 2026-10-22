import hashlib
import io
import json
import logging
from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from pydantic import HttpUrl, TypeAdapter, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.bot.keyboards import (
    details_keyboard,
    education_keyboard,
    followup_actions_keyboard,
    history_keyboard,
    main_menu,
    result_actions_keyboard,
)
from app.config import settings
from app.core.exceptions import ApplicationError, ContentTooLargeError, LLMError
from app.database.models import CheckModel
from app.database.session import session_factory
from app.domain.content import ContentInput, ContentType
from app.redis import create_redis
from app.repositories.checks import CheckPersistenceService, CheckRepository
from app.services.claims.service import ClaimExtractionService
from app.services.content import ContentPreparationService
from app.services.demo import demo_keyboard, demo_report
from app.services.education import LESSONS, lesson_page
from app.services.evidence import EvidenceAnalysisService, EvidenceExtractionService, VerdictService
from app.services.extraction.text import TextContentExtractor
from app.services.extraction.url import UrlContentExtractor
from app.services.history import (
    HISTORY_PAGE_SIZE,
    format_history_datetime,
    parse_details_callback,
    parse_history_callback,
)
from app.services.llm.provider import OpenRouterLLMProvider, UnconfiguredLLMProvider
from app.services.ocr.provider import MockOCRProvider
from app.services.queue import CheckJobQueue
from app.services.ratelimit import RateLimiter
from app.services.report import (
    format_saved_check,
    format_saved_details_page,
    format_saved_evidence,
    format_saved_sources,
    verdict_label,
)
from app.services.search.provider import UnconfiguredSearchProvider, YandexSearchProvider
from app.services.search.service import SearchQueryGenerator, SourceSearchService

router = Router()
logger = logging.getLogger(__name__)
content_service = ContentPreparationService(
    TextContentExtractor(settings),
    UrlContentExtractor(settings, create_redis()),
    MockOCRProvider(settings, settings.mock_ocr_text),
)
llm_provider = (
    OpenRouterLLMProvider(settings)
    if settings.openrouter_api_key or settings.anthropic_api_key
    else UnconfiguredLLMProvider()
)
claim_extraction_service = ClaimExtractionService(llm_provider, settings)
search_provider = (
    YandexSearchProvider(settings, create_redis())
    if settings.yandex_api_key and settings.yandex_folder_id
    else UnconfiguredSearchProvider()
)
source_search_service = SourceSearchService(
    SearchQueryGenerator(llm_provider, settings),
    search_provider,
    settings,
    content_extractor=UrlContentExtractor(settings, create_redis()),
)
evidence_extraction_service = EvidenceExtractionService(llm_provider, settings)
evidence_analysis_service = EvidenceAnalysisService(llm_provider)
verdict_service = VerdictService()
persistence_service = CheckPersistenceService(session_factory)
redis_client = create_redis()
rate_limiter = RateLimiter(
    redis_client,
    limit=settings.rate_limit_per_minute,
    window_seconds=settings.rate_limit_window_seconds,
)
job_queue = CheckJobQueue(redis_client, stream=settings.queue_stream, group=settings.queue_group)


async def _answer_callback_safely(callback: CallbackQuery) -> None:
    """A stale callback must not break the handler that processes its action."""
    try:
        await callback.answer()
    except TelegramBadRequest as exc:
        error_text = str(exc).casefold()
        if "query is too old" in error_text or "query id is invalid" in error_text:
            logger.info("telegram_callback_expired")
            return
        raise


@router.message(Command("start"))
async def start_handler(message: Message) -> None:
    await message.answer(
        "🔬 Правда под вопросом\n\n"
        "Помогу проверить медицинскую информацию и понять, насколько ей можно доверять.\n\n"
        "Выберите действие:",
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(
        "Как пользоваться:\n\n"
        "1. Отправьте текст или ссылку.\n"
        "2. На следующем этапе бот выделит утверждения и найдет источники.\n\n"
        "Важно: бот проверяет информацию, но не ставит диагноз."
    )


@router.message(Command("demo"))
async def demo_handler(message: Message) -> None:
    await message.answer(demo_report(), reply_markup=demo_keyboard())


@router.message(Command("cancel"))
async def cancel_handler(message: Message) -> None:
    """Cancel the user's queued or currently processing check."""
    if message.from_user is None:
        await message.answer("⚠️ Не удалось определить пользователя.")
        return
    try:
        check = await persistence_service.get_active(message.from_user.id)
        if check is None:
            await message.answer("ℹ️ Активной проверки нет.")
            return
        await redis_client.set(f"check-cancel:{check.id}", "1", ex=settings.job_dedupe_ttl)
        cancelled = await persistence_service.cancel(check.id)
        if not cancelled:
            await message.answer("ℹ️ Проверка уже завершена или отменена.")
            return
        payload = check.job_payload or {}
        chat_id = payload.get("chat_id")
        status_message_id = payload.get("status_message_id")
        if isinstance(chat_id, int) and isinstance(status_message_id, int) and message.bot:
            try:
                await message.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_message_id,
                    text="❌ Проверка отменена.",
                )
            except Exception:
                logger.info("telegram_cancel_status_update_failed", exc_info=True)
        await message.answer("❌ Проверка отменена.")
    except SQLAlchemyError:
        logger.exception("cancel_database_failed")
        await message.answer("⚠️ Не удалось отменить проверку. Попробуйте позже.")


@router.message(Command("history"))
async def history_handler(message: Message) -> None:
    if message.from_user is None:
        await message.answer("⚠️ Не удалось определить пользователя.")
        return
    await _show_history(message, message.from_user.id, 0)


@router.callback_query(F.data.startswith("history:"))
async def history_callback(callback: CallbackQuery) -> None:
    await _answer_callback_safely(callback)
    if not isinstance(callback.message, Message) or callback.from_user is None or not callback.data:
        return
    if callback.data.startswith("history:details:"):
        details = parse_details_callback(callback.data)
        if details is None:
            await callback.message.answer(
                "⚠️ Эта кнопка устарела. Откройте историю заново: /history"
            )
            return
        check_id, page = details
        await _show_saved_details(callback.message, callback.from_user.id, check_id, page)
        return
    parsed = parse_history_callback(callback.data)
    if parsed is None:
        await callback.message.answer("⚠️ Эта кнопка устарела. Откройте историю заново: /history")
        return
    action, value = parsed
    if action == "page":
        await _show_history(callback.message, callback.from_user.id, value, edit=True)
        return
    if action == "view":
        await _show_saved_check(callback.message, callback.from_user.id, value)
    elif action == "result":
        await _show_saved_result(callback.message, callback.from_user.id, value)
    elif action == "details":
        await _show_saved_details(callback.message, callback.from_user.id, value)
    elif action == "evidence":
        await _show_saved_material(callback.message, callback.from_user.id, value, "evidence")
    else:
        await _show_saved_material(callback.message, callback.from_user.id, value, "sources")


@router.callback_query(F.data == "check")
async def check_callback(callback: CallbackQuery) -> None:
    await _answer_callback_safely(callback)
    if callback.message:
        await callback.message.answer(
            "Отправьте текст, ссылку или изображение с текстом.\n\n"
            f"Максимальный размер текста: {settings.max_text_length} символов."
        )


@router.callback_query(F.data.startswith("education"))
async def education_callback(callback: CallbackQuery) -> None:
    await _answer_callback_safely(callback)
    if not isinstance(callback.message, Message):
        return
    page = 0
    if callback.data and ":" in callback.data:
        try:
            page = int(callback.data.rsplit(":", 1)[1])
        except ValueError:
            page = 0
    page = min(max(page, 0), len(LESSONS) - 1)
    await callback.message.edit_text(
        lesson_page(page), reply_markup=education_keyboard(page, len(LESSONS))
    )


@router.callback_query(F.data == "about")
async def about_callback(callback: CallbackQuery) -> None:
    await _answer_callback_safely(callback)
    if callback.message:
        await callback.message.answer(
            "🔬 Правда под вопросом\n\n"
            "Проверяем медицинскую информацию по доступным источникам.\n\n"
            "Важно: результат носит информационный характер, не является диагнозом "
            "или заменой консультации врача.",
            reply_markup=main_menu(),
        )


@router.message()
async def input_placeholder_handler(message: Message) -> None:
    if message.photo:
        await _handle_image(message)
        return
    if not message.text:
        await message.answer("Пожалуйста, отправьте текст, ссылку или изображение с текстом.")
        return
    await _handle_text_or_url(message)


async def _handle_text_or_url(message: Message) -> None:
    raw = message.text or ""
    if message.from_user is None or not await rate_limiter.allow(message.from_user.id, "check"):
        await message.answer("⏳ Слишком много запросов подряд. Попробуйте немного позже.")
        return
    if len(raw) > settings.max_text_length:
        await message.answer("⚠️ Текст слишком большой.")
        return
    status_message = await message.answer("🔎 Получил материал. Подготавливаю его к проверке…")
    source_type = ContentType.URL if urlparse(raw).scheme in {"http", "https"} else ContentType.TEXT
    try:
        parsed_url = (
            TypeAdapter(HttpUrl).validate_python(raw) if source_type is ContentType.URL else None
        )
        content = ContentInput(
            source_type=source_type,
            text=None if source_type is ContentType.URL else raw,
            url=parsed_url,
        )
        await _enqueue_check(message, content, status_message)
    except (ApplicationError, ValidationError) as exc:
        logger.info("content_preparation_failed type=%s error=%s", source_type, type(exc).__name__)
        await message.answer(_user_error(exc))
        return
    except Exception:
        logger.exception("content_preparation_unexpected type=%s", source_type)
        await message.answer("⚠️ Не удалось подготовить материал. Попробуйте позже.")
        return


async def _handle_image(message: Message) -> None:
    photos = message.photo
    if not photos:
        await message.answer("Пожалуйста, отправьте изображение с текстом.")
        return
    photo = photos[-1]
    if message.from_user is None or not await rate_limiter.allow(message.from_user.id, "check"):
        await message.answer("⏳ Слишком много запросов подряд. Попробуйте немного позже.")
        return
    if photo.file_size and photo.file_size > settings.max_image_size:
        await message.answer("⚠️ Изображение слишком большое.")
        return
    status_message = await message.answer("🖼 Получил изображение. Подготавливаю его к проверке…")
    try:
        bot = message.bot
        if bot is None:
            raise RuntimeError("Telegram bot is unavailable")
        telegram_file = await bot.get_file(photo.file_id)
        if not telegram_file.file_path:
            raise ContentTooLargeError("Image path is unavailable")
        buffer = io.BytesIO()
        await bot.download_file(telegram_file.file_path, destination=buffer)
        await _enqueue_check(
            message,
            ContentInput(
                source_type=ContentType.IMAGE,
                image_bytes=buffer.getvalue(),
                original_reference=photo.file_id,
            ),
            status_message,
        )
    except (ApplicationError, ValidationError) as exc:
        logger.info("content_preparation_failed type=IMAGE error=%s", type(exc).__name__)
        await message.answer(_user_error(exc))
        return
    except Exception:
        logger.exception("content_preparation_unexpected type=IMAGE")
        await message.answer("⚠️ Не удалось подготовить изображение. Попробуйте позже.")
        return


def _user_error(error: Exception) -> str:
    if isinstance(error, ContentTooLargeError):
        return "⚠️ Материал превышает допустимый размер."
    if isinstance(error, LLMError):
        return "⚠️ Анализ утверждений временно недоступен. Попробуйте позже."
    return "⚠️ Не удалось подготовить материал. Проверьте его и попробуйте ещё раз."


def _content_hash(content: ContentInput) -> str:
    """Hash only stable content identity, excluding Telegram delivery metadata."""
    if content.source_type is ContentType.TEXT:
        identity = {
            "type": content.source_type.value,
            "text": " ".join((content.text or "").split()),
        }
    elif content.source_type is ContentType.URL:
        identity = {
            "type": content.source_type.value,
            "url": UrlContentExtractor._cache_key(str(content.url)),
        }
    elif content.source_type is ContentType.IMAGE:
        image_hash = hashlib.sha256(content.image_bytes or b"").hexdigest()
        identity = {"type": content.source_type.value, "image": image_hash}
    else:
        identity = content.model_dump(mode="json", exclude={"original_reference"})
    serialized = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


async def _enqueue_check(message: Message, content: ContentInput, status_message: Message) -> None:
    if message.from_user is None or message.chat is None:
        await message.answer("⚠️ Не удалось определить пользователя. Попробуйте ещё раз.")
        return
    content_payload = json.loads(content.model_dump_json())
    payload: dict[str, object] = {"content": content_payload}
    payload.update(
        {
            "telegram_id": message.from_user.id,
            "chat_id": message.chat.id,
            "status_message_id": status_message.message_id,
            "attempt": 0,
        }
    )
    input_hash = _content_hash(content)
    dedupe_key = f"check-active:v1:{message.from_user.id}:{input_hash}"
    try:
        acquired = await redis_client.set(dedupe_key, "1", ex=settings.job_dedupe_ttl, nx=True)
        if not acquired:
            await _update_status(
                status_message, "⏳ Такая проверка уже выполняется. Дождитесь результата."
            )
            return
        payload["dedupe_key"] = dedupe_key
        check_id = await persistence_service.create_queued(
            telegram_id=message.from_user.id,
            input_type=content.source_type.value,
            input_hash=input_hash,
            pipeline_version="stage-9",
            model_version=settings.openrouter_model or settings.anthropic_model,
            job_payload=payload,
        )
        payload["check_id"] = check_id
        await persistence_service.set_job_payload(check_id, payload)
        await job_queue.enqueue(payload)
        await _update_status(status_message, "✅ Материал получен. Проверка поставлена в очередь…")
    except Exception:
        await redis_client.delete(dedupe_key)
        logger.exception(
            "check_enqueue_failed user_id_hash=%s", _safe_user_id(message.from_user.id)
        )
        await message.answer("⚠️ Не удалось начать проверку. Попробуйте ещё раз позже.")


def _safe_user_id(user_id: int) -> str:
    return hashlib.sha256(str(user_id).encode()).hexdigest()[:12]


async def _update_status(message: Message | None, text: str) -> None:
    if message is None:
        return
    try:
        await message.edit_text(text)
    except Exception:
        logger.info("telegram_status_update_failed", exc_info=True)


async def _show_history(
    message: Message, telegram_id: int, page: int, *, edit: bool = False
) -> None:
    page = max(page, 0)

    async def render(text: str, markup: InlineKeyboardMarkup) -> None:
        if edit:
            await message.edit_text(text, reply_markup=markup)
        else:
            await message.answer(text, reply_markup=markup)

    try:
        async with session_factory() as session:
            checks, has_next = await CheckRepository(session).get_user_history(
                telegram_id,
                offset=page * HISTORY_PAGE_SIZE,
                limit=HISTORY_PAGE_SIZE,
            )
    except SQLAlchemyError:
        logger.exception("history_database_failed operation=list")
        await render(
            "⚠️ История временно недоступна. Попробуйте позже.",
            history_keyboard(page, page > 0, False),
        )
        return
    if not checks:
        if page > 0:
            await render(
                f"🗂 История проверок · страница {page + 1}\n\nНа этой странице проверок нет.",
                history_keyboard(page, page > 0, False),
            )
        else:
            await render(
                "🗂 История проверок пока пуста.\n\nОтправьте материал, чтобы начать проверку.",
                history_keyboard(0, False, False),
            )
        return
    lines = [f"🗂 История проверок · страница {page + 1}", ""]
    for check in checks:
        claim = check.claims[0] if check.claims else None
        verdict = claim.verdict if claim else None
        text = _truncate(claim.text if claim else "Без утверждений", 100)
        created_at = check.created_at
        date_text = format_history_datetime(created_at)
        status = verdict_label(verdict.status) if verdict else "НЕ ЗАВЕРШЕНО"
        lines.append(f"№{check.id} · {date_text}\n{text}\n{status}\n")
    await render(
        "\n".join(lines)[:3900],
        history_keyboard(page, page > 0, has_next),
    )


async def _show_saved_check(message: Message, telegram_id: int, check_id: int) -> None:
    check = await _get_saved_check(message, telegram_id, check_id)
    if check is None:
        return
    for report in format_saved_check(check):
        await _send_report_chunks(message, report, result_actions_keyboard(check_id))


async def _show_saved_details(
    message: Message, telegram_id: int, check_id: int, page: int = 0
) -> None:
    check = await _get_saved_check(message, telegram_id, check_id)
    if check is None:
        return
    text, has_next = format_saved_details_page(check, page)
    await message.edit_text(
        text,
        reply_markup=details_keyboard(check_id, max(page, 0), page > 0, has_next),
    )


async def _show_saved_result(message: Message, telegram_id: int, check_id: int) -> None:
    check = await _get_saved_check(message, telegram_id, check_id)
    if check is None:
        return
    reports = format_saved_check(check)
    report = "\n\n".join(reports)
    await message.edit_text(report[:3900], reply_markup=result_actions_keyboard(check_id))


async def _show_saved_material(
    message: Message, telegram_id: int, check_id: int, material: str
) -> None:
    check = await _get_saved_check(message, telegram_id, check_id)
    if check is None:
        return
    report = format_saved_evidence(check) if material == "evidence" else format_saved_sources(check)
    await _send_report_chunks(message, report, followup_actions_keyboard())


async def _get_saved_check(message: Message, telegram_id: int, check_id: int) -> CheckModel | None:
    try:
        async with session_factory() as session:
            check = await CheckRepository(session).get_user_check_with_details(
                telegram_id, check_id
            )
    except SQLAlchemyError:
        logger.exception("history_database_failed operation=view")
        await message.answer("⚠️ Проверка временно недоступна. Попробуйте позже.")
        return None
    if check is None:
        await message.answer("⚠️ Проверка не найдена или недоступна.")
    return check


async def _send_report_chunks(
    message: Message, report: str, reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    chunk_size = 3900
    for index in range(0, len(report), chunk_size):
        await message.answer(
            report[index : index + chunk_size],
            reply_markup=reply_markup if index + chunk_size >= len(report) else None,
        )


def _truncate(value: str, limit: int) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else f"{value[: limit - 1]}…"
