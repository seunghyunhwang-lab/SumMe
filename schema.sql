-- SumMe feed_items table
-- Supabase PostgreSQL

create table if not exists feed_items (
    id               bigserial primary key,
    category         text        not null check (category in ('news', 'policy', 'stock', 'beauty')),
    feed_type        text        not null check (feed_type in ('realtime', 'daily', 'weekly')),
    title            text        not null,
    summary          jsonb,                   -- 실시간: 1줄(text), 일일: 3줄(array), 주간: text
    importance_score integer     default 0,   -- 1~5
    source_url       text        not null,
    published_at     timestamptz,
    crawled_at       timestamptz default now(),
    why_important    text,
    is_duplicate     boolean     default false,

    constraint feed_items_source_url_key unique (source_url)
);

-- 피드 조회 인덱스
create index if not exists idx_feed_items_category    on feed_items (category);
create index if not exists idx_feed_items_feed_type   on feed_items (feed_type);
create index if not exists idx_feed_items_importance  on feed_items (importance_score desc);
create index if not exists idx_feed_items_crawled_at  on feed_items (crawled_at desc);
create index if not exists idx_feed_items_is_duplicate on feed_items (is_duplicate);
