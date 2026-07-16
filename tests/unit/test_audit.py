from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from oracle.audit import AuditWriter
from oracle.llm import LLMResult
from oracle.prompts import RenderedPrompt


@pytest.fixture
def rendered() -> RenderedPrompt:
    return RenderedPrompt(
        system="s",
        user="u",
        metadata={
            "prompt_name": "generic",
            "prompt_version": 1,
            "model": "claude-sonnet-4-6",
            "temperature": 0.2,
            "max_tokens": 128,
            "tools": [],
        },
    )


@pytest.mark.asyncio
async def test_record_llm_call_success(rendered: RenderedPrompt) -> None:
    conn = AsyncMock()
    pool_ctx = AsyncMock()
    pool_ctx.__aenter__.return_value = conn
    pool_ctx.__aexit__.return_value = None
    pool = SimpleNamespace(acquire=lambda: pool_ctx)

    writer = AuditWriter(pool=pool)
    result = LLMResult(
        text="ok",
        tokens_in=10,
        tokens_out=5,
        cost_usd=0.001,
        latency_ms=42,
        cache_read=False,
        model="claude-sonnet-4-6",
        request_id="req_abc",
    )
    await writer.record_llm_call(prompt=rendered, result=result, error=None, incident_id="INC-1")

    conn.execute.assert_awaited_once()
    sql, *params = conn.execute.await_args.args
    assert "insert into audit_llm_calls" in sql.lower()
    assert "req_abc" in params
