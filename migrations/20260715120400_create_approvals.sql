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
