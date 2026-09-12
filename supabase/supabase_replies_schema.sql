-- REPLY + RAG SCHEMA — inbound reply capture, knowledge base, drafts, routing
-- Run: psql $SUPABASE_DB_URL -f supabase_replies_schema.sql
-- (or apply via the Supabase SQL editor / REST with the service key)

-- ---------------------------------------------------------------- knowledge (RAG)
create table if not exists reply_knowledge (
    id           uuid primary key default gen_random_uuid(),
    slug         text unique not null,
    title        text not null,
    category     text,                 -- offer | objection | proof | process | pricing | recruiting | gtm | personal
    content      text not null,        -- the actual knowledge, written for retrieval
    tags         text[] default '{}',
    priority     int default 50,       -- higher = retrieved first when tied
    source       text,                 -- file path / url
    embedding    vector(1536),         -- optional: OpenAI text-embedding-3-small
    created_at   timestamptz default now(),
    updated_at   timestamptz default now()
);
create index if not exists reply_knowledge_tags_idx on reply_knowledge using gin (tags);
create index if not exists reply_knowledge_cat_idx on reply_knowledge (category);

-- ---------------------------------------------------------------- inbound replies
create table if not exists email_replies (
    id                uuid primary key default gen_random_uuid(),
    -- linkage back to the outbound
    lead_id           uuid,
    outbound_id       uuid,            -- email_send_queue.id when we can match it
    from_email        text not null,
    from_name         text,
    to_mailbox        text,            -- which of our mailboxes received it
    subject           text,
    body              text,
    received_at       timestamptz default now(),
    -- classification
    intent            text,            -- interested | question | objection | not_interested | unsubscribe | ooo | referral | wrong_person
    sentiment         text,            -- positive | neutral | negative
    urgency           text,            -- hot | warm | nurture | parked
    -- routing / handling
    status            text default 'new',  -- new | drafted | approved | sent | dismissed | escalated
    routed_to         text,            -- brendan@tryviewsai.com | chatwoot | scout | other
    chatwoot_conversation_id bigint,
    chatwoot_contact_id      bigint,
    -- RAG output
    draft_reply       text,
    draft_model       text,
    retrieved_ids     uuid[],
    confidence        numeric(4,3),
    -- metadata
    source            text default 'forward',  -- forward | graph | zapmail | manual | api
    raw               jsonb,
    tags              text[] default '{}',
    created_at        timestamptz default now(),
    updated_at        timestamptz default now()
);
create index if not exists email_replies_from_idx on email_replies (from_email);
create index if not exists email_replies_status_idx on email_replies (status);
create index if not exists email_replies_received_idx on email_replies (received_at desc);
create index if not exists email_replies_intent_idx on email_replies (intent);

-- ---------------------------------------------------------------- routing rules
create table if not exists reply_routing_rules (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    priority    int default 50,          -- lower = evaluated first
    match_intent text,                    -- intent to match (null = any)
    match_tags   text[] default '{}',
    match_from   text,                    -- domain/email contains
    action       text not null,           -- forward | chatwoot_assign | chatwoot_label | notify_slack | auto_draft | escalate
    action_value text,                    -- team id, label, address
    enabled     boolean default true,
    created_at  timestamptz default now()
);

-- ---------------------------------------------------------------- helpful views
create or replace view reply_dashboard as
select
    date_trunc('day', received_at) as day,
    intent,
    sentiment,
    count(*) as replies,
    count(*) filter (where status in ('drafted','approved','sent')) as handled
from email_replies
group by 1,2,3
order by 1 desc;

-- ---------------------------------------------------------------- RLS
alter table reply_knowledge      enable row level security;
alter table email_replies        enable row level security;
alter table reply_routing_rules  enable row level security;
-- service role bypasses RLS; no public policies (internal tables only)

-- ---------------------------------------------------------------- seed routing rules
insert into reply_routing_rules (name, priority, match_intent, action, action_value) values
    ('unsubscribe → suppress immediately', 10, 'unsubscribe', 'chatwoot_label', 'unsubscribe'),
    ('hot interest → notify + assign',     20, 'interested',  'chatwoot_assign', '1'),
    ('objection → draft + escalate',       30, 'objection',   'auto_draft', 'escalate'),
    ('question → auto draft',              40, 'question',    'auto_draft', 'answer'),
    ('not interested → park',              50, 'not_interested', 'chatwoot_label', 'not-interested'),
    ('out of office → park 7d',            60, 'ooo',         'chatwoot_label', 'ooo'),
    ('everything else → forward to Brendan', 90, null,        'forward', 'brendan@tryviewsai.com')
on conflict do nothing;
