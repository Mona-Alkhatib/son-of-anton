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
