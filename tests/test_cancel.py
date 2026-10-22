from app.bot.handlers import cancel_handler


def test_cancel_command_handler_exists() -> None:
    assert cancel_handler.__name__ == "cancel_handler"
