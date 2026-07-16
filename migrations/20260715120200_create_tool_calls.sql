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
