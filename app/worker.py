import asyncio
import hashlib
import logging
import os
import socket
from typing import Any

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from app.bot.handlers import (
    claim_extraction_service,
    content_service,
    evidence_analysis_service,
    evidence_extraction_service,
    job_queue,
    persistence_service,
    redis_client,
    source_search_service,
    verdict_service,
)
from app.bot.keyboards import result_actions_keyboard
from app.config import settings
from app.core.exceptions import LLMTimeoutError, SearchTimeoutError
from app.domain.content import ContentInput
from app.services.pipeline import FactCheckPipeline

logger = logging.getLogger(__name__)


def _failure_message(error: Exception) -> str:
    if isinstance(error, (LLMTimeoutError, SearchTimeoutError)):
        return "⏱️ Проверка заняла слишком много времени. Попробуйте ещё раз позже."
    return "⚠️ Не удалось завершить проверку. Попробуйте ещё раз позже."


def _should_release_dedupe(retry_scheduled: bool) -> bool:
    """Keep the active-job lock while a retry remains in the queue."""
    return not retry_scheduled


async def _update_status(bot: Bot, payload: dict[str, Any], text: str) -> None:
    try:
        await bot.edit_message_text(
            chat_id=int(payload["chat_id"]),
            message_id=int(payload["status_message_id"]),
            text=text,
        )
    except Exception:
        logger.info("worker_status_update_failed check_id=%s", payload.get("check_id"))


async def _delete_status(bot: Bot, payload: dict[str, Any]) -> None:
    try:
        await bot.delete_message(
            chat_id=int(payload["chat_id"]),
            message_id=int(payload["status_message_id"]),
        )
    except Exception:
        logger.info("worker_status_delete_failed check_id=%s", payload.get("check_id"))


async def _send_reports(
    bot: Bot, payload: dict[str, Any], reports: list[str], check_id: int
) -> None:
    for index, report in enumerate(reports):
        for start in range(0, len(report), 3900):
            await bot.send_message(
                chat_id=int(payload["chat_id"]),
                text=report[start : start + 3900],
                reply_markup=(
                    result_actions_keyboard(check_id)
                    if index == len(reports) - 1 and start + 3900 >= len(report)
                    else None
                ),
            )


async def process_job(bot: Bot, payload: dict[str, Any]) -> None:
    check_id = int(payload["check_id"])
    cancel_key = f"check-cancel:{check_id}"
    if await redis_client.get(cancel_key):
        await redis_client.delete(cancel_key)
        return
    await persistence_service.mark_processing(check_id)
    pipeline = FactCheckPipeline(
        content_service,
        claim_extraction_service,
        source_search_service,
        evidence_extraction_service,
        evidence_analysis_service,
        verdict_service,
        settings,
    )

    async def progress(text: str) -> None:
        await _update_status(bot, payload, text)

    content = ContentInput.model_validate(payload["content"])
    prepared = await content_service.prepare(content)
    results, reports, source_count = await pipeline.run(prepared, progress)
    if await redis_client.get(cancel_key):
        await redis_client.delete(cancel_key)
        return
    completed = await persistence_service.complete(check_id, results)
    if not completed:
        await redis_client.delete(cancel_key)
        return
    if reports:
        await _send_reports(bot, payload, reports, check_id)
        await _delete_status(bot, payload)
    else:
        await _update_status(bot, payload, "ℹ️ В материале не найдено проверяемых утверждений.")
    logger.info(
        "check_completed check_id=%s user_id_hash=%s sources=%d",
        check_id,
        hashlib.sha256(str(payload["telegram_id"]).encode()).hexdigest()[:12],
        source_count,
    )


async def main() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    consumer = f"{socket.gethostname()}-{os.getpid()}"
    session = AiohttpSession(proxy=settings.tg_proxy_url or None)
    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(link_preview_is_disabled=True),
    )
    try:
        while True:
            item = await job_queue.receive(consumer, settings.queue_block_ms)
            if item is None:
                continue
            message_id, payload = item
            retry_scheduled = False
            try:
                await process_job(bot, payload)
            except Exception as exc:
                attempt = int(payload.get("attempt", 0))
                check_id = int(payload["check_id"])
                if attempt < settings.job_max_retries:
                    retry_payload = {**payload, "attempt": attempt + 1}
                    await job_queue.enqueue(retry_payload)
                    retry_scheduled = True
                    logger.warning(
                        "check_retry check_id=%s attempt=%d error=%s",
                        check_id,
                        attempt + 1,
                        type(exc).__name__,
                    )
                else:
                    await persistence_service.fail(check_id, type(exc).__name__)
                    await _update_status(
                        bot,
                        payload,
                        _failure_message(exc),
                    )
                    logger.exception("check_failed check_id=%s", check_id)
            finally:
                dedupe_key = payload.get("dedupe_key")
                if _should_release_dedupe(retry_scheduled) and isinstance(dedupe_key, str):
                    await redis_client.delete(dedupe_key)
                await job_queue.acknowledge(message_id)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
