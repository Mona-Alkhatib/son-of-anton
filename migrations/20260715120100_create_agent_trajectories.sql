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
