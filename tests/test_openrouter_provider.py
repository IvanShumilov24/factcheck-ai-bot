import json

import httpx
import pytest

from app.config import Settings
from app.domain.evidence import EvidenceAnalysisResponse
from app.services.llm.provider import OpenRouterLLMProvider
from app.services.ports import ClaimExtractionRequest, EvidenceAnalysisRequest


class FakeResponse:
    status_code = 200

    def json(self):
        return {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "arguments": json.dumps({"claims": []}),
                                }
                            }
                        ]
                    }
                }
            ]
        }


class FakeClient:
    request = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        self.request = {"url": url, **kwargs}
        FakeClient.request = self.request
        return FakeResponse()


@pytest.mark.asyncio
async def test_openrouter_uses_bearer_and_chat_completions(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: FakeClient())
    provider = OpenRouterLLMProvider(
        Settings(OPENROUTER_API_KEY="sk-or-v1-test", OPENROUTER_MODEL="anthropic/test")
    )

    result = await provider.extract_claims(
        ClaimExtractionRequest(text="text", source_type="TEXT", title=None, system_prompt="system")
    )

    assert result.claims == []
    assert FakeClient.request["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert FakeClient.request["headers"]["authorization"] == "Bearer sk-or-v1-test"
    assert FakeClient.request["json"]["model"] == "anthropic/test"
    assert FakeClient.request["json"]["tools"][0]["type"] == "function"


@pytest.mark.asyncio
async def test_openrouter_adds_claim_id_to_evidence_analysis(monkeypatch) -> None:
    provider = OpenRouterLLMProvider(Settings(OPENROUTER_API_KEY="key"))

    async def fake_structured(*args, **kwargs):
        return EvidenceAnalysisResponse()

    monkeypatch.setattr(provider, "_structured_request", fake_structured)
    result = await provider.analyze_evidence(
        EvidenceAnalysisRequest(
            claim_id="claim-42",
            claim_text="claim",
            evidence=[],
            source_metadata=[],
            system_prompt="system",
        )
    )

    assert result.claim_id == "claim-42"
