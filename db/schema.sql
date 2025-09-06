create extension if not exists pgcrypto;

create table if not exists pins (
    id uuid primary key default gen_random_uuid(),
    kind text not null check (kind in ('need','offer')),
    categories text[] not null default '{}',
    title text,
    body text not null,
    lat double precision not null,
    lng double precision not null,
    author_anon_id text not null,
    urgency smallint not null default 2,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    is_hidden boolean not null default false
);

-- In-place migration for existing databases
alter table if exists pins add column if not exists urgency smallint not null default 2;

create index if not exists idx_pins_kind_created on pins(kind, created_at desc);
create index if not exists idx_pins_expires_at on pins(expires_at);
create index if not exists idx_pins_geo on pins(lat, lng);

create table if not exists comments (
    id uuid primary key default gen_random_uuid(),
    pin_id uuid not null references pins(id) on delete cascade,
    body text not null,
    author_anon_id text not null,
    created_at timestamptz not null default now(),
    is_hidden boolean not null default false
);
create index if not exists idx_comments_pin_created on comments(pin_id, created_at desc);

create table if not exists shelters (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    type text not null check (type in ('official','community')),
    lat double precision not null,
    lng double precision not null,
    capacity text,
    notes text,
    last_updated timestamptz not null default now()
);

create table if not exists food_supply_sites (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    kind text not null check (kind in ('free_food','drop_off')),
    lat double precision not null,
    lng double precision not null,
    status text,
    needs text,
    source text not null check (source in ('official','community')),
    last_updated timestamptz not null default now()
);

-- Optional push subscriptions
create table if not exists push_subscriptions (
    anon_id text primary key,
    onesignal_id text not null,
    geohash text not null,
    radius_mi integer not null,
    role text not null,
    categories text[] not null default '{}',
    last_notified_at timestamptz
);


