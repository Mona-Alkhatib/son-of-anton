from __future__ import annotations

import uuid
from typing import Any

from oracle.llm import LLMResult
from oracle.prompts import RenderedPrompt

_INSERT_LLM = """
insert into audit_llm_calls
    (request_id, incident_id, prompt_name, prompt_version, model,
     tokens_in, tokens_out, cost_usd, latency_ms, cache_read, error)
values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
on conflict (request_id) do nothing
""".strip()


class AuditWriter:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def record_llm_call(
        self,
        *,
        prompt: RenderedPrompt,
        result: LLMResult | None,
        error: str | None,
        incident_id: str | None = None,
    ) -> None:
        request_id = result.request_id if result is not None else f"err-{uuid.uuid4().hex[:12]}"
        model = result.model if result is not None else str(prompt.metadata.get("model"))
        async with self._pool.acquire() as conn:
            await conn.execute(
                _INSERT_LLM,
                request_id,
                incident_id,
                prompt.metadata["prompt_name"],
                str(prompt.metadata["prompt_version"]),
                model,
                result.tokens_in if result else 0,
                result.tokens_out if result else 0,
                result.cost_usd if result else 0.0,
                result.latency_ms if result else 0,
                result.cache_read if result else False,
                error,
            )

    def as_gateway_callable(self) -> Any:
        async def _cb(**kwargs: Any) -> None:
            await self.record_llm_call(
                prompt=kwargs["prompt"],
                result=kwargs.get("result"),
                error=kwargs.get("error"),
                incident_id=(kwargs.get("extra_context") or {}).get("incident_id"),
            )

        return _cb
