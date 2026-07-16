from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import litellm
from litellm import acompletion
from pydantic import BaseModel, ConfigDict
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from oracle.prompts import RenderedPrompt

AuditWriter = Callable[..., Awaitable[None]]


class LLMResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    cache_read: bool
    model: str
    request_id: str


_RETRYABLE = (
    litellm.exceptions.RateLimitError,
    litellm.exceptions.APIConnectionError,
)


class LLMGateway:
    def __init__(
        self,
        audit_writer: AuditWriter | None = None,
    ) -> None:
        self._audit = audit_writer

    async def complete(
        self,
        prompt: RenderedPrompt,
        *,
        model_override: str | None = None,
        extra_context: dict[str, Any] | None = None,
    ) -> LLMResult:
        model = model_override or prompt.metadata["model"]
        messages = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": prompt.system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            },
            {"role": "user", "content": prompt.user},
        ]

        started = time.perf_counter()
        error: str | None = None
        result: LLMResult | None = None
        try:
            resp = await _call_with_retry(
                model=model,
                messages=messages,
                temperature=prompt.metadata["temperature"],
                max_tokens=prompt.metadata["max_tokens"],
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            text = resp.choices[0].message.content or ""
            usage = getattr(resp, "usage", None)
            tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
            tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
            cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0) > 0
            try:
                cost = float(litellm.completion_cost(completion_response=resp) or 0.0)
            except Exception:
                cost = 0.0
            request_id = getattr(resp, "id", None) or f"resp_{uuid.uuid4().hex[:12]}"
            result = LLMResult(
                text=text,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost,
                latency_ms=latency_ms,
                cache_read=cache_read,
                model=str(getattr(resp, "model", model)),
                request_id=request_id,
            )
            return result
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            if self._audit is not None:
                await self._audit(
                    prompt=prompt,
                    result=result,
                    error=error,
                    extra_context=extra_context or {},
                )


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
    retry=retry_if_exception_type(_RETRYABLE),
)
async def _call_with_retry(**kwargs: Any) -> Any:
    return await acompletion(**kwargs)


__all__ = ["LLMGateway", "LLMResult", "RetryError"]
