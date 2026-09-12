-- CONTACT BEHAVIOR GRAPH — every interaction becomes a signal
-- Run: psql "$SUPABASE_DB_URL" -f supabase_tracking_schema.sql

-- ---------------------------------------------------------------- contacts (identity spine)
create table if not exists gtm_contacts (
    id            uuid primary key default gen_random_uuid(),
    email         text unique,
    first_name    text,
    last_name     text,
    company       text,
    company_domain text,
    title         text,
    phone         text,
    crm_id        text,                -- Twenty person id
    scout_person_id uuid,
    listmonk_subscriber_id bigint,
    tags          text[] default '{}',
    source        text,
    created_at    timestamptz default now(),
    updated_at    timestamptz default now()
);
create index if not exists gtm_contacts_domain_idx on gtm_contacts (company_domain);

-- ---------------------------------------------------------------- the event table
create table if not exists contact_events (
    id          bigserial primary key,
    contact_id  uuid references gtm_contacts(id) on delete cascade,
    email       text,                  -- denormalized for fast joins before contact exists
    company_id  uuid references scout_companies(id) on delete set null,
    event       text not null,         -- EMAIL_OPEN | EMAIL_CLICK | LINK_CLICK | PAGE_VIEW | PDF_DOWNLOAD
                                       -- | FORM_SUBMIT | CALENDAR_VIEW | REPLY | CALL
                                       -- | LINKEDIN_ENGAGEMENT | INSTAGRAM_ENGAGEMENT | X_ENGAGEMENT | WEBSITE_VISIT
    source      text,                  -- email | web | social | crm | manual
    campaign    text,                  -- campaign or sequence slug
    asset       text,                  -- link slug, pdf name, page path
    url         text,                  -- destination for clicks
    signal_weight int default 1,       -- 1=awareness 3=interest 6=intent 10=conversion
    metadata    jsonb default '{}'::jsonb,
    ip          text,
    user_agent  text,
    occurred_at timestamptz default now()
);
create index if not exists ce_contact_idx  on contact_events (contact_id, occurred_at desc);
create index if not exists ce_email_idx    on contact_events (lower(email), occurred_at desc);
create index if not exists ce_event_idx    on contact_events (event, occurred_at desc);
create index if not exists ce_campaign_idx on contact_events (campaign);
create index if not exists ce_occurred_idx on contact_events (occurred_at desc);

-- ---------------------------------------------------------------- tracked links (click attribution)
create table if not exists tracked_links (
    id          uuid primary key default gen_random_uuid(),
    slug        text unique not null,       -- /c/<slug>
    contact_id  uuid references gtm_contacts(id) on delete set null,
    email       text,
    destination text not null,
    campaign    text,
    asset       text,
    label       text,                       -- human name, e.g. "AI recruiting guide"
    clicks      int default 0,
    first_click_at timestamptz,
    last_click_at  timestamptz,
    created_at  timestamptz default now()
);
create index if not exists tl_contact_idx on tracked_links (contact_id);

-- ---------------------------------------------------------------- open pixels (one per send)
create table if not exists open_pixels (
    id          uuid primary key default gen_random_uuid(),
    token       text unique not null,       -- /o/<token>.gif
    contact_id  uuid references gtm_contacts(id) on delete set null,
    email       text,
    outbound_id uuid,                       -- email_send_queue.id
    campaign    text,
    opens       int default 0,
    first_open_at timestamptz,
    last_open_at  timestamptz,
    likely_apple_mpp boolean default false, -- heuristics: single fast open, no click, proxy UA
    created_at  timestamptz default now()
);
create index if not exists op_outbound_idx on open_pixels (outbound_id);

-- ---------------------------------------------------------------- rolling intent score
create table if not exists contact_scores (
    contact_id  uuid primary key references gtm_contacts(id) on delete cascade,
    email       text,
    company     text,
    score       int default 0,               -- sum of weighted events, time-decayed
    tier        text default 'cold',         -- hot | warm | nurture | cold
    last_event  text,
    last_event_at timestamptz,
    opens       int default 0,
    clicks      int default 0,
    replies     int default 0,
    page_views  int default 0,
    updated_at  timestamptz default now()
);
create index if not exists cs_score_idx on contact_scores (score desc);

-- ---------------------------------------------------------------- scoring + rollup
create or replace function signal_weight_for(ev text) returns int language sql immutable as $$
  select case ev
    when 'EMAIL_OPEN'    then 1
    when 'PAGE_VIEW'     then 3
    when 'WEBSITE_VISIT' then 3
    when 'LINK_CLICK'    then 4
    when 'EMAIL_CLICK'   then 5
    when 'PDF_DOWNLOAD'  then 6
    when 'CALENDAR_VIEW' then 8
    when 'FORM_SUBMIT'   then 10
    when 'REPLY'         then 10
    when 'CALL'          then 12
    else 2
  end;
$$;

-- time-decayed score: events in the last 7 days count full, older decay
create or replace view contact_intent as
select
    coalesce(c.id, gen_random_uuid()) as contact_id,
    e.email,
    max(c.company) as company,
    sum(e.signal_weight *
        greatest(0.15, exp(-extract(epoch from (now() - e.occurred_at)) / (14 * 86400))))::int as score,
    count(*) filter (where e.event = 'EMAIL_OPEN')  as opens,
    count(*) filter (where e.event in ('LINK_CLICK','EMAIL_CLICK')) as clicks,
    count(*) filter (where e.event = 'REPLY')       as replies,
    count(*) filter (where e.event = 'PAGE_VIEW')   as page_views,
    max(e.occurred_at) as last_event_at
from contact_events e
left join gtm_contacts c on c.id = e.contact_id
group by c.id, e.email
order by score desc;

-- refresh the scores table (call from n8n hourly, or cron)
create or replace function refresh_contact_scores() returns void language sql as $$
  insert into contact_scores (contact_id, email, company, score, tier, last_event, last_event_at,
                              opens, clicks, replies, page_views, updated_at)
  select
      c.id, c.email, c.company,
      coalesce(sum(e.signal_weight * greatest(0.15, exp(-extract(epoch from (now()-e.occurred_at))/(14*86400)))), 0)::int,
      case
        when coalesce(sum(e.signal_weight * greatest(0.15, exp(-extract(epoch from (now()-e.occurred_at))/(14*86400)))), 0) >= 25 then 'hot'
        when coalesce(sum(e.signal_weight * greatest(0.15, exp(-extract(epoch from (now()-e.occurred_at))/(14*86400)))), 0) >= 12 then 'warm'
        when coalesce(sum(e.signal_weight * greatest(0.15, exp(-extract(epoch from (now()-e.occurred_at))/(14*86400)))), 0) >= 4  then 'nurture'
        else 'cold' end,
      (array_agg(e.event order by e.occurred_at desc))[1],
      max(e.occurred_at),
      count(*) filter (where e.event='EMAIL_OPEN'),
      count(*) filter (where e.event in ('LINK_CLICK','EMAIL_CLICK')),
      count(*) filter (where e.event='REPLY'),
      count(*) filter (where e.event='PAGE_VIEW'),
      now()
  from gtm_contacts c
  left join contact_events e on e.contact_id = c.id
  group by c.id, c.email, c.company
  on conflict (contact_id) do update set
      score = excluded.score, tier = excluded.tier,
      last_event = excluded.last_event, last_event_at = excluded.last_event_at,
      opens = excluded.opens, clicks = excluded.clicks,
      replies = excluded.replies, page_views = excluded.page_views,
      updated_at = now();
$$;

-- ---------------------------------------------------------------- RLS
alter table gtm_contacts      enable row level security;
alter table contact_events  enable row level security;
alter table tracked_links   enable row level security;
alter table open_pixels     enable row level security;
alter table contact_scores  enable row level security;
