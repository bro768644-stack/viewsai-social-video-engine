-- SCOUT SCHEMA — sourced leads (LinkedIn people + GitHub orgs + job-board companies)
-- Feeds outbound, and enriches inbound replies with context.
-- Run: psql "$SUPABASE_DB_URL" -f supabase_scout_schema.sql

create table if not exists scout_companies (
    id           uuid primary key default gen_random_uuid(),
    domain       text unique,
    company      text not null,
    website      text,
    location     text,
    job_count    int default 0,
    sample_roles text,
    source       text,                 -- agency-leads.com | job-board | manual
    hiring_signal boolean default false,
    geo_score    int,
    notes        text,
    tags         text[] default '{}',
    raw          jsonb,
    created_at   timestamptz default now()
);
create index if not exists scout_companies_company_idx on scout_companies (lower(company));
create index if not exists scout_companies_domain_idx  on scout_companies (domain);

create table if not exists scout_people (
    id            uuid primary key default gen_random_uuid(),
    email         text,
    first_name    text,
    last_name     text,
    full_name     text,
    title         text,
    company       text,
    company_domain text,
    linkedin_url  text,
    github_handle text,
    location      text,
    bio           text,
    followers     int,
    priority      text,                -- high | medium | low
    source        text,                -- linkedin | github | agency-leads | job-board
    query         text,                -- the search that found them
    score         int,
    tags          text[] default '{}',
    raw           jsonb,
    created_at    timestamptz default now()
);
create unique index if not exists scout_people_email_uniq on scout_people (lower(email)) where email is not null;
create index if not exists scout_people_domain_idx  on scout_people (company_domain);
create index if not exists scout_people_company_idx on scout_people (lower(company));
create index if not exists scout_people_li_idx      on scout_people (lower(linkedin_url));

-- link replies to scout + outbound context
alter table email_replies add column if not exists scout_person_id uuid;
alter table email_replies add column if not exists scout_company_id uuid;
alter table email_replies add column if not exists outbound_subject text;
alter table email_replies add column if not exists scout_context text;

-- helpful join for the reply agent
create or replace view reply_context as
select r.id as reply_id, r.from_email, r.subject, r.intent, r.urgency,
       p.full_name as person_name, p.title as person_title,
       p.company as person_company, p.linkedin_url,
       c.company as company_name, c.hiring_signal, c.sample_roles, c.job_count
from email_replies r
left join scout_people p
       on lower(p.email) = lower(r.from_email)
       or (p.company_domain is not null and r.from_email ilike '%@' || p.company_domain)
left join scout_companies c on lower(c.company) = lower(p.company)
order by r.received_at desc;
