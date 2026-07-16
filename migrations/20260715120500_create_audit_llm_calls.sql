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
