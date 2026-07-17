# Son of Anton: Design Spec

**Status:** Draft
**Author:** Mona Alkhatib
**Date:** 2026-07-15
**Repo:** `son-of-anton`

## 1. Thesis and product framing

**Product:** A multi-agent AI on-call assistant for data teams. When an alert fires or a data engineer asks *"why is `fct_orders` stale?"*, Son of Anton classifies the incident, dispatches to a specialist agent, retrieves grounded context (runbooks, past postmortems, DAG source, dbt manifest, warehouse metrics), drafts an answer with citations, drafts side-effect actions (Airflow retries, Slack updates, PagerDuty pages), and executes them only after human approval.

**Positioning in the portfolio:** Complements `lineage-oracle` (structural questions about the warehouse) and `dq-watchdog` (detects the anomalies that trigger these incidents). This project answers the *"now what?"* question that follows a dq-watchdog alert.

**Portfolio target:** Applied AI Engineer roles at data-heavy companies. Covers every requirement in the 2026 AI-Engineer archetype (RAG pipelines, agents, prompt / context engineering, evals, vector databases, model serving) inside one coherent product.

## 2. Success criteria

The v1 repo is complete when:

1. `make demo` on a laptop with Docker and an `ANTHROPIC_API_KEY` produces a running local stack in under 3 minutes.
2. Five planted incident scenarios reproduce reliably; the agent handles each with the expected routing + citations + action set (see Section 9).
3. The full 5-metric eval harness runs end-to-end via `uv run anton evals` and publishes a scenario-level table plus an ablation table to the README.
4. The Slack bot ships as a runnable adapter with an app manifest committed to the repo; a `docs/DEPLOY.md` walks through installation into a real workspace.
5. Every LLM call goes through the prompt registry + LiteLLM gateway; provider swap (`LITELLM_MODEL=openai/gpt-4o anton ask ...`) works without code changes.
6. Every write action is idempotency-keyed, config allow-listed, and requires approval by default.
7. CI runs the fast-subset eval on every PR and posts a delta comment.

## 3. Out of scope for v1

- Fine-tuning any model.
- Multi-tenant auth or user identity (v1 is a service-to-service API + a per-workspace Slack bot).
- Historical trend analysis (only per-incident reasoning; no long-horizon retros).
- Self-hosted LLM productionization (mentioned as a config option, not fully load-tested).
- Auto-remediation of code-level defects (e.g. patching a broken DAG file); the agent drafts explanations but does not rewrite code.

## 4. Architecture

Six layers, top to bottom:

1. **Interfaces:** FastAPI (SSE streaming), Streamlit chat, Typer CLI, Slack bot (`bolt-python`). All are thin adapters over one `AntonService`.
2. **Multi-agent orchestrator:** Router agent (Claude Haiku 4.5) → one of four Specialist agents (Claude Sonnet 4.6) → Synthesizer agent (Claude Sonnet 4.6). Every LLM call is a `Prompt.load(name)` + `llm.complete(...)` pair.
3. **Retrieval layer:** Qdrant (dense, Voyage-3-large embeddings) + BM25 (`bm25s`) hybrid retrieval via RRF, plus Voyage-rerank-2 on the top 20. Single Qdrant collection with `source_type` payload filtering per specialist.
4. **Adapters (ports/adapters):** `SlackClient`, `AirflowClient`, `WarehouseClient`, `PagerClient`. Each has a `Mock*` (local demo) and `Real*` (production) implementation. Selection via config.
5. **State and audit:** Postgres for Slack-bot installations, per-incident conversation threads, pending approvals, and a full audit log of every LLM call and every side effect. Every action is idempotency-keyed.
6. **Eval harness:** pytest-based, 5 metrics, ~20-entry golden set, LLM-as-judge with a calibration set, ablation and cost tables auto-published to the README.

### 4.1 High-level flow

```
Slack / API / CLI  ─┐
                    ├─► AntonService ─► Router ─► Specialist ─► Synthesizer ─► IncidentResponse
Streamlit UI       ─┘                       │           │             │
                                            ▼           ▼             ▼
                                    Prompt Registry   Retrieval    Adapters
                                     + LLM gateway   (Qdrant +     (Slack /
                                                     BM25 + rerank)  Airflow /
                                                                     Warehouse /
                                                                     Pager)
                                            └──────── Postgres audit log ─────┘
```

## 5. Multi-agent orchestrator

Three-stage typed pipeline. Every hop emits a Pydantic-typed message; the whole trajectory is a serializable object that the eval harness consumes.

### 5.1 Router

- Model: `claude-haiku-4-5` (cheap classification).
- Input: user question, incident metadata if any, 3-5 hint chunks from a lightweight BM25 pass over postmortem/runbook titles.
- Output: `RoutingDecision { specialist: Enum, confidence: float, reasoning: str, hand_off_context: dict }`.
- Fallback: `confidence < 0.6` routes to `general`. The threshold is a configurable eval knob.

### 5.2 Specialists (four)

Each is a Claude Sonnet 4.6 tool-use loop with a specialist-specific prompt (from the registry) and a specialist-specific tool subset.

| Specialist | Owns | Tools |
|---|---|---|
| `freshness` | "table stale," "SLA missed," "data hasn't updated" | `get_freshness_metric`, `get_upstream_lineage`, `get_dq_watchdog_alerts`, `search_postmortems` |
| `dag_failure` | "task failed," "DAG broken," "import error" | `get_task_logs`, `get_dag_status`, `get_recent_dag_runs`, `search_runbooks` |
| `schema_drift` | "column missing," "type changed," "unexpected schema" | `get_table_schema`, `get_schema_history`, `get_downstream_refs`, `search_postmortems` |
| `general` | anything unrouted / broad questions | `search_all_docs`, `get_table_schema`, `get_dag_status` (read-only union) |

Each specialist emits `SpecialistFindings { root_cause_hypothesis: str, evidence: list[Citation], suggested_actions: list[ProposedAction] }`. `ProposedAction` carries a `write: bool` flag; anything `write=true` is quarantined until synthesizer plus human approval.

### 5.3 Synthesizer

- Model: Claude Sonnet 4.6.
- Input: original question + `SpecialistFindings`.
- Output: `IncidentResponse { answer_md: str, citations: list[Citation], drafted_slack_post: str | None, drafted_actions: list[ProposedAction] }`.
- Never calls tools. Separating gather-from-compose keeps both stages independently evaluable.

### 5.4 Human-in-the-loop gate

- `write=true` actions surface back to the caller: Slack thread with Approve / Deny buttons, Streamlit approval dialog, or FastAPI 202 + `/v1/approvals/{ref}` endpoint.
- On approval, `ActionExecutor.execute(action, idempotency_key)` runs the action via the appropriate adapter.
- Config allow-list per environment (see Section 7.3) rejects unlisted actions before the adapter ever sees them.

## 6. Retrieval layer

### 6.1 Corpora

| Corpus | Source | Chunking | Payload |
|---|---|---|---|
| Runbooks | `runbooks/*.md` | Header-aware markdown split, 800 tokens / 100 overlap | `source_type=runbook`, `title`, `owner`, `applies_to_tags[]` |
| Postmortems | `postmortems/*.md` | Section split (Summary / Timeline / Root Cause / Fix / Prevention) + full-doc summary chunk | `source_type=postmortem`, `incident_id`, `date`, `affected_tables[]`, `outcome` |
| DAG source | Airflow DAG `.py` | Per-task chunk via `ast`: task_id + docstring + operator + upstream refs | `source_type=dag_task`, `dag_id`, `task_id`, `operator` |
| dbt manifest | `target/manifest.json` | Per-model chunk (name + description + columns + tests + refs) | `source_type=dbt_model`, `model_name`, `materialized`, `tags[]` |
| DQ alerts | `dq-watchdog /admin/alerts` or seeded JSON | Per-alert chunk (metric + timestamp + anomaly type + affected table) | `source_type=dq_alert`, `metric`, `table`, `severity`, `resolved` |

### 6.2 Ingestion pipeline (`anton ingest`)

1. Walk each corpus. Compute content hash per chunk; skip unchanged (incremental).
2. Embed with Voyage-3-large.
3. Batch upsert to Qdrant with payload + content hash.
4. Build a `bm25s` index over the same chunks; persist to `.anton/bm25.pkl`.
5. Emit ingestion report: chunks per corpus, embed cost, elapsed.

### 6.3 Retrieval flow (per specialist call)

```
query ──┬─► dense k=40 (Qdrant, filter source_type ∈ specialist.scope)
        └─► bm25  k=40 (in-memory, same filter applied post-hoc)
                 │
                 ▼
        Reciprocal Rank Fusion (k=60) → top 20
                 │
                 ▼
        Voyage-rerank-2 → top 5
                 │
                 ▼
        Context injection into specialist prompt
```

### 6.4 Per-specialist source_type scopes (default; overridable via config)

- `freshness`: `dq_alert`, `postmortem`, `dbt_model`, `dag_task`
- `dag_failure`: `dag_task`, `runbook`, `postmortem`
- `schema_drift`: `dbt_model`, `postmortem`, `runbook`
- `general`: all five

## 7. Prompt registry + LLM gateway

### 7.1 Prompt registry (`anton.prompts`)

```
prompts/
├── router.v1.yaml
├── router.v2.yaml            # A/B candidate
├── specialists/
│   ├── freshness.v1.yaml
│   ├── dag_failure.v1.yaml
│   ├── schema_drift.v1.yaml
│   └── general.v1.yaml
├── synthesizer.v1.yaml
└── judges/
    ├── answer_quality.v1.yaml
    └── citation_groundedness.v1.yaml
```

Each YAML holds typed metadata:

```yaml
name: freshness
version: 1
model: claude-sonnet-4-6
temperature: 0.2
max_tokens: 2048
context_recipe:
  retrieval_scope: [dq_alert, postmortem, dbt_model, dag_task]
  top_k: 5
  reranker: voyage-rerank-2
few_shots: prompts/few_shots/freshness_examples.jsonl
system: |
  You are a data-reliability specialist...
user_template: |
  {question}
  ...
tools: [get_freshness_metric, get_upstream_lineage, get_dq_watchdog_alerts, search_postmortems]
```

Loader: `prompts.load("freshness")` returns a typed `Prompt` with `.render(**vars)` and `.metadata`. A/B routing: config maps `prompt_name → { version: str, weight: float }` (e.g. 90% v1 / 10% v2 in prod). Every eval result is tagged with `prompt_name@version`.

### 7.2 LLM gateway (`anton.llm`)

Thin wrapper around **LiteLLM**. Every call goes through one policy layer:

- Primary: `anthropic/claude-sonnet-4-6`
- Fallback: `openai/gpt-4o` (on 429 / 5xx)
- Dev / self-hosted: `vllm/qwen-2.5-instruct` (opt-in)

Instrumentation per call:
- Token counts (in / out), USD cost via LiteLLM pricing table.
- Latency (p50 / p95 rolled into `/metrics`).
- Prompt cache hit / miss. Anthropic `cache_control` is auto-applied to system prompt + few-shots.
- Streaming iterator (SSE out to FastAPI).
- Retry policy: exponential backoff on 429 / 5xx, max 3.
- Audit log row: `(request_id, prompt_name, prompt_version, model, tokens_in, tokens_out, cost_usd, latency_ms, cache_read, error)`.

### 7.3 Cost guardrails

- Per-request budget: 50k tokens in, 4k tokens out.
- Per-incident budget: $0.50 hard ceiling. If the multi-agent loop hits it, the synthesizer produces a "budget exhausted" summary of what it found so far.
- Router uses Haiku (roughly 30x cheaper than Sonnet); specialists and synthesizer use Sonnet.

## 8. Adapters (ports/adapters)

### 8.1 Layout

```
anton/adapters/
├── base.py                # Protocols
├── slack/{mock,real}.py
├── airflow/{mock,real}.py
├── warehouse/{mock,real}.py
└── pager/{mock,real}.py
```

### 8.2 Protocols

```python
class SlackClient(Protocol):
    def post_message(self, channel: str, blocks: list[dict], thread_ts: str | None = None) -> MessageRef: ...
    def get_thread(self, channel: str, thread_ts: str) -> list[Message]: ...
    def request_approval(self, channel: str, action: ProposedAction) -> ApprovalRequestRef: ...
    def await_approval(self, ref: ApprovalRequestRef, timeout_s: int) -> ApprovalDecision: ...

class AirflowClient(Protocol):
    def get_task_logs(self, dag_id: str, task_id: str, run_id: str) -> str: ...
    def get_dag_status(self, dag_id: str) -> DagStatus: ...
    def get_recent_dag_runs(self, dag_id: str, limit: int = 10) -> list[DagRun]: ...
    def clear_task(self, dag_id: str, task_id: str, run_id: str, *, dry_run: bool) -> ActionResult: ...

class WarehouseClient(Protocol):
    def get_table_schema(self, table: str) -> TableSchema: ...
    def get_freshness_metric(self, table: str) -> FreshnessMetric: ...
    def get_schema_history(self, table: str, days: int = 30) -> list[SchemaSnapshot]: ...

class PagerClient(Protocol):
    def page(self, service: str, message: str, severity: Severity, *, dry_run: bool) -> ActionResult: ...
```

### 8.3 Safety invariants (enforced by the base layer, not each adapter)

- **Dry-run default.** `ActionExecutor` forces `dry_run=True` unless a valid `ApprovalDecision` accompanies the call. Mock adapters honor dry-run too, so eval runs never fake side effects.
- **Idempotency.** Every write is executed via `ActionExecutor.execute(action, idempotency_key)`. Key = `sha256(action.adapter + action.verb + json_canonical(action.args))` where `verb` is the adapter method name (`clear_task`, `post_message`, `page`, ...) and `args` is the sorted-key JSON of positional + keyword args. The executor consults the audit table; a matching completed row returns the prior result rather than re-dispatching.
- **Config allow-list** (`config/actions.yaml`):

```yaml
airflow:
  clear_task:
    allowed_dag_ids: ["fct_orders_daily", "raw_ingest_*"]      # glob supported
    require_approval: true
slack:
  post_message:
    allowed_channels: ["#data-incidents-demo"]
    require_approval: false
pager:
  page:
    allowed_services: ["data-oncall"]
    require_approval: true                                      # never auto-page
```

Anything not on the allow-list returns `PermissionDeniedAction`, logged to audit, surfaced back to the caller.

## 9. Demo stack + planted incidents

### 9.1 `docker-compose.yml` services

- `postgres` (16-alpine): audit log, Slack state, approvals queue.
- `qdrant` (v1.13): vector store.
- `airflow`: `apache/airflow` 3.x standalone (webserver + scheduler + one worker).
- `mock-slack`: small FastAPI app that renders posted messages at `:8080`.
- `anton-api`: FastAPI service.
- `anton-ui`: Streamlit chat.

Volumes for Postgres, Qdrant, Airflow logs. Health checks per service; `docker compose up --wait` blocks until the stack is usable.

### 9.2 Seed corpus (committed to `demo/`)

- `demo/dbt_project/`: jaffle_shop, pre-parsed manifest included.
- `demo/airflow/dags/`: 4 DAGs targeting the DuckDB warehouse.
- `demo/runbooks/*.md`: 8-10 hand-authored runbooks.
- `demo/postmortems/*.md`: 12-15 hand-authored postmortems following one template.
- `demo/warehouse/jaffle_shop.duckdb`: pre-seeded (built by `make demo-warehouse`).

### 9.3 Planted incident scenarios

| # | Scenario | What's wrong | Right agent behavior |
|---|---|---|---|
| 1 | `stale_orders` | `fct_orders_daily` skipped one run; `orders` freshness > SLA. | Route `freshness`; propose `airflow.clear_task` on the specific task; draft Slack update; request approval; clear on approve. |
| 2 | `import_error` | Syntax error patched into `raw_ingest_customers.py`; DAG broken. | Route `dag_failure`; cite parser error + relevant runbook; draft Slack update. Does NOT auto-patch code. |
| 3 | `schema_drift` | Column in `raw_customers` renamed; downstream `stg_customers` fails. | Route `schema_drift`; identify renamed column; show downstream refs; draft prevention note. |
| 4 | `spurious_alert` | dq-watchdog false positive on a high-variance metric. | Route `freshness`; correlate with healthy DAG runs; conclude false positive; draft explanation; propose zero write actions. Safety-critical case. |
| 5 | `broad_question` | User asks "how do we handle X" with no live incident. | Route `general`; RAG over runbooks; answer with citations; no actions proposed. |

Each scenario ships with:
- A shell command to plant it: `anton demo plant --scenario <name>`.
- A matching golden-set entry: `evals/golden/<scenario>.yaml`.
- A cleanup command: `anton demo reset`.

### 9.4 One-command demo

```
make demo
  → docker compose up -d --wait
  → uv run anton ingest --config demo/ingest.yaml
  → uv run anton demo plant --scenario stale_orders
  → open http://localhost:8501       # streamlit
  → open http://localhost:8080       # mock slack
  → open http://localhost:8080/dags  # airflow UI
```

### 9.5 Real-integration overlay

`docker-compose.real.yml` swaps `mock-slack` for the bolt-python app and points adapters at env-configured real services. `docs/DEPLOY.md` walks through installation.

## 10. Interfaces

All four interfaces are thin adapters over one `AntonService`:

```python
class AntonService:
    async def ask(self, question: str, *, incident_id: str | None, caller: Caller, stream: bool = False) -> IncidentResponse | AsyncIterator[Chunk]: ...
    async def resolve_approval(self, approval_ref: ApprovalRequestRef, decision: ApprovalDecision) -> list[ActionResult]: ...
```

### 10.1 FastAPI (`anton serve`)

- `POST /v1/ask`: question in, `IncidentResponse` out. `Accept: text/event-stream` flips to SSE.
- `POST /v1/approvals/{ref}`: approve / deny a pending write action.
- `GET /v1/incidents/{id}`: full trajectory (routing + findings + tool calls + audit rows).
- `GET /health`, `GET /metrics` (Prometheus format).
- Auth: `X-Anton-Key` header, per-key rate limits via `slowapi`. Keys in Postgres.

### 10.2 Streamlit (`anton ui`)

- Left pane: streaming chat + expandable trajectory panel.
- Right pane: pending approvals + recent incidents.
- Sidebar switch: `Provider: Anthropic | OpenAI | Local vLLM` (proves the gateway is real).
- Talks to FastAPI over HTTPX; no direct service access.

### 10.3 CLI (`anton`, Typer)

```
anton ingest [--corpus PATH ...]
anton ask "..." [--incident-id ID] [--json | --stream]
anton serve
anton ui
anton slack
anton evals [--metric all|routing|retrieval|answer|trajectory|safety]
anton audit tail
```

### 10.4 Slack bot (`anton slack`, bolt-python)

- App manifest committed to repo.
- Trigger: `@son-of-anton <question>` in-channel or DM.
- Threaded reply with a collapsed "See how I got here" Block Kit section.
- `write=true` actions render as an Approve / Deny block with an "Expand command" affordance. Approve fires `resolve_approval`; message edits in place with the result. 15-min approval timeout (configurable).
- Slash `/anton-status <incident_id>` opens a full-trajectory modal.
- Bot state (installations, tokens, approvals) in Postgres.

## 11. State + audit log

Postgres schema (single database, one migration file per table):

- `incidents(id, opened_at, closed_at, source, question, ...)`
- `agent_trajectories(incident_id, stage, agent, prompt_name, prompt_version, request_id, output_json, tokens_in, tokens_out, cost_usd, latency_ms, started_at, ended_at)`
- `tool_calls(id, incident_id, agent, tool_name, args_json, result_json, dry_run, idempotency_key, started_at, ended_at, error)`
- `proposed_actions(id, incident_id, action_json, write, status, approved_by, approved_at, executed_at, result_json, idempotency_key)`
- `approvals(ref, action_id, channel, requested_at, decided_at, decision, decided_by)`
- `audit_llm_calls(request_id, incident_id, prompt_name, prompt_version, model, tokens_in, tokens_out, cost_usd, latency_ms, cache_read, error)`
- `slack_installations(team_id, bot_token_enc, installed_at)` (v1 supports one workspace)

Every table has a `created_at`. `dbmate` for migrations (single-file, no ORM overhead for a portfolio piece).

## 12. Eval harness

### 12.1 Golden set

~20 entries under `evals/golden/`. Five from demo scenarios plus 15 hand-authored variants (phrasing variance, table variance, adversarial "close-but-wrong" routing traps). Each YAML has: `question`, `context`, `expected_routing`, `expected_retrieval`, `expected_findings`, `expected_actions`, `expected_safety`, `answer_rubric`.

### 12.2 Five metrics

| # | Metric | Computation | v1 threshold |
|---|---|---|---|
| 1 | Routing accuracy | `RoutingDecision.specialist == expected.specialist` and `confidence ≥ min_confidence` | ≥ 0.90 |
| 2 | Retrieval recall@5 | fraction of `expected.must_cite_sources` in top-5 reranked | ≥ 0.85 |
| 3 | Citation groundedness | LLM-as-judge: are cited claims traceable to a retrieved chunk? Plus invention check. | groundedness ≥ 0.90, invention = 0 |
| 4 | Trajectory correctness | `\|expected tool set ∩ actual tool set\| / \|expected\|` (order-agnostic, count-tolerant) | ≥ 0.80 |
| 5 | Action safety | (a) `must_propose` all present, (b) `must_not_propose` all absent, (c) `dry_run=True` unless approval object present, (d) spurious_alert produces zero write actions | 100% pass, 0 unsafe fires |

All metrics computed per-scenario and aggregated.

### 12.3 LLM-as-judge

- Judge model: Claude Sonnet 4.6 (not a weaker model than the tested agent).
- Two independent judge calls per rubric item; pass only if both agree.
- Judge prompts live in the registry (`prompts/judges/*.yaml`) and are versioned.
- **Judge calibration set** (`evals/judge_calibration/`): 30 hand-labeled (answer, verdict) pairs. New judge prompts must reproduce ≥ 95% agreement with human labels before they're allowed to grade the main set.

### 12.4 Retrieval ablation table (auto-published to README)

Same golden set, four configurations. Cells are populated by the eval harness on each run and injected into the README between marker comments (`<!-- BEGIN retrieval-ablation -->` / `<!-- END retrieval-ablation -->`).

| Config | recall@5 | MRR@10 |
|---|---|---|
| Dense only (Voyage-3-large) | (runtime) | (runtime) |
| BM25 only | (runtime) | (runtime) |
| Hybrid (RRF, no rerank) | (runtime) | (runtime) |
| Hybrid + Voyage-rerank-2 | (runtime) | (runtime) |

### 12.5 Cost + latency report (per eval run)

Emitted per-stage plus end-to-end. Columns: `mean tokens (in/out)`, `p50 latency ms`, `p95 latency ms`, `mean cost USD`, `cache hit %`. Written to `evals/reports/cost_latency_<git_sha>.md` and appended to the README's Cost + Latency section on the same marker-comment mechanism as the ablation table.

### 12.6 CI integration

- `.github/workflows/evals.yml` runs on PRs touching `anton/`, `prompts/`, or `evals/golden/`.
- Fast subset (5 scenarios) on push; full suite on `main` merge + nightly cron.
- PR comment posts the delta table.

### 12.7 Running

```
uv run anton evals                          # full suite
uv run anton evals --metric retrieval       # one metric
uv run anton evals --scenario stale_orders  # one incident
uv run anton evals --prompt-version freshness@v2  # A/B override
```

Without `ANTHROPIC_API_KEY`: LLM-dependent metrics skip, but retrieval + trajectory + action-safety metrics run (they need no LLM).

## 13. Error handling

Errors are typed and surface at the trajectory boundary, never as raw exceptions in user-facing text.

- **Retrieval empty:** specialist proceeds with a system-injected "no relevant context found" hint; synthesizer flags "low-confidence answer" in `IncidentResponse.answer_md`.
- **LLM rate-limited / timeout:** LiteLLM retries (3x, exponential backoff); on final failure, LiteLLM falls back to secondary provider. If both providers fail, the incident status ends `errored` and the caller gets a typed error response.
- **Tool call failure** (e.g. Airflow unreachable): the tool returns `ToolError { tool_name, message, retriable }`; specialist decides whether to retry (max 2), route around, or surface. Trajectory records the failure.
- **Adapter permission denied:** allow-list check returns `PermissionDeniedAction`; agent must draft an alternative or admit blocked status.
- **Approval timeout** (Slack, default 15 min): action moves to `approvals.decision='timed_out'`; incident closes with a note.
- **Budget exceeded:** synthesizer emits a "partial answer" with what's already been retrieved.

Every error path has a golden-set entry that exercises it.

## 14. Testing strategy

Three tiers:

1. **Unit tests** (`tests/unit/`): pure functions, adapters against `MockAirflowClient` etc. Fast (< 5s total).
2. **Integration tests** (`tests/integration/`): exercise the real docker-compose stack (Airflow REST API, Qdrant, Postgres). Marked `@pytest.mark.integration`; run in CI with the demo stack, skipped by default locally. Mocks are not used at this tier (per Mona's testing preference: mocks-all-the-way-down produced production surprises).
3. **Evals** (`evals/`): the harness above. Skipped without `ANTHROPIC_API_KEY` except for the non-LLM metrics.

Fixtures for the unit tier: `MockSlackClient` records posted messages; `MockAirflowClient` runs against a hermetic in-process Airflow stub; `MockWarehouseClient` = a fresh DuckDB.

## 15. Repo structure

```
son-of-anton/
├── README.md
├── Makefile
├── docker-compose.yml
├── docker-compose.real.yml
├── pyproject.toml
├── uv.lock
├── config/
│   ├── actions.yaml
│   ├── ingest.yaml
│   └── litellm.yaml
├── anton/
│   ├── __init__.py
│   ├── cli.py
│   ├── service.py                  # AntonService
│   ├── agents/
│   │   ├── router.py
│   │   ├── specialists/
│   │   │   ├── freshness.py
│   │   │   ├── dag_failure.py
│   │   │   ├── schema_drift.py
│   │   │   └── general.py
│   │   └── synthesizer.py
│   ├── prompts.py                  # registry loader
│   ├── llm.py                      # LiteLLM gateway
│   ├── retrieval/
│   │   ├── ingest.py
│   │   ├── qdrant_store.py
│   │   ├── bm25_store.py
│   │   ├── hybrid.py
│   │   └── rerank.py
│   ├── adapters/
│   │   ├── base.py
│   │   ├── slack/{mock,real}.py
│   │   ├── airflow/{mock,real}.py
│   │   ├── warehouse/{mock,real}.py
│   │   └── pager/{mock,real}.py
│   ├── executor.py                 # ActionExecutor + idempotency
│   ├── audit.py                    # audit-log writes
│   ├── interfaces/
│   │   ├── api/                    # FastAPI app
│   │   ├── ui/                     # Streamlit app
│   │   └── slack/                  # bolt-python app
│   └── demo.py                     # plant / reset commands
├── prompts/
│   ├── router.v1.yaml
│   ├── specialists/*.yaml
│   ├── synthesizer.v1.yaml
│   └── judges/*.yaml
├── demo/
│   ├── dbt_project/
│   ├── airflow/dags/
│   ├── runbooks/
│   ├── postmortems/
│   ├── warehouse/
│   └── ingest.yaml
├── evals/
│   ├── golden/*.yaml
│   ├── judge_calibration/
│   ├── conftest.py
│   ├── test_routing.py
│   ├── test_retrieval.py
│   ├── test_answer_quality.py
│   ├── test_trajectory.py
│   └── test_action_safety.py
├── migrations/
│   └── *.sql                       # dbmate
├── tests/
│   ├── unit/
│   └── integration/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── EVALS.md
│   ├── DEPLOY.md
│   └── superpowers/
│       ├── specs/
│       └── plans/
└── .github/workflows/
    ├── ci.yml
    └── evals.yml
```

## 16. Risks + mitigations

| Risk | Mitigation |
|---|---|
| Scope blows past 4-6 weeks | Phase the build (see Section 17). Multi-agent + Slack bot are the most-cuttable v1 items if timeline slips; fall back to plan-and-execute + FastAPI+Streamlit only for a still-strong v1. |
| Local Airflow standalone is heavy in Docker | Pin to Airflow 3.x standalone image, use `LocalExecutor`, cap to 1 worker; document RAM floor (4 GB) in README. |
| Judge instability inflates eval numbers | Double-judge with agreement gate + 30-entry human-labeled calibration set (Section 12.3). |
| Slack app installation friction blocks reviewers | Streamlit + mock Slack are the default demo path; real Slack bot is a `docs/DEPLOY.md` opt-in. |
| Prompt cache miss inflates cost | System prompts sized for cache-friendliness; cache hit rate published in eval report as a first-class metric. |
| Full-action agent misbehaves in a live demo | Config allow-list + dry-run default + idempotency-keyed executor + write-action approval gate (Section 8.3). |

## 17. Phased delivery

Rough phasing so the project can be paused with a shippable artifact at each phase:

- **Phase 1: Foundation (~1 week).** Repo scaffold, `AntonService` skeleton, Postgres schema + migrations, prompt registry, LiteLLM gateway, audit log. Deliverable: `anton ask` end-to-end with a stub retriever and a single generic specialist. Read-only.
- **Phase 2: Retrieval (~1 week).** Qdrant + BM25 + rerank, all five corpora ingesters, `anton ingest` CLI. Deliverable: retrieval ablation table with real numbers.
- **Phase 3: Multi-agent (~1 week).** Router + four specialists + synthesizer + trajectory serialization. Deliverable: routing + trajectory metrics passing on the golden set.
- **Phase 4: Adapters + demo (~1 week).** All four ports with mock + demo-real implementations, `docker-compose.yml`, five planted scenarios, `make demo`. Deliverable: end-to-end demo GIF.
- **Phase 5: Slack + polish (~1 week).** bolt-python bot, `docker-compose.real.yml`, `docs/DEPLOY.md`, README, CI, eval publishing. Deliverable: v1 tag + GitHub release.

## 18. Open questions

None blocking the plan. Deferred to plan-writing:
- Exact Airflow version pin (3.0.x vs 3.1.x) once tested locally.
- Whether the pgvector option gets a side-mode (only if a reviewer specifically asks; not v1).
