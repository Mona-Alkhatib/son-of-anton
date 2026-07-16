-- migrate:up
create table slack_installations (
    team_id text primary key,
    bot_token_enc bytea not null,
    installed_at timestamptz not null default now()
);

-- migrate:down
drop table slack_installations;
