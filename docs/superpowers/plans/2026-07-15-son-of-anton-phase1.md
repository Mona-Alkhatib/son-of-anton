# Son of Anton Phase 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working `anton ask` end-to-end path: CLI receives a question, `AntonService` loads a prompt from the registry, LiteLLM gateway calls Claude with instrumentation, results are persisted to a Postgres audit log, and the answer streams back to the terminal. Read-only, single generic specialist, stub retriever.

**Architecture:** Foundation layer of the design spec. Every downstream phase (retrieval, multi-agent, adapters, Slack) plugs into the interfaces defined here. Layout follows spec Section 15.

**Tech Stack:** Python 3.11+, uv, Pydantic v2, Typer, LiteLLM, Anthropic Claude Sonnet 4.6, Postgres 16-alpine, dbmate migrations, pytest, docker compose, tenacity, structlog.

## Global Constraints

- No em-dashes (`—`) or en-dashes (`–`) anywhere in code, docs, YAML, prompts, or commit messages. Use `-`, `:`, or restructure. Feedback preference.
- All git commits authored as `Mona Alkhatib <muna.alkhateeb@gmail.com>`. No Claude co-author trailer. Repo config already set at init time; verify per commit.
- Python `>=3.11,<3.13`. Pydantic v2. Typer for the CLI. Ruff + mypy strict for linting and typing.
- Postgres 16-alpine. `dbmate` for schema migrations, one SQL file per table under `migrations/`.
- Every LLM call routes through `anton.llm.LLMGateway`. Direct `anthropic.Anthropic(...)` calls are forbidden.
- Every prompt lives in `prompts/*.yaml` and is loaded via `anton.prompts.load(name, version=...)`. No inline f-string prompts.
- Every LLM call writes exactly one row to `audit_llm_calls` with the schema from spec Section 11.
- All Pydantic models derive from `anton.types.OracleModel` (a common base with `model_config = ConfigDict(frozen=True, extra="forbid")`).
- Tests use `pytest`. Unit tests never touch Postgres or Anthropic. Integration tests run against real docker-compose services; skipped without `ANTHROPIC_API_KEY`.
- Every task ends with a commit. Prefer conventional-commit prefixes (`feat:`, `test:`, `chore:`, `docs:`).

---

## File Structure

Phase 1 produces these files (create unless marked `exists`):

```
son-of-anton/
├── .gitignore                                (exists)
├── .env.example
├── README.md
├── Makefile
├── pyproject.toml
├── uv.lock                                   (generated)
├── docker-compose.yml
├── config/
│   └── settings.example.yaml
├── prompts/
│   └── generic.v1.yaml
├── migrations/
│   ├── 20260715120000_create_incidents.sql
│   ├── 20260715120100_create_agent_trajectories.sql
│   ├── 20260715120200_create_tool_calls.sql
│   ├── 20260715120300_create_proposed_actions.sql
│   ├── 20260715120400_create_approvals.sql
│   ├── 20260715120500_create_audit_llm_calls.sql
│   └── 20260715120600_create_slack_installations.sql
├── anton/
│   ├── __init__.py
│   ├── config.py                             # Settings loader
│   ├── types.py                              # Pydantic domain types
│   ├── prompts.py                            # Prompt registry
│   ├── llm.py                                # LiteLLM gateway
│   ├── audit.py                              # Postgres audit writer
│   ├── db.py                                 # asyncpg pool + helpers
│   ├── retrieval/
│   │   ├── __init__.py
│   │   ├── base.py                           # Retriever protocol
│   │   └── stub.py                           # No-op retriever for Phase 1
│   ├── service.py                            # AntonService orchestrator
│   └── cli.py                                # Typer CLI
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_config.py
│   │   ├── test_types.py
│   │   ├── test_prompts.py
│   │   ├── test_llm.py
│   │   ├── test_audit.py
│   │   ├── test_retrieval_stub.py
│   │   └── test_service.py
│   └── integration/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_db_migrations.py
│       └── test_e2e_phase1.py
└── docs/superpowers/
    ├── specs/2026-07-15-son-of-anton-design.md   (exists)
    └── plans/2026-07-15-son-of-anton-phase1.md   (this file)
```

Split rationale: `db.py` isolates connection-pool + row-mapping concerns from the audit-writing intent (`audit.py`); `retrieval/` gets its own package because Phase 2 will fill it with Qdrant + BM25 + rerank without touching `service.py`.

---

## Task 1: Project scaffold + tooling

**Files:**
- Create: `pyproject.toml`, `README.md`, `Makefile`, `.env.example`, `anton/__init__.py`, `tests/__init__.py`, `tests/conftest.py`
- Test: `tests/unit/test_scaffold.py` (temporary sanity test, removed at task end)

**Interfaces:**
- Consumes: nothing
- Produces: a `uv sync`-able project with `ruff`, `mypy`, `pytest` runnable; import path `anton.*` resolves.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "son-of-anton"
version = "0.1.0-phase1"
description = "Multi-agent AI on-call assistant for data teams"
readme = "README.md"
requires-python = ">=3.11,<3.13"
authors = [{ name = "Mona Alkhatib", email = "muna.alkhateeb@gmail.com" }]
dependencies = [
    "pydantic>=2.9,<3",
    "pydantic-settings>=2.6,<3",
    "typer>=0.15,<0.16",
    "litellm>=1.55,<2",
    "anthropic>=0.42,<1",
    "tenacity>=9,<10",
    "structlog>=24.4,<25",
    "asyncpg>=0.30,<0.31",
    "pyyaml>=6.0,<7",
    "orjson>=3.10,<4",
]

[project.optional-dependencies]
dev = [
    "pytest>=8,<9",
    "pytest-asyncio>=0.24,<0.25",
    "pytest-cov>=5,<6",
    "ruff>=0.7,<0.8",
    "mypy>=1.13,<2",
    "types-PyYAML",
]

[project.scripts]
anton = "anton.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["anton"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "A", "C4", "SIM", "RUF"]

[tool.mypy]
python_version = "3.11"
strict = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "integration: requires docker-compose stack + optional ANTHROPIC_API_KEY",
]
```

- [ ] **Step 2: Write `.env.example`**

```
# Copy to .env and fill in.
ANTHROPIC_API_KEY=
DATABASE_URL=postgres://anton:anton@localhost:5432/anton?sslmode=disable
ANTON_LOG_LEVEL=INFO
```

- [ ] **Step 3: Write `Makefile`**

```
.PHONY: install lint typecheck test test-integration db-up db-migrate demo

install:
	uv sync --all-extras

lint:
	uv run ruff check anton tests
	uv run ruff format --check anton tests

typecheck:
	uv run mypy anton

test:
	uv run pytest tests/unit -v

test-integration:
	uv run pytest tests/integration -v -m integration

db-up:
	docker compose up -d postgres --wait

db-migrate: db-up
	dbmate --url "$$DATABASE_URL" --migrations-dir migrations up
```

- [ ] **Step 4: Write a minimal `README.md`**

```markdown
# Son of Anton

Multi-agent AI on-call assistant for data teams. Phase 1 in progress; see `docs/superpowers/plans/`.

## Development

```
make install
make lint typecheck test
```
```

- [ ] **Step 5: Create empty package files**

```
touch anton/__init__.py tests/__init__.py
```

`tests/conftest.py`:

```python
import pytest


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"
```

- [ ] **Step 6: Write a sanity test**

`tests/unit/test_scaffold.py`:

```python
import anton


def test_package_imports() -> None:
    assert anton.__name__ == "anton"
```

- [ ] **Step 7: Run lint + typecheck + test**

```
uv sync --all-extras
make lint typecheck test
```

Expected: all pass. If `ruff format --check` complains, run `uv run ruff format anton tests`.

- [ ] **Step 8: Commit**

```
git add pyproject.toml README.md Makefile .env.example anton/__init__.py \
        tests/__init__.py tests/conftest.py tests/unit/test_scaffold.py
git -c user.name="Mona Alkhatib" -c user.email=muna.alkhateeb@gmail.com \
    commit -m "chore: project scaffold with uv, ruff, mypy, pytest"
```

---

## Task 2: Settings loader

**Files:**
- Create: `anton/config.py`, `config/settings.example.yaml`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Settings` dataclass loaded via `get_settings()`. Fields: `database_url: str`, `anthropic_api_key: SecretStr`, `openai_api_key: SecretStr | None`, `log_level: Literal["DEBUG","INFO","WARNING","ERROR"]`, `default_model: str`, `per_incident_budget_usd: float`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_config.py`:

```python
from pydantic import SecretStr

from anton.config import Settings


def test_settings_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("DATABASE_URL", "postgres://x:y@localhost/z")
    monkeypatch.setenv("ANTON_LOG_LEVEL", "DEBUG")

    s = Settings()

    assert s.anthropic_api_key.get_secret_value() == "sk-ant-test"
    assert s.database_url == "postgres://x:y@localhost/z"
    assert s.log_level == "DEBUG"
    assert s.default_model == "claude-sonnet-4-6"
    assert s.per_incident_budget_usd == 0.50


def test_settings_missing_required_raises(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import pytest

    with pytest.raises(Exception):
        Settings()
```

- [ ] **Step 2: Run test, expect FAIL**

```
uv run pytest tests/unit/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'anton.config'`.

- [ ] **Step 3: Implement `anton/config.py`**

```python
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    anthropic_api_key: SecretStr
    openai_api_key: SecretStr | None = None
    database_url: str
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", alias="ANTON_LOG_LEVEL"
    )
    default_model: str = "claude-sonnet-4-6"
    per_incident_budget_usd: float = 0.50


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Write example YAML for reference (not used by loader)**

`config/settings.example.yaml`:

```yaml
# Reference only. Real settings load from environment variables.
# See .env.example for the runtime configuration.
default_model: claude-sonnet-4-6
per_incident_budget_usd: 0.50
log_level: INFO
```

- [ ] **Step 5: Run tests, expect PASS**

```
uv run pytest tests/unit/test_config.py -v
```

- [ ] **Step 6: Commit**

```
git add anton/config.py config/settings.example.yaml tests/unit/test_config.py
git -c user.name="Mona Alkhatib" -c user.email=muna.alkhateeb@gmail.com \
    commit -m "feat: settings loader with pydantic-settings"
```

---

## Task 3: Docker compose (Postgres only for Phase 1)

**Files:**
- Create: `docker-compose.yml`
- Test: manual smoke via Makefile target

**Interfaces:**
- Consumes: nothing
- Produces: `docker compose up postgres --wait` yields a Postgres 16 instance at `localhost:5432` with database `anton`, user `anton`, password `anton`.

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: anton
      POSTGRES_PASSWORD: anton
      POSTGRES_DB: anton
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "anton", "-d", "anton"]
      interval: 2s
      timeout: 3s
      retries: 15

volumes:
  postgres_data:
```

- [ ] **Step 2: Bring up Postgres and verify**

```
docker compose up -d postgres --wait
docker compose exec postgres psql -U anton -d anton -c "select 1;"
```

Expected: `?column? | 1`.

- [ ] **Step 3: Bring it down (for cleanliness)**

```
docker compose down
```

- [ ] **Step 4: Commit**

```
git add docker-compose.yml
git -c user.name="Mona Alkhatib" -c user.email=muna.alkhateeb@gmail.com \
    commit -m "chore: postgres 16 compose service"
```

---

## Task 4: Database schema and migrations

**Files:**
- Create: `migrations/20260715120000_create_incidents.sql` through `migrations/20260715120600_create_slack_installations.sql`
- Test: `tests/integration/test_db_migrations.py`

**Interfaces:**
- Consumes: `Settings.database_url` from Task 2.
- Produces: seven tables (spec Section 11) applied to the database. `dbmate up` + `dbmate down` are both clean.

**Prerequisite:** `dbmate` installed locally (`brew install dbmate` on macOS, `apt install dbmate` on Linux) OR run via Docker as documented in Step 6.

- [ ] **Step 1: Write the failing integration test**

`tests/integration/test_db_migrations.py`:

```python
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
        rows = await conn.fetch(
            "select tablename from pg_tables where schemaname = 'public'"
        )
    finally:
        await conn.close()
    tables = {r["tablename"] for r in rows}
    missing = REQUIRED_TABLES - tables
    assert not missing, f"missing tables: {missing}"
```

- [ ] **Step 2: Run test, expect FAIL**

```
make db-up
uv run pytest tests/integration/test_db_migrations.py -v -m integration
```

Expected: FAIL with `missing tables: {...}`.

- [ ] **Step 3: Write migration `20260715120000_create_incidents.sql`**

```sql
-- migrate:up
create table incidents (
    id text primary key,
    opened_at timestamptz not null default now(),
    closed_at timestamptz,
    source text not null,
    question text not null,
    status text not null default 'open',
    created_at timestamptz not null default now()
);

create index incidents_status_opened_at_idx on incidents (status, opened_at desc);

-- migrate:down
drop table incidents;
```

- [ ] **Step 4: Write migration `20260715120100_create_agent_trajectories.sql`**

```sql
-- migrate:up
create table agent_trajectories (
    id bigserial primary key,
    incident_id text not null references incidents(id) on delete cascade,
    stage text not null,
    agent text not null,
    prompt_name text not null,
    prompt_version text not null,
    request_id text not null,
    output_json jsonb not null,
    tokens_in integer not null default 0,
    tokens_out integer not null default 0,
    cost_usd numeric(10, 6) not null default 0,
    latency_ms integer not null default 0,
    started_at timestamptz not null,
    ended_at timestamptz not null,
    created_at timestamptz not null default now()
);

create index agent_trajectories_incident_id_idx
    on agent_trajectories (incident_id, started_at);

-- migrate:down
drop table agent_trajectories;
```

- [ ] **Step 5: Write migration `20260715120200_create_tool_calls.sql`**

```sql
-- migrate:up
create table tool_calls (
    id bigserial primary key,
    incident_id text not null references incidents(id) on delete cascade,
    agent text not null,
    tool_name text not null,
    args_json jsonb not null,
    result_json jsonb,
    dry_run boolean not null default true,
    idempotency_key text,
    started_at timestamptz not null,
    ended_at timestamptz,
    error text,
    created_at timestamptz not null default now(),
    unique (idempotency_key)
);

create index tool_calls_incident_id_idx on tool_calls (incident_id, started_at);

-- migrate:down
drop table tool_calls;
```

- [ ] **Step 6: Write migration `20260715120300_create_proposed_actions.sql`**

```sql
-- migrate:up
create table proposed_actions (
    id bigserial primary key,
    incident_id text not null references incidents(id) on delete cascade,
    action_json jsonb not null,
    write boolean not null,
    status text not null default 'pending',
    approved_by text,
    approved_at timestamptz,
    executed_at timestamptz,
    result_json jsonb,
    idempotency_key text,
    created_at timestamptz not null default now(),
    unique (idempotency_key)
);

create index proposed_actions_incident_id_status_idx
    on proposed_actions (incident_id, status);

-- migrate:down
drop table proposed_actions;
```

- [ ] **Step 7: Write migration `20260715120400_create_approvals.sql`**

```sql
-- migrate:up
create table approvals (
    ref text primary key,
    action_id bigint not null references proposed_actions(id) on delete cascade,
    channel text not null,
    requested_at timestamptz not null default now(),
    decided_at timestamptz,
    decision text,
    decided_by text
);

-- migrate:down
drop table approvals;
```

- [ ] **Step 8: Write migration `20260715120500_create_audit_llm_calls.sql`**

```sql
-- migrate:up
create table audit_llm_calls (
    request_id text primary key,
    incident_id text references incidents(id) on delete set null,
    prompt_name text not null,
    prompt_version text not null,
    model text not null,
    tokens_in integer not null default 0,
    tokens_out integer not null default 0,
    cost_usd numeric(10, 6) not null default 0,
    latency_ms integer not null default 0,
    cache_read boolean not null default false,
    error text,
    created_at timestamptz not null default now()
);

create index audit_llm_calls_incident_created_idx
    on audit_llm_calls (incident_id, created_at);

-- migrate:down
drop table audit_llm_calls;
```

- [ ] **Step 9: Write migration `20260715120600_create_slack_installations.sql`**

```sql
-- migrate:up
create table slack_installations (
    team_id text primary key,
    bot_token_enc bytea not null,
    installed_at timestamptz not null default now()
);

-- migrate:down
drop table slack_installations;
```

- [ ] **Step 10: Apply migrations**

If dbmate is installed locally:

```
export $(grep -v '^#' .env | xargs)   # loads DATABASE_URL etc.
dbmate --migrations-dir migrations up
```

Or via Docker (no local install):

```
docker run --rm --network host \
    -v "$(pwd)/migrations:/db/migrations" \
    -e DATABASE_URL="postgres://anton:anton@localhost:5432/anton?sslmode=disable" \
    amacneil/dbmate up
```

- [ ] **Step 11: Run integration test, expect PASS**

```
uv run pytest tests/integration/test_db_migrations.py -v -m integration
```

- [ ] **Step 12: Verify rollback works**

```
dbmate --migrations-dir migrations down                     # rolls back last
dbmate --migrations-dir migrations up                       # reapply
```

- [ ] **Step 13: Commit**

```
git add migrations/ tests/integration/test_db_migrations.py
git -c user.name="Mona Alkhatib" -c user.email=muna.alkhateeb@gmail.com \
    commit -m "feat: dbmate migrations for all 7 phase-1 tables"
```

---

## Task 5: Domain types

**Files:**
- Create: `anton/types.py`
- Test: `tests/unit/test_types.py`

**Interfaces:**
- Consumes: nothing
- Produces: Pydantic v2 models used by every subsequent task:
  - `OracleModel` (base): `model_config = ConfigDict(frozen=True, extra="forbid")`
  - `Caller { source: Literal["api","cli","ui","slack"], identity: str }`
  - `Citation { source_type: str, source_id: str, snippet: str, score: float | None }`
  - `ProposedAction { adapter: str, verb: str, args: dict[str, Any], write: bool, rationale: str }`
  - `ToolError { tool_name: str, message: str, retriable: bool }`
  - `RoutingDecision { specialist: Literal["freshness","dag_failure","schema_drift","general"], confidence: float, reasoning: str, hand_off_context: dict[str, Any] }`
  - `SpecialistFindings { specialist: str, root_cause_hypothesis: str, evidence: list[Citation], suggested_actions: list[ProposedAction] }`
  - `IncidentResponse { answer_md: str, citations: list[Citation], drafted_slack_post: str | None, drafted_actions: list[ProposedAction], incident_id: str, request_id: str }`
  - `ApprovalDecision { approved: bool, decided_by: str, decided_at: datetime, note: str | None }`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_types.py`:

```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from anton.types import (
    ApprovalDecision,
    Caller,
    Citation,
    IncidentResponse,
    ProposedAction,
    RoutingDecision,
    SpecialistFindings,
)


def test_caller_round_trip() -> None:
    c = Caller(source="cli", identity="mona@laptop")
    dumped = c.model_dump_json()
    assert Caller.model_validate_json(dumped) == c


def test_caller_rejects_unknown_source() -> None:
    with pytest.raises(ValidationError):
        Caller(source="mail", identity="x")


def test_frozen_model_cannot_mutate() -> None:
    c = Citation(source_type="runbook", source_id="r1.md", snippet="hi", score=0.5)
    with pytest.raises(ValidationError):
        c.snippet = "changed"   # type: ignore[misc]


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        Citation(
            source_type="runbook", source_id="r1.md", snippet="hi", score=0.5,
            bogus="nope",   # type: ignore[call-arg]
        )


def test_incident_response_defaults() -> None:
    r = IncidentResponse(
        answer_md="answer",
        citations=[],
        drafted_slack_post=None,
        drafted_actions=[],
        incident_id="INC-1",
        request_id="req-1",
    )
    assert r.drafted_slack_post is None
    assert r.drafted_actions == []


def test_routing_decision_confidence_bounds() -> None:
    ok = RoutingDecision(
        specialist="freshness", confidence=0.85, reasoning="r", hand_off_context={}
    )
    assert ok.confidence == 0.85
    with pytest.raises(ValidationError):
        RoutingDecision(
            specialist="freshness", confidence=1.5, reasoning="r", hand_off_context={}
        )


def test_specialist_findings_with_action() -> None:
    a = ProposedAction(
        adapter="airflow",
        verb="clear_task",
        args={"dag_id": "d", "task_id": "t", "run_id": "r"},
        write=True,
        rationale="skipped run",
    )
    f = SpecialistFindings(
        specialist="freshness",
        root_cause_hypothesis="missed run",
        evidence=[],
        suggested_actions=[a],
    )
    assert f.suggested_actions[0].write is True


def test_approval_decision() -> None:
    d = ApprovalDecision(
        approved=True, decided_by="mona", decided_at=datetime.now(UTC), note=None
    )
    assert d.approved
```

- [ ] **Step 2: Run tests, expect FAIL**

```
uv run pytest tests/unit/test_types.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `anton/types.py`**

```python
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Specialist = Literal["freshness", "dag_failure", "schema_drift", "general"]
CallerSource = Literal["api", "cli", "ui", "slack"]


class OracleModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Caller(OracleModel):
    source: CallerSource
    identity: str


class Citation(OracleModel):
    source_type: str
    source_id: str
    snippet: str
    score: float | None = None


class ProposedAction(OracleModel):
    adapter: str
    verb: str
    args: dict[str, Any]
    write: bool
    rationale: str


class ToolError(OracleModel):
    tool_name: str
    message: str
    retriable: bool


class RoutingDecision(OracleModel):
    specialist: Specialist
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    hand_off_context: dict[str, Any]


class SpecialistFindings(OracleModel):
    specialist: Specialist
    root_cause_hypothesis: str
    evidence: list[Citation]
    suggested_actions: list[ProposedAction]


class IncidentResponse(OracleModel):
    answer_md: str
    citations: list[Citation]
    drafted_slack_post: str | None
    drafted_actions: list[ProposedAction]
    incident_id: str
    request_id: str


class ApprovalDecision(OracleModel):
    approved: bool
    decided_by: str
    decided_at: datetime
    note: str | None
```

- [ ] **Step 4: Run tests, expect PASS**

```
uv run pytest tests/unit/test_types.py -v
```

- [ ] **Step 5: Commit**

```
git add anton/types.py tests/unit/test_types.py
git -c user.name="Mona Alkhatib" -c user.email=muna.alkhateeb@gmail.com \
    commit -m "feat: core pydantic domain types"
```

---

## Task 6: Prompt registry

**Files:**
- Create: `anton/prompts.py`, `prompts/generic.v1.yaml`
- Test: `tests/unit/test_prompts.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `Prompt` frozen model with fields `name: str`, `version: int`, `model: str`, `temperature: float`, `max_tokens: int`, `system: str`, `user_template: str`, `tools: list[str]`, `few_shots_path: str | None`, `context_recipe: dict[str, Any]`
  - `Prompt.render(**vars) -> RenderedPrompt` where `RenderedPrompt` has `system: str`, `user: str`, `metadata: dict[str, Any]`
  - `load(name: str, version: int | Literal["latest"] = "latest", *, root: Path | None = None) -> Prompt`
- Registry root defaults to `prompts/` at repo root; overridable for tests.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_prompts.py`:

```python
from pathlib import Path

import pytest

from anton.prompts import Prompt, load


@pytest.fixture
def prompt_root(tmp_path: Path) -> Path:
    root = tmp_path / "prompts"
    root.mkdir()
    (root / "sample.v1.yaml").write_text(
        """
name: sample
version: 1
model: claude-sonnet-4-6
temperature: 0.2
max_tokens: 1024
system: |
  You are a helpful assistant.
user_template: |
  Q: {question}
tools: []
context_recipe:
  top_k: 5
""".strip()
    )
    (root / "sample.v2.yaml").write_text(
        """
name: sample
version: 2
model: claude-sonnet-4-6
temperature: 0.1
max_tokens: 2048
system: |
  You are a helpful assistant (v2).
user_template: |
  Question: {question}
tools: []
context_recipe: {}
""".strip()
    )
    return root


def test_load_latest_version(prompt_root: Path) -> None:
    p = load("sample", root=prompt_root)
    assert p.version == 2
    assert p.temperature == 0.1


def test_load_specific_version(prompt_root: Path) -> None:
    p = load("sample", version=1, root=prompt_root)
    assert p.version == 1
    assert "helpful assistant." in p.system


def test_load_unknown_prompt(prompt_root: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load("nope", root=prompt_root)


def test_render_substitutes_vars(prompt_root: Path) -> None:
    p = load("sample", version=1, root=prompt_root)
    r = p.render(question="what feeds fct_orders?")
    assert "Q: what feeds fct_orders?" in r.user
    assert r.metadata["prompt_name"] == "sample"
    assert r.metadata["prompt_version"] == 1


def test_render_missing_var_raises(prompt_root: Path) -> None:
    p = load("sample", version=1, root=prompt_root)
    with pytest.raises(KeyError):
        p.render()


def test_prompt_frozen(prompt_root: Path) -> None:
    p = load("sample", root=prompt_root)
    with pytest.raises(Exception):
        p.temperature = 0.9   # type: ignore[misc]
```

- [ ] **Step 2: Run tests, expect FAIL**

```
uv run pytest tests/unit/test_prompts.py -v
```

- [ ] **Step 3: Implement `anton/prompts.py`**

```python
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

_DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "prompts"


class RenderedPrompt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    system: str
    user: str
    metadata: dict[str, Any]


class Prompt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: int
    model: str
    temperature: float = 0.2
    max_tokens: int = 2048
    system: str
    user_template: str
    tools: list[str] = Field(default_factory=list)
    few_shots_path: str | None = None
    context_recipe: dict[str, Any] = Field(default_factory=dict)

    def render(self, **vars: Any) -> RenderedPrompt:
        try:
            user = self.user_template.format(**vars)
        except KeyError as missing:
            raise KeyError(
                f"prompt {self.name}@v{self.version} missing template var: {missing}"
            ) from missing
        metadata = {
            "prompt_name": self.name,
            "prompt_version": self.version,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "tools": list(self.tools),
        }
        return RenderedPrompt(system=self.system, user=user, metadata=metadata)


def _resolve_root(root: Path | None) -> Path:
    return root if root is not None else _DEFAULT_ROOT


def load(
    name: str,
    version: int | Literal["latest"] = "latest",
    *,
    root: Path | None = None,
) -> Prompt:
    base = _resolve_root(root)
    if version == "latest":
        candidates = sorted(
            base.glob(f"{name}.v*.yaml"),
            key=lambda p: int(p.stem.split(".v")[-1]),
        )
        if not candidates:
            raise FileNotFoundError(f"no prompt named {name!r} under {base}")
        path = candidates[-1]
    else:
        path = base / f"{name}.v{version}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"prompt {name}@v{version} not found at {path}")

    data = yaml.safe_load(path.read_text())
    return Prompt.model_validate(data)
```

- [ ] **Step 4: Write the real Phase 1 prompt**

`prompts/generic.v1.yaml`:

```yaml
name: generic
version: 1
model: claude-sonnet-4-6
temperature: 0.2
max_tokens: 2048
system: |
  You are Son of Anton, an assistant for data engineers investigating incidents.

  Ground rules:
  - Answer plainly. Ask clarifying questions when the request is ambiguous.
  - When you do not know, say so. Never invent table names, DAG IDs, or column names.
  - Cite specific sources when the caller supplies them; otherwise say the answer is unsourced.
  - Keep answers concise: a two-sentence summary first, details after.

user_template: |
  Question:
  {question}

  Context available:
  {context}

tools: []
context_recipe:
  retrieval_scope: []
  top_k: 0
```

- [ ] **Step 5: Run tests, expect PASS**

```
uv run pytest tests/unit/test_prompts.py -v
```

- [ ] **Step 6: Commit**

```
git add anton/prompts.py prompts/generic.v1.yaml tests/unit/test_prompts.py
git -c user.name="Mona Alkhatib" -c user.email=muna.alkhateeb@gmail.com \
    commit -m "feat: yaml prompt registry with versioning"
```

---

## Task 7: LLM gateway

**Files:**
- Create: `anton/llm.py`
- Test: `tests/unit/test_llm.py`

**Interfaces:**
- Consumes: `RenderedPrompt` from Task 6, `Settings` from Task 2.
- Produces:
  - `LLMResult` frozen model: `text: str`, `tokens_in: int`, `tokens_out: int`, `cost_usd: float`, `latency_ms: int`, `cache_read: bool`, `model: str`, `request_id: str`
  - `LLMGateway` async class with `async def complete(prompt: RenderedPrompt, *, model_override: str | None = None, extra_context: dict[str, Any] | None = None) -> LLMResult`
  - Retry policy via `tenacity`: 3 attempts, exponential backoff on `litellm.exceptions.RateLimitError` and `litellm.exceptions.APIConnectionError`.
  - Cache directive: system prompt automatically wrapped in `cache_control: {"type": "ephemeral"}` (Anthropic prompt caching).

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_llm.py`:

```python
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from anton.llm import LLMGateway, LLMResult
from anton.prompts import RenderedPrompt


@pytest.fixture
def rendered() -> RenderedPrompt:
    return RenderedPrompt(
        system="You are helpful.",
        user="Q: is water wet?",
        metadata={
            "prompt_name": "sample",
            "prompt_version": 1,
            "model": "claude-sonnet-4-6",
            "temperature": 0.2,
            "max_tokens": 128,
            "tools": [],
        },
    )


def _fake_litellm_response(text: str = "yes") -> Any:
    class Msg:
        content = text

    class Choice:
        message = Msg()

    class Usage:
        prompt_tokens = 40
        completion_tokens = 5
        cache_read_input_tokens = 10

    class Resp:
        id = "resp_abc"
        model = "claude-sonnet-4-6"
        choices = [Choice()]
        usage = Usage()

    return Resp()


@pytest.mark.asyncio
async def test_complete_returns_result_and_writes_audit(rendered: RenderedPrompt) -> None:
    audit = AsyncMock()
    gw = LLMGateway(audit_writer=audit)

    with patch("anton.llm.acompletion", AsyncMock(return_value=_fake_litellm_response())):
        result = await gw.complete(rendered)

    assert isinstance(result, LLMResult)
    assert result.text == "yes"
    assert result.tokens_in == 40
    assert result.tokens_out == 5
    assert result.cache_read is True
    assert result.request_id.startswith("resp_")
    audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_complete_retries_on_rate_limit(rendered: RenderedPrompt) -> None:
    import litellm

    audit = AsyncMock()
    gw = LLMGateway(audit_writer=audit)

    call = AsyncMock(
        side_effect=[
            litellm.exceptions.RateLimitError(
                "rl", llm_provider="anthropic", model="claude-sonnet-4-6"
            ),
            _fake_litellm_response(),
        ]
    )
    with patch("anton.llm.acompletion", call):
        result = await gw.complete(rendered)

    assert result.text == "yes"
    assert call.await_count == 2


@pytest.mark.asyncio
async def test_complete_records_error_and_reraises(rendered: RenderedPrompt) -> None:
    import litellm

    audit = AsyncMock()
    gw = LLMGateway(audit_writer=audit)

    call = AsyncMock(
        side_effect=litellm.exceptions.APIError(
            status_code=500, message="boom", llm_provider="anthropic",
            model="claude-sonnet-4-6",
        )
    )
    with patch("anton.llm.acompletion", call):
        with pytest.raises(Exception):
            await gw.complete(rendered)

    audit.assert_awaited_once()
    args, kwargs = audit.await_args
    assert kwargs["error"] is not None or (args and args[-1] is not None)
```

- [ ] **Step 2: Run tests, expect FAIL**

```
uv run pytest tests/unit/test_llm.py -v
```

- [ ] **Step 3: Implement `anton/llm.py`**

```python
from __future__ import annotations

import time
import uuid
from typing import Any, Awaitable, Callable

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

from anton.prompts import RenderedPrompt

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
            cost = float(
                litellm.completion_cost(completion_response=resp) or 0.0
            )
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
```

- [ ] **Step 4: Run tests, expect PASS**

```
uv run pytest tests/unit/test_llm.py -v
```

- [ ] **Step 5: Commit**

```
git add anton/llm.py tests/unit/test_llm.py
git -c user.name="Mona Alkhatib" -c user.email=muna.alkhateeb@gmail.com \
    commit -m "feat: LiteLLM gateway with cache_control, retries, cost tracking"
```

---

## Task 8: Postgres helper + audit writer

**Files:**
- Create: `anton/db.py`, `anton/audit.py`
- Test: `tests/unit/test_audit.py`, `tests/integration/test_audit_integration.py`

**Interfaces:**
- Consumes: `Settings.database_url` (Task 2), `LLMResult`, `RenderedPrompt`.
- Produces:
  - `anton.db.pool()` returning a cached `asyncpg.Pool`; `anton.db.close_pool()` for teardown.
  - `AuditWriter` class with `async def record_llm_call(*, prompt: RenderedPrompt, result: LLMResult | None, error: str | None, incident_id: str | None = None) -> None` matching the callable shape `anton.llm.LLMGateway` expects.
  - The class exposes `.callable` returning an `AuditWriter`-compatible partial for wiring into the gateway.

- [ ] **Step 1: Write the unit test (uses a fake pool)**

`tests/unit/test_audit.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from anton.audit import AuditWriter
from anton.llm import LLMResult
from anton.prompts import RenderedPrompt


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
    await writer.record_llm_call(
        prompt=rendered, result=result, error=None, incident_id="INC-1"
    )

    conn.execute.assert_awaited_once()
    sql, *params = conn.execute.await_args.args
    assert "insert into audit_llm_calls" in sql.lower()
    assert "req_abc" in params
```

- [ ] **Step 2: Run test, expect FAIL**

```
uv run pytest tests/unit/test_audit.py -v
```

- [ ] **Step 3: Implement `anton/db.py`**

```python
from __future__ import annotations

import asyncpg

from anton.config import get_settings

_pool: asyncpg.Pool | None = None


async def pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url, min_size=1, max_size=5
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
```

- [ ] **Step 4: Implement `anton/audit.py`**

```python
from __future__ import annotations

from typing import Any

from anton.llm import LLMResult
from anton.prompts import RenderedPrompt

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
        request_id = result.request_id if result is not None else f"err-{id(prompt):x}"
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
```

- [ ] **Step 5: Run unit test, expect PASS**

```
uv run pytest tests/unit/test_audit.py -v
```

- [ ] **Step 6: Write the integration test**

`tests/integration/test_audit_integration.py`:

```python
import os

import asyncpg
import pytest

from anton.audit import AuditWriter
from anton.llm import LLMResult
from anton.prompts import RenderedPrompt

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
            "INC-audit-test", "cli", "why is fct_orders stale?",
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
        text="hi", tokens_in=5, tokens_out=2, cost_usd=0.0001,
        latency_ms=10, cache_read=False, model="claude-sonnet-4-6",
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
```

- [ ] **Step 7: Run integration test, expect PASS**

```
make db-up && make db-migrate
uv run pytest tests/integration/test_audit_integration.py -v -m integration
```

- [ ] **Step 8: Commit**

```
git add anton/db.py anton/audit.py tests/unit/test_audit.py \
        tests/integration/test_audit_integration.py
git -c user.name="Mona Alkhatib" -c user.email=muna.alkhateeb@gmail.com \
    commit -m "feat: postgres audit writer with LLM-call persistence"
```

---

## Task 9: Stub retriever

**Files:**
- Create: `anton/retrieval/__init__.py`, `anton/retrieval/base.py`, `anton/retrieval/stub.py`
- Test: `tests/unit/test_retrieval_stub.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Retriever` protocol: `async def search(query: str, *, scope: list[str] | None = None, top_k: int = 5) -> list[Citation]`
  - `StubRetriever` implementation that returns an empty list. Kept as the Phase 1 placeholder so `AntonService` can construct a valid retriever without importing Qdrant. Phase 2 will replace with the real retriever.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_retrieval_stub.py`:

```python
import pytest

from anton.retrieval.stub import StubRetriever


@pytest.mark.asyncio
async def test_stub_returns_empty() -> None:
    r = StubRetriever()
    out = await r.search("anything")
    assert out == []


@pytest.mark.asyncio
async def test_stub_honors_top_k_argument() -> None:
    r = StubRetriever()
    out = await r.search("anything", top_k=10)
    assert out == []
```

- [ ] **Step 2: Run test, expect FAIL**

```
uv run pytest tests/unit/test_retrieval_stub.py -v
```

- [ ] **Step 3: Implement the package**

`anton/retrieval/__init__.py`:

```python
from anton.retrieval.base import Retriever
from anton.retrieval.stub import StubRetriever

__all__ = ["Retriever", "StubRetriever"]
```

`anton/retrieval/base.py`:

```python
from typing import Protocol

from anton.types import Citation


class Retriever(Protocol):
    async def search(
        self,
        query: str,
        *,
        scope: list[str] | None = None,
        top_k: int = 5,
    ) -> list[Citation]:
        ...
```

`anton/retrieval/stub.py`:

```python
from anton.types import Citation


class StubRetriever:
    async def search(
        self,
        query: str,
        *,
        scope: list[str] | None = None,
        top_k: int = 5,
    ) -> list[Citation]:
        return []
```

- [ ] **Step 4: Run test, expect PASS**

```
uv run pytest tests/unit/test_retrieval_stub.py -v
```

- [ ] **Step 5: Commit**

```
git add anton/retrieval/ tests/unit/test_retrieval_stub.py
git -c user.name="Mona Alkhatib" -c user.email=muna.alkhateeb@gmail.com \
    commit -m "feat: retriever protocol + phase-1 stub implementation"
```

---

## Task 10: AntonService (Phase 1 orchestrator)

**Files:**
- Create: `anton/service.py`
- Test: `tests/unit/test_service.py`

**Interfaces:**
- Consumes: `LLMGateway` (Task 7), `Retriever` (Task 9), prompt registry `load` (Task 6), `Caller`, `IncidentResponse` (Task 5).
- Produces:
  - `class AntonService`
    - `def __init__(self, *, llm: LLMGateway, retriever: Retriever, prompt_name: str = "generic")`
    - `async def ask(question: str, *, incident_id: str | None, caller: Caller) -> IncidentResponse`
  - Behavior for Phase 1:
    1. Compute `incident_id` if not provided (`INC-<uuid short>`).
    2. Call `retriever.search(question, top_k=0)` (stub returns empty).
    3. Load `generic` prompt (latest), render with `{question, context}` where `context` is `"(no context available in phase 1)"` if the retriever returned nothing.
    4. Call `llm.complete(rendered, extra_context={"incident_id": incident_id})`.
    5. Wrap result in `IncidentResponse(answer_md=text, citations=[], drafted_slack_post=None, drafted_actions=[], incident_id=incident_id, request_id=result.request_id)`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_service.py`:

```python
from unittest.mock import AsyncMock

import pytest

from anton.llm import LLMResult
from anton.retrieval.stub import StubRetriever
from anton.service import AntonService
from anton.types import Caller


@pytest.mark.asyncio
async def test_ask_returns_incident_response_and_calls_llm() -> None:
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value=LLMResult(
            text="two-sentence answer.",
            tokens_in=100, tokens_out=20, cost_usd=0.002, latency_ms=350,
            cache_read=True, model="claude-sonnet-4-6", request_id="resp_1",
        )
    )
    svc = AntonService(llm=llm, retriever=StubRetriever())

    resp = await svc.ask(
        "why is fct_orders stale?",
        incident_id=None,
        caller=Caller(source="cli", identity="mona"),
    )

    assert resp.answer_md == "two-sentence answer."
    assert resp.request_id == "resp_1"
    assert resp.incident_id.startswith("INC-")
    assert resp.citations == []
    assert resp.drafted_slack_post is None
    llm.complete.assert_awaited_once()
    kwargs = llm.complete.await_args.kwargs
    assert kwargs["extra_context"]["incident_id"] == resp.incident_id


@pytest.mark.asyncio
async def test_ask_uses_provided_incident_id() -> None:
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value=LLMResult(
            text="ok",
            tokens_in=1, tokens_out=1, cost_usd=0.0, latency_ms=1,
            cache_read=False, model="claude-sonnet-4-6", request_id="r",
        )
    )
    svc = AntonService(llm=llm, retriever=StubRetriever())

    resp = await svc.ask(
        "hi", incident_id="INC-fixed", caller=Caller(source="api", identity="k")
    )
    assert resp.incident_id == "INC-fixed"
```

- [ ] **Step 2: Run test, expect FAIL**

```
uv run pytest tests/unit/test_service.py -v
```

- [ ] **Step 3: Implement `anton/service.py`**

```python
from __future__ import annotations

import uuid

from anton.llm import LLMGateway
from anton.prompts import load as load_prompt
from anton.retrieval.base import Retriever
from anton.types import Caller, IncidentResponse


class AntonService:
    def __init__(
        self,
        *,
        llm: LLMGateway,
        retriever: Retriever,
        prompt_name: str = "generic",
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._prompt_name = prompt_name

    async def ask(
        self,
        question: str,
        *,
        incident_id: str | None,
        caller: Caller,
    ) -> IncidentResponse:
        incident_id = incident_id or f"INC-{uuid.uuid4().hex[:8]}"

        hits = await self._retriever.search(question, top_k=0)
        context_block = (
            "\n".join(f"- {c.source_id}: {c.snippet}" for c in hits)
            if hits
            else "(no context available in phase 1)"
        )

        prompt = load_prompt(self._prompt_name)
        rendered = prompt.render(question=question, context=context_block)

        result = await self._llm.complete(
            rendered, extra_context={"incident_id": incident_id, "caller": caller.source}
        )

        return IncidentResponse(
            answer_md=result.text,
            citations=list(hits),
            drafted_slack_post=None,
            drafted_actions=[],
            incident_id=incident_id,
            request_id=result.request_id,
        )
```

- [ ] **Step 4: Run test, expect PASS**

```
uv run pytest tests/unit/test_service.py -v
```

- [ ] **Step 5: Commit**

```
git add anton/service.py tests/unit/test_service.py
git -c user.name="Mona Alkhatib" -c user.email=muna.alkhateeb@gmail.com \
    commit -m "feat: AntonService phase-1 orchestrator"
```

---

## Task 11: Typer CLI

**Files:**
- Create: `anton/cli.py`
- Test: `tests/unit/test_cli.py`

**Interfaces:**
- Consumes: `AntonService` (Task 10), `LLMGateway` (Task 7), `AuditWriter` (Task 8), `StubRetriever` (Task 9), `Settings` (Task 2), `anton.db.pool` (Task 8).
- Produces:
  - `anton` Typer app entry point (registered in `pyproject.toml`, Task 1).
  - Command `anton ask "QUESTION"` prints the answer to stdout.
    - Flags: `--incident-id`, `--json` (emits full `IncidentResponse` as JSON), `--stream` (Phase 1 stub, warns "streaming lands in Phase 3").
    - Exit code `0` on success, `1` on API error.
  - Command `anton audit-tail [--limit N]` prints the last N `audit_llm_calls` rows.

- [ ] **Step 1: Write the failing CLI test**

`tests/unit/test_cli.py`:

```python
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from anton.cli import app
from anton.types import IncidentResponse

runner = CliRunner()


def _fake_response() -> IncidentResponse:
    return IncidentResponse(
        answer_md="short answer.",
        citations=[],
        drafted_slack_post=None,
        drafted_actions=[],
        incident_id="INC-x",
        request_id="req_1",
    )


def test_ask_prints_answer() -> None:
    svc = AsyncMock()
    svc.ask = AsyncMock(return_value=_fake_response())
    with (
        patch("anton.cli.build_service", AsyncMock(return_value=(svc, None))),
        patch("anton.cli.close_pool", AsyncMock()),
    ):
        r = runner.invoke(app, ["ask", "hi there"])

    assert r.exit_code == 0
    assert "short answer." in r.stdout


def test_ask_json_flag_emits_json() -> None:
    svc = AsyncMock()
    svc.ask = AsyncMock(return_value=_fake_response())
    with (
        patch("anton.cli.build_service", AsyncMock(return_value=(svc, None))),
        patch("anton.cli.close_pool", AsyncMock()),
    ):
        r = runner.invoke(app, ["ask", "hi", "--json"])

    assert r.exit_code == 0
    assert '"answer_md":"short answer."' in r.stdout.replace(" ", "")
```

- [ ] **Step 2: Run tests, expect FAIL**

```
uv run pytest tests/unit/test_cli.py -v
```

- [ ] **Step 3: Implement `anton/cli.py`**

Key correctness constraint: every command runs a single `asyncio.run(_work())`; the asyncpg pool is created and closed inside that same loop. Do not spin a second event loop.

```python
from __future__ import annotations

import asyncio
import sys
from typing import Optional

import asyncpg
import typer
from rich.console import Console

from anton.audit import AuditWriter
from anton.db import close_pool, pool
from anton.llm import LLMGateway
from anton.retrieval.stub import StubRetriever
from anton.service import AntonService
from anton.types import Caller

app = typer.Typer(help="Son of Anton CLI (phase 1)")
console = Console()


async def build_service() -> tuple[AntonService, asyncpg.Pool]:
    """Async factory: opens the pool and wires the service on the current loop."""
    p = await pool()
    writer = AuditWriter(pool=p)
    gateway = LLMGateway(audit_writer=writer.as_gateway_callable())
    svc = AntonService(llm=gateway, retriever=StubRetriever())
    return svc, p


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question for the Oracle"),
    incident_id: Optional[str] = typer.Option(None, "--incident-id"),
    json_out: bool = typer.Option(False, "--json"),
    stream: bool = typer.Option(False, "--stream"),
) -> None:
    if stream:
        console.print("[yellow]streaming lands in phase 3; ignoring --stream.[/yellow]")

    async def _work() -> int:
        try:
            svc, _ = await build_service()
            resp = await svc.ask(
                question,
                incident_id=incident_id,
                caller=Caller(source="cli", identity="local"),
            )
            if json_out:
                sys.stdout.write(resp.model_dump_json())
                sys.stdout.write("\n")
            else:
                console.print(resp.answer_md)
            return 0
        except Exception as exc:
            console.print(f"[red]error:[/red] {exc}")
            return 1
        finally:
            await close_pool()

    raise typer.Exit(asyncio.run(_work()))


@app.command("audit-tail")
def audit_tail(limit: int = typer.Option(10, "--limit")) -> None:
    async def _work() -> int:
        try:
            p = await pool()
            rows = await p.fetch(
                "select request_id, prompt_name, model, tokens_in, tokens_out, "
                "cost_usd, latency_ms, cache_read, error, created_at "
                "from audit_llm_calls order by created_at desc limit $1",
                limit,
            )
            for row in rows:
                console.print(dict(row))
            return 0
        finally:
            await close_pool()

    raise typer.Exit(asyncio.run(_work()))


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Add `rich` dependency**

Edit `pyproject.toml`, add to `dependencies`:

```
    "rich>=13.9,<14",
```

Then:

```
uv sync --all-extras
```

- [ ] **Step 5: Run CLI tests, expect PASS**

```
uv run pytest tests/unit/test_cli.py -v
```

- [ ] **Step 6: Manual smoke (only if you have DB + API key)**

```
make db-up && make db-migrate
export $(grep -v '^#' .env | xargs)
uv run anton ask "in two sentences: what is a dbt incremental model?"
uv run anton audit-tail --limit 3
```

Expected: an answer prints; `audit-tail` shows a row with a non-zero `tokens_out`.

- [ ] **Step 7: Commit**

```
git add anton/cli.py tests/unit/test_cli.py pyproject.toml
git -c user.name="Mona Alkhatib" -c user.email=muna.alkhateeb@gmail.com \
    commit -m "feat: typer CLI with 'ask' and 'audit-tail' commands"
```

---

## Task 12: End-to-end integration test

**Files:**
- Create: `tests/integration/conftest.py`, `tests/integration/test_e2e_phase1.py`
- Test: itself

**Interfaces:**
- Consumes: everything above.
- Produces: one integration test that spins the real path (Postgres + real Anthropic call) and asserts an `IncidentResponse` returns and an `audit_llm_calls` row lands. Skipped without `ANTHROPIC_API_KEY`.

- [ ] **Step 1: Write the integration conftest**

`tests/integration/conftest.py`:

```python
import os

import pytest


def pytest_collection_modifyitems(config, items):
    if "ANTHROPIC_API_KEY" not in os.environ or not os.environ["ANTHROPIC_API_KEY"]:
        skip_llm = pytest.mark.skip(reason="ANTHROPIC_API_KEY not set")
        for item in items:
            if "needs_llm" in item.keywords:
                item.add_marker(skip_llm)
    if "DATABASE_URL" not in os.environ:
        skip_db = pytest.mark.skip(reason="DATABASE_URL not set")
        for item in items:
            if item.get_closest_marker("integration") is not None:
                item.add_marker(skip_db)
```

- [ ] **Step 2: Write the end-to-end test**

`tests/integration/test_e2e_phase1.py`:

```python
import asyncpg
import os
import pytest

from anton.audit import AuditWriter
from anton.llm import LLMGateway
from anton.retrieval.stub import StubRetriever
from anton.service import AntonService
from anton.types import Caller

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.needs_llm]


async def test_ask_end_to_end_writes_audit_row() -> None:
    dsn = os.environ["DATABASE_URL"]
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "insert into incidents (id, source, question) values ($1, $2, $3) "
                "on conflict (id) do nothing",
                "INC-e2e-phase1", "cli", "in one sentence: what is dbt?",
            )

        writer = AuditWriter(pool=pool)
        gateway = LLMGateway(audit_writer=writer.as_gateway_callable())
        svc = AntonService(llm=gateway, retriever=StubRetriever())

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
```

- [ ] **Step 3: Register the `needs_llm` marker**

Edit `pyproject.toml`, extend the `markers` list under `[tool.pytest.ini_options]`:

```
markers = [
    "integration: requires docker-compose stack + optional ANTHROPIC_API_KEY",
    "needs_llm: requires a live Anthropic API key",
]
```

- [ ] **Step 4: Run the E2E test**

```
make db-up && make db-migrate
export $(grep -v '^#' .env | xargs)
uv run pytest tests/integration/test_e2e_phase1.py -v -m integration
```

Expected: PASS (with a real answer) if `ANTHROPIC_API_KEY` is set; SKIP otherwise.

- [ ] **Step 5: Commit**

```
git add tests/integration/conftest.py tests/integration/test_e2e_phase1.py pyproject.toml
git -c user.name="Mona Alkhatib" -c user.email=muna.alkhateeb@gmail.com \
    commit -m "test: end-to-end phase-1 integration on real postgres + anthropic"
```

---

## Phase 1 done: what you have

At the end of Task 12, `anton ask "..."` runs a real LLM call, persists an audit row, and returns an `IncidentResponse`. Every LLM call goes through the versioned prompt registry and the LiteLLM gateway. The Postgres schema is in place for every downstream table Phase 2-5 will populate. The stub retriever, generic specialist, and read-only default hold the multi-agent seat for Phase 2.

**Next plan:** `2026-07-15-son-of-anton-phase2-retrieval.md` (Qdrant + BM25 + rerank + all five corpora ingesters + retrieval ablation eval).

---

## Self-review notes

- **Spec coverage (Phase 1 items only):** repo scaffold (Task 1), Postgres + migrations (Tasks 3, 4), prompt registry (Task 6), LiteLLM gateway (Task 7), audit log (Task 8), `AntonService` skeleton (Task 10), stub retriever (Task 9), CLI (Task 11), end-to-end proof (Task 12). Settings (Task 2) and domain types (Task 5) are Phase 1 prerequisites the spec assumes but does not list separately; covered.
- **Placeholder scan:** none. All code blocks are complete.
- **Type consistency:** `Prompt`, `RenderedPrompt`, `LLMResult`, `AuditWriter`, `AntonService`, `Caller`, `IncidentResponse`, `Citation`, `ProposedAction`, `RoutingDecision`, `SpecialistFindings`, `ApprovalDecision`, `Retriever`, `StubRetriever` all consistent across tasks.
- **Scope check:** 12 tasks, one working `anton ask` end-to-end path. Multi-agent, real retrieval, adapters, and Slack are deferred to their own phase plans. Correctly scoped.
