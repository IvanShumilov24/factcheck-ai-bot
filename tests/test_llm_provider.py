import pytest

from app.config import Settings
from app.services.llm.provider import AnthropicLLMProvider, UnconfiguredLLMProvider
from app.services.ports import ClaimExtractionRequest


@pytest.mark.asyncio
async def test_unconfigured_llm_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="not configured"):
        await UnconfiguredLLMProvider().extract_claims(None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_anthropic_provider_validates_tool_response(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "content": [
                    {
                        "type": "tool_use",
                        "input": {"claims": []},
                    }
                ]
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: FakeClient())
    result = await AnthropicLLMProvider(Settings(ANTHROPIC_API_KEY="key")).extract_claims(
        ClaimExtractionRequest(text="text", source_type="TEXT", title=None, system_prompt="system")
    )
    assert result.claims == []
