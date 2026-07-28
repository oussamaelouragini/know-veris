"""Answer generation via Ollama (Qwen3), blocking and streaming.

Qwen3 4B Instruct 2507, `temperature=0` always (ADR-003, conventions). The
CPU-critical options live here: `num_ctx=4096` bounds the KV cache, `num_thread`
pins the Zen-2 cores, `num_predict` optionally caps the answer length.

Two entry points share one payload:
* `generate` — blocks for the full answer (used by tests, eval, non-SSE callers).
* `stream_generate` — yields token deltas as Ollama produces them, then a final
  chunk carrying the assembled text + timing counters. SSE streaming is about
  *perceived* latency: first token in a few seconds instead of a blank minute.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

settings = get_settings()

_CHAT_ENDPOINT = "/api/chat"
# Generation on CPU is slow (prefill dominates, 30-45 s) — budget generously.
_TIMEOUT = httpx.Timeout(300.0, connect=5.0)


class GenerationError(RuntimeError):
    """Raised when Ollama returns no / malformed generation output."""


@dataclass
class GenerationResult:
    text: str
    model_used: str
    latency_ms: int
    prompt_tokens: int | None  # prefill token count (the CPU bottleneck)
    completion_tokens: int | None
    tokens_per_second: float | None  # generation throughput, for the benchmark


@dataclass
class StreamChunk:
    """One streamed step: an incremental `delta`, or the terminal chunk (`done`)."""

    delta: str
    done: bool
    result: GenerationResult | None = None  # populated only on the terminal chunk


def _build_payload(system_prompt: str, user_prompt: str, model: str, *, stream: bool) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": stream,
        "options": {
            "temperature": 0,
            "num_ctx": settings.ollama_num_ctx,
            "num_thread": settings.ollama_num_thread,
            # -1 = unlimited (off); a positive cap bounds generation time.
            "num_predict": settings.ollama_num_predict,
        },
    }


def _result_from(data: dict, text: str, model: str) -> GenerationResult:
    """Build a GenerationResult from an Ollama response object (ns → ms, tok/s)."""
    total_ns = data.get("total_duration") or 0
    eval_count = data.get("eval_count")
    eval_ns = data.get("eval_duration")
    tps = (eval_count / (eval_ns / 1e9)) if eval_count and eval_ns else None
    return GenerationResult(
        text=text,
        model_used=model,
        latency_ms=int(total_ns / 1e6),
        prompt_tokens=data.get("prompt_eval_count"),
        completion_tokens=eval_count,
        tokens_per_second=round(tps, 2) if tps is not None else None,
    )


async def generate(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
) -> GenerationResult:
    """Generate a full (non-streamed) answer and report its timing counters."""
    used_model = model or settings.ollama_generation_model
    payload = _build_payload(system_prompt, user_prompt, used_model, stream=False)

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(f"{settings.ollama_url}{_CHAT_ENDPOINT}", json=payload)
        response.raise_for_status()
        data = response.json()

    text = (data.get("message") or {}).get("content")
    if not text:
        raise GenerationError("Ollama returned an empty generation")
    return _result_from(data, text.strip(), used_model)


async def stream_generate(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
) -> AsyncIterator[StreamChunk]:
    """Yield token deltas as they arrive, then a terminal chunk with the result."""
    used_model = model or settings.ollama_generation_model
    payload = _build_payload(system_prompt, user_prompt, used_model, stream=True)

    async with (
        httpx.AsyncClient(timeout=_TIMEOUT) as client,
        client.stream("POST", f"{settings.ollama_url}{_CHAT_ENDPOINT}", json=payload) as response,
    ):
        response.raise_for_status()
        parts: list[str] = []
        async for line in response.aiter_lines():
            if not line.strip():
                continue
            data = json.loads(line)
            delta = (data.get("message") or {}).get("content", "")
            if delta:
                parts.append(delta)
                yield StreamChunk(delta=delta, done=False)
            if data.get("done"):
                text = "".join(parts).strip()
                if not text:
                    raise GenerationError("Ollama returned an empty generation")
                yield StreamChunk(delta="", done=True, result=_result_from(data, text, used_model))
