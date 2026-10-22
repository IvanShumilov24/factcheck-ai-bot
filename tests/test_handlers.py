from app.bot.handlers import router


def test_bot_router_is_configured() -> None:
    assert router.message.handlers
