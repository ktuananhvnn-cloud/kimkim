-- Personal stock assistant - Supabase schema
-- Run this once in the Supabase SQL editor (or via `supabase db push`).
-- Single-owner app: no per-row user_id / RLS multi-tenancy needed. Access
-- from the app goes through the service-role key (server-side only, never
-- exposed to a browser), so RLS is left disabled here on purpose. If you
-- ever expose these tables via the Supabase client-side anon key, enable
-- RLS and add owner-scoped policies before doing so.

create table if not exists holdings (
    id          bigint generated always as identity primary key,
    ticker      text not null,
    quantity    numeric not null check (quantity > 0),
    cost_basis  numeric not null check (cost_basis >= 0),
    purchase_date date,
    notes       text default '',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);
create unique index if not exists holdings_ticker_key on holdings (ticker);

create table if not exists watchlist (
    id               bigint generated always as identity primary key,
    ticker           text not null unique,
    alert_price_high numeric,
    alert_price_low  numeric,
    notes            text default '',
    created_at       timestamptz not null default now()
);

create table if not exists conversation_messages (
    id               bigint generated always as identity primary key,
    telegram_chat_id bigint not null,
    role             text not null check (role in ('user', 'assistant')),
    content          jsonb not null,
    created_at       timestamptz not null default now()
);
create index if not exists conversation_messages_chat_idx
    on conversation_messages (telegram_chat_id, created_at desc);

create table if not exists prompts (
    id         bigint generated always as identity primary key,
    name       text not null,
    content    text not null,
    version    int not null,
    is_active  boolean not null default false,
    updated_at timestamptz not null default now()
);
create index if not exists prompts_name_active_idx on prompts (name, is_active);
create unique index if not exists prompts_name_version_key on prompts (name, version);

create table if not exists config (
    key        text primary key,
    value      jsonb not null,
    updated_at timestamptz not null default now()
);

create table if not exists price_cache (
    ticker     text primary key,
    price      numeric not null,
    fetched_at timestamptz not null default now()
);

create table if not exists alerts_log (
    id           bigint generated always as identity primary key,
    ticker       text not null,
    alert_type   text not null,
    triggered_at timestamptz not null default now(),
    message      text not null
);
create index if not exists alerts_log_ticker_type_idx
    on alerts_log (ticker, alert_type, triggered_at desc);

-- Seed a default system prompt so the bot has something to load on first run.
insert into prompts (name, content, version, is_active)
values (
    'system',
    'You are a personal Vietnamese stock market assistant. You only use '
    'publicly available market data and never place real trades. You may '
    'suggest ideas, but always make clear these are not financial advice '
    'and the user must place any order themselves in their own broker app. '
    'Be concise, use VND for prices, and mention when data may be delayed '
    'or outside VN market trading hours (9:00-11:30, 13:00-14:45 ICT).',
    1,
    true
)
on conflict do nothing;

-- Default alert-check interval (minutes), editable later from the admin site.
insert into config (key, value)
values ('alert_check_interval_minutes', '5')
on conflict (key) do nothing;
