import os

import asyncpg
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


REQUIRED_TABLES = {
    "incidents",
    "agent_trajectories",
    "tool_calls",
    "proposed_actions",
    "approvals",
    "audit_llm_calls",
    "slack_installations",
    "schema_migrations",
}


async def test_all_tables_exist() -> None:
    dsn = os.environ["DATABASE_URL"]
    conn = await asyncpg.connect(dsn=dsn)
    try:
        rows = await conn.fetch("select tablename from pg_tables where schemaname = 'public'")
    finally:
        await conn.close()
    tables = {r["tablename"] for r in rows}
    missing = REQUIRED_TABLES - tables
    assert not missing, f"missing tables: {missing}"
