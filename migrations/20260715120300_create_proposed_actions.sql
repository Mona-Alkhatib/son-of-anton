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
