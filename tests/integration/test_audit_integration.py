import os

import asyncpg
import pytest

from oracle.audit import AuditWriter
from oracle.llm import LLMResult
from oracle.prompts import RenderedPrompt

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def pool():
    dsn = os.environ["DATABASE_URL"]
    p = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
    yield p
    await p.close()


async def test_round_trip(pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "insert into incidents (id, source, question) values ($1, $2, $3) "
            "on conflict (id) do nothing",
            "INC-audit-test",
            "cli",
            "why is fct_orders stale?",
        )

    writer = AuditWriter(pool=pool)
    rendered = RenderedPrompt(
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
    result = LLMResult(
        text="hi",
        tokens_in=5,
        tokens_out=2,
        cost_usd=0.0001,
        latency_ms=10,
        cache_read=False,
        model="claude-sonnet-4-6",
        request_id="req_integration_1",
    )
    await writer.record_llm_call(
        prompt=rendered, result=result, error=None, incident_id="INC-audit-test"
    )

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select * from audit_llm_calls where request_id = $1", "req_integration_1"
        )

    assert row is not None
    assert row["prompt_name"] == "generic"
    assert row["tokens_in"] == 5
    assert row["cache_read"] is False
