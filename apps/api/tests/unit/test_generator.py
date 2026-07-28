"""Generator: request options (incl. num_predict cap) and timing parsing.

No Ollama needed — httpx.AsyncClient.post is monkeypatched to capture the
outgoing payload and return a canned Ollama response.
"""

import httpx
import pytest

from app.core.config import get_settings
from app.services.rag import generator

_OLLAMA_RESPONSE = {
    "message": {"content": "  Grounded answer [S1].  "},
    "total_duration": 2_000_000_000,  # 2 s in ns
    "prompt_eval_count": 1200,
    "eval_count": 100,
    "eval_duration": 10_000_000_000,  # 10 s in ns -> 10 tok/s
}


class _FakeResponse:
    def raise_for_status(self) -> None:  # noqa: D401
        pass

    def json(self) -> dict:
        return _OLLAMA_RESPONSE


@pytest.fixture
def captured_payload(monkeypatch):
    captured: dict = {}

    async def _fake_post(self, url, json):  # noqa: ANN001
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    return captured


async def test_generate_sends_cpu_options_and_num_predict(captured_payload):
    settings = get_settings()
    result = await generator.generate("SYSTEM", "USER")

    options = captured_payload["json"]["options"]
    assert options["temperature"] == 0
    assert options["num_ctx"] == settings.ollama_num_ctx
    assert options["num_thread"] == settings.ollama_num_thread
    # num_predict is always sent; -1 (unlimited) by default until Week 2 tuning.
    assert options["num_predict"] == settings.ollama_num_predict

    # System prompt is the first message (stable -> prefix cache).
    messages = captured_payload["json"]["messages"]
    assert messages[0] == {"role": "system", "content": "SYSTEM"}
    assert messages[1] == {"role": "user", "content": "USER"}
    assert captured_payload["json"]["stream"] is False

    # Timing counters are parsed and units converted (ns -> ms, tok/s).
    assert result.text == "Grounded answer [S1]."
    assert result.latency_ms == 2000
    assert result.prompt_tokens == 1200
    assert result.completion_tokens == 100
    assert result.tokens_per_second == 10.0


async def test_generate_honours_num_predict_override(captured_payload, monkeypatch):
    monkeypatch.setattr(get_settings(), "ollama_num_predict", 256)
    await generator.generate("SYSTEM", "USER")
    assert captured_payload["json"]["options"]["num_predict"] == 256


async def test_generate_uses_explicit_model(captured_payload):
    result = await generator.generate("SYSTEM", "USER", model="qwen3:1.7b")
    assert captured_payload["json"]["model"] == "qwen3:1.7b"
    assert result.model_used == "qwen3:1.7b"


async def test_empty_generation_raises(monkeypatch):
    async def _fake_post(self, url, json):  # noqa: ANN001
        class _Empty(_FakeResponse):
            def json(self) -> dict:
                return {"message": {"content": ""}}

        return _Empty()

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    with pytest.raises(generator.GenerationError):
        await generator.generate("SYSTEM", "USER")
