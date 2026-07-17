import os

import asyncpg
import pytest

from oracle.audit import AuditWriter
from oracle.llm import LLMGateway
from oracle.retrieval.stub import StubRetriever
from oracle.service import OracleService
from oracle.types import Caller

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.needs_llm]


async def test_ask_end_to_end_writes_audit_row() -> None:
    dsn = os.environ["DATABASE_URL"]
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "insert into incidents (id, source, question) values ($1, $2, $3) "
                "on conflict (id) do nothing",
                "INC-e2e-phase1",
                "cli",
                "in one sentence: what is dbt?",
            )

        writer = AuditWriter(pool=pool)
        gateway = LLMGateway(audit_writer=writer.as_gateway_callable())
        svc = OracleService(llm=gateway, retriever=StubRetriever())

        resp = await svc.ask(
            "in one sentence: what is dbt?",
            incident_id="INC-e2e-phase1",
            caller=Caller(source="cli", identity="e2e-test"),
        )

        assert resp.incident_id == "INC-e2e-phase1"
        assert len(resp.answer_md.strip()) > 0

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "select * from audit_llm_calls where incident_id = $1 "
                "order by created_at desc limit 1",
                "INC-e2e-phase1",
            )

        assert row is not None
        assert row["prompt_name"] == "generic"
        assert row["tokens_out"] > 0
        assert row["cost_usd"] >= 0.0
        assert row["error"] is None
    finally:
        await pool.close()
