from app.config import Settings


def test_settings_loads_environment(monkeypatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("MAX_INPUT_LENGTH", "100")
    loaded = Settings()
    assert loaded.bot_token == "test-token"
    assert loaded.anthropic_api_key == "test-key"
    assert loaded.anthropic_model == "claude-haiku-5.5"
    assert loaded.max_input_length == 100


def test_settings_loads_telegram_proxy() -> None:
    loaded = Settings(BOT_TOKEN="test-token", TG_PROXY_URL="http://proxy:8080")

    assert loaded.tg_proxy_url == "http://proxy:8080"


def test_external_proxy_is_configurable() -> None:
    loaded = Settings(
        BOT_TOKEN="test-token",
        TG_PROXY_URL="socks5://telegram-proxy:1080",
        EXTERNAL_PROXY_URL="socks5://external-proxy:1080",
    )

    assert loaded.external_proxy_url == "socks5://external-proxy:1080"


def test_search_proxy_is_optional() -> None:
    loaded = Settings(BOT_TOKEN="test-token", SEARCH_PROXY_URL="")

    assert loaded.search_proxy_url == ""
