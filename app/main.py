import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from app.bot.handlers import router
from app.config import settings


async def main() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    session = AiohttpSession(proxy=settings.tg_proxy_url or None)
    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(link_preview_is_disabled=True),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
