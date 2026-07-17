# Son of Anton

Multi-agent AI on-call assistant for data teams. When an alert fires or a data engineer asks *"why is `fct_orders` stale?"*, Son of Anton classifies the incident, dispatches to a specialist agent, retrieves grounded context (runbooks, past postmortems, DAG source, dbt manifest, warehouse metrics), drafts an answer with citations, drafts side-effect actions (Airflow retries, Slack updates, PagerDuty pages), and executes them only after human approval.

Named after Gilfoyle's autonomous SRE in Silicon Valley.

## Status

Phase 1 (foundation) shipped. Phases 2 through 5 in progress. See `docs/superpowers/plans/` and `docs/superpowers/specs/`.

## Development

```
make install
make lint typecheck test
```

## Quickstart

```
cp .env.example .env
# Fill in ANTHROPIC_API_KEY

make db-up
make db-migrate

uv run anton ask "in one sentence, what is dbt?"
uv run anton audit-tail --limit 3
```
