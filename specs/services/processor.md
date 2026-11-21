# Service: processor

**Repo:** `launchpad-processor` · **Language:** Rust (`launchpad-rust-kit`, rdkafka, clickhouse, maxminddb, uaparser, siphasher, redis) · **Ports:** 8080 (health/metrics) · **Owns:** writes `analytics.events` (`05-data.md` §7.3) · **Risk:** medium (privacy-relevant changes: high)

## 1. Purpose
Turns raw tracker events into privacy-preserving, enriched rows in ClickHouse.

## 2. Pipeline (consumer group `processor`, topic `events.raw`)
For each `insights.event.v1`:
1. **Bot filter:** UA matches bot list (embedded, updated with uaparser regexes + `bot|crawl|spider|headless|lighthouse|preview` patterns) or empty UA → drop (`dropped{reason=bot}`).
2. **Geo:** MaxMind GeoLite2-City (`/geoip/GeoLite2-City.mmdb`, hot-reloaded when the file changes) → country (ISO-2), region, city. **The IP is not stored or logged; it is dropped after step 4.**
3. **UA parse:** browser family, OS family, device (`mobile|tablet|desktop`).
4. **Visitor ID (cookieless):** `visitor_id = siphash64(daily_salt, app_id || ip || user_agent)`. Daily salt: 16 random bytes in Redis `salt:<YYYY-MM-DD>` (UTC), created on first use with `SET NX EX 172800`; salts older than yesterday are deleted. Events use the salt of their `received_at` date.
5. **URL normalization:** split `u` into path + query; keep only `utm_source`, `utm_medium`, `utm_campaign`; lowercase host-less path; strip trailing `/` except root; collapse numeric/UUID segments? **No** (keep paths as sent; owners control their URLs).
6. **Referrer:** extract domain; same-site referrers (same host) → `direct`; classify `source`: utm present → `campaign`; known search engines → `search`; known social → `social`; empty → `direct`; else `referral`.
7. **Session:** Redis key `sess:<app_id>:<visitor_id>` → session_id (random u64) with TTL 30 min, refreshed on each event (`SET` with `EX 1800`, `GET` first).
8. Map to `analytics.events` row (`type`, `name`, `value`, `props`, `screen_w`, `event_id = UUIDv7 from envelope id`).
9. Batch insert (flush at 5,000 rows or 1 s); commit Kafka offsets **after** insert success. Dedupe event_ids within a batch.
10. Poison message (schema invalid, repeated insert failure for a single row) → `events.dlq`.

## 3. Config
`LP_KAFKA_BROKERS`, `LP_REDIS_ADDR`, `LP_CH_ADDR`, `LP_CH_USER=processor_w`, `LP_CH_PASSWORD_FILE`, `LP_GEOIP_PATH` + common.

## 4. Performance / freshness
≥ 5k events/s sustained on 1 core; p95 freshness ≤ 10 s; memory < 128 MB (+ mmdb ~70 MB mapped).

## 5. Tests
Bot list; geo lookup with test mmdb; visitor hash stability within a day and change across days; salt deletion; referrer classification table; session expiry; batch/offset semantics (kill mid-batch → no loss, possible duplicates deduped by ReplacingMergeTree); IP never present in ClickHouse rows or logs (assertion over captured logs and inserted rows).

## 6. Acceptance
Kill `processor` mid-batch → 0 events lost; IP appears nowhere at rest; freshness target met under k6 load.
