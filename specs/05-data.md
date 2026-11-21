# 05 — Data

Each service owns its own Postgres database and DB user (`<service>` / `<service>_app`). **No foreign keys across services**; references are plain UUID columns kept consistent by events. Migrations live in the owning repo and run as a one-shot container before the service starts (expand-only; see §6).

Every service that publishes events from DB writes has `outbox` and `processed_events`:

```sql
CREATE TABLE outbox (
  id           uuid PRIMARY KEY,                 -- = event id
  topic        text NOT NULL,
  key          text NOT NULL,                    -- partition key (app_id)
  envelope     jsonb NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz
);
CREATE INDEX outbox_unpublished ON outbox (created_at) WHERE published_at IS NULL;

CREATE TABLE processed_events (
  event_id     uuid PRIMARY KEY,
  processed_at timestamptz NOT NULL DEFAULT now()  -- pruned after 7 days
);
```

## 1. identity
```sql
CREATE TABLE users (
  id            uuid PRIMARY KEY DEFAULT uuidv7(),
  github_id     bigint UNIQUE NOT NULL,
  github_login  text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE sessions (
  id_hash     bytea PRIMARY KEY,                   -- sha256(cookie value)
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at  timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz NOT NULL,                -- 14 days, sliding
  user_agent  text
);
CREATE TABLE api_tokens (
  id          uuid PRIMARY KEY DEFAULT uuidv7(),
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name        text NOT NULL,
  prefix      text NOT NULL,                       -- first 8 chars shown in UI ("lp_ab12cd34")
  token_hash  bytea NOT NULL UNIQUE,               -- sha256
  scopes      text[] NOT NULL DEFAULT '{full}',
  last_used   timestamptz,
  expires_at  timestamptz,
  revoked_at  timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE oauth_states (
  state       text PRIMARY KEY,
  pkce_verifier text NOT NULL,
  redirect_to text NOT NULL,
  expires_at  timestamptz NOT NULL                 -- 10 min
);
CREATE TABLE signing_keys (                        -- Ed25519 for JWTs; rotated (13-runbooks.md)
  kid         text PRIMARY KEY,
  private_enc bytea NOT NULL,                      -- AES-256-GCM with identity master key
  public_key  bytea NOT NULL,
  active      boolean NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  retired_at  timestamptz
);
```

## 2. projects
```sql
CREATE TABLE apps (
  id               uuid PRIMARY KEY DEFAULT uuidv7(),
  name             text UNIQUE NOT NULL CHECK (name ~ '^[a-z0-9]([a-z0-9-]{0,38}[a-z0-9])?$'),
  repo_full_name   text NOT NULL,
  root_dir         text NOT NULL DEFAULT '.',
  default_branch   text NOT NULL DEFAULT 'main',
  build_strategy   text NOT NULL DEFAULT 'auto' CHECK (build_strategy IN ('auto','railpack','dockerfile')),
  port             int  NOT NULL DEFAULT 3000 CHECK (port BETWEEN 1 AND 65535),
  health_path      text NOT NULL DEFAULT '/',
  cpu_limit        numeric(4,2) NOT NULL DEFAULT 0.50 CHECK (cpu_limit BETWEEN 0.1 AND 2),
  mem_limit_mb     int  NOT NULL DEFAULT 512 CHECK (mem_limit_mb BETWEEN 64 AND 4096),
  previews_enabled boolean NOT NULL DEFAULT true,
  insights_enabled boolean NOT NULL DEFAULT true,
  insights_inject  boolean NOT NULL DEFAULT true,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (repo_full_name, root_dir)
);
CREATE TABLE env_vars (
  id         uuid PRIMARY KEY DEFAULT uuidv7(),
  app_id     uuid NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
  key        text NOT NULL CHECK (key ~ '^[A-Z_][A-Z0-9_]{0,127}$'),
  value_enc  bytea NOT NULL,                        -- AES-256-GCM: 12-byte nonce || ciphertext || tag; AAD = app_id||key||scope
  scope      text NOT NULL DEFAULT 'all' CHECK (scope IN ('all','production','preview')),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (app_id, key, scope)
);
```
Reserved keys (rejected): `PORT`, any `LAUNCHPAD_*`. Max 100 vars/app, 32 KB per value.

## 3. scm
```sql
CREATE TABLE webhook_deliveries (
  delivery_id text PRIMARY KEY,                     -- X-GitHub-Delivery
  event       text NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now()    -- pruned after 30 days
);
CREATE TABLE installations (
  repo_full_name  text PRIMARY KEY,
  installation_id bigint NOT NULL,
  updated_at      timestamptz NOT NULL DEFAULT now()
);
```

## 4. deployer
```sql
CREATE TYPE deploy_status AS ENUM
  ('queued','building','starting','health_checking','routing','live','superseded','failed','cancelled');

CREATE TABLE deployments (
  id               uuid PRIMARY KEY DEFAULT uuidv7(),
  short_id         text UNIQUE NOT NULL,            -- 8 hex chars
  app_id           uuid NOT NULL,
  app_name         text NOT NULL,
  branch           text NOT NULL,
  kind             text NOT NULL CHECK (kind IN ('production','preview')),
  commit_sha       text NOT NULL CHECK (commit_sha ~ '^[0-9a-f]{40}$'),
  commit_message   text,
  trigger          text NOT NULL CHECK (trigger IN ('push','manual','rollback','cli')),
  rollback_of      uuid,
  status           deploy_status NOT NULL DEFAULT 'queued',
  saga_step        text NOT NULL DEFAULT 'created',
  attempt          int  NOT NULL DEFAULT 0,
  image_ref        text,
  image_digest     text,
  container_id     text,
  upstream         text,
  node             text NOT NULL DEFAULT 'node-1',
  build_config     jsonb,                           -- effective port/health/resources
  vitals_regressed boolean NOT NULL DEFAULT false,
  error_stage      text,
  error            text,
  build_ms         int,
  created_at       timestamptz NOT NULL DEFAULT now(),
  started_at       timestamptz,
  live_at          timestamptz,
  finished_at      timestamptz
);
CREATE INDEX ON deployments (app_id, branch, created_at DESC);
CREATE INDEX deployments_active ON deployments (status) WHERE status NOT IN ('live','superseded','failed','cancelled');
```

## 5. router / notifier
```sql
-- router
CREATE TABLE routes (
  hostname       text PRIMARY KEY,
  app_id         uuid NOT NULL,
  app_name       text NOT NULL,
  deployment_id  uuid NOT NULL,
  kind           text NOT NULL CHECK (kind IN ('production','preview','immutable')),
  upstream       text NOT NULL,                     -- http://lp-<app>-<short>:<port>
  health_path    text NOT NULL DEFAULT '/',
  insights       boolean NOT NULL DEFAULT true,
  inject         boolean NOT NULL DEFAULT true,
  updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON routes (app_id);

-- notifier
CREATE TABLE channels (
  id         uuid PRIMARY KEY DEFAULT uuidv7(),
  kind       text NOT NULL CHECK (kind IN ('telegram','email')),
  target     text NOT NULL,                         -- chat id / address
  events     text[] NOT NULL,
  enabled    boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE notifications_sent (                   -- dedupe + rate limiting
  dedupe_key text PRIMARY KEY,
  sent_at    timestamptz NOT NULL DEFAULT now()
);
```

## 6. Migration rules (expand/contract)
1. **Expand** (allowed any time): add table, add nullable column or column with default, add index `CONCURRENTLY`, add enum value.
2. **Migrate**: backfill in batches in application code or a one-shot job.
3. **Contract** (separate later release, high risk): drop/rename column/table, add NOT NULL without default, narrow types.
Every release must work with both the previous and the new schema (so rollback never needs a down-migration).

## 7. ClickHouse
### 7.1 Databases and users
| User | Rights | Used by |
|---|---|---|
| `logs_rw` | INSERT/SELECT on `logs.*` | logs |
| `processor_w` | INSERT on `analytics.events` | processor |
| `analytics_rw` | SELECT on `analytics.*`, INSERT on `analytics.deploy_markers`, `ACCESS MANAGEMENT` limited to users `ask_*` and their row policies | analytics |
| `ask_<app_slug>` (one per app) | SELECT on `analytics.*`; settings profile `ask_profile`; row policies `app = '<slug>'` on every analytics table | analytics "Ask your data" only |

`ask_profile`: `readonly = 1`, `max_execution_time = 5`, `max_result_rows = 10000`, `result_overflow_mode = 'break'`, `max_memory_usage = 1000000000`, `max_rows_to_read = 200000000`. With `readonly = 1` the user cannot change any setting, run DDL/writes, or use most table functions. Isolation does not depend on the generated SQL (see ADR-012).

### 7.2 logs
```sql
CREATE DATABASE IF NOT EXISTS logs;
CREATE TABLE logs.lines (
  app_id        UUID,
  deployment_id UUID,
  source        LowCardinality(String),   -- build | runtime
  stream        LowCardinality(String),   -- system | stdout | stderr
  seq           UInt64,
  ts            DateTime64(3, 'UTC'),
  line          String,
  INDEX line_tokens line TYPE tokenbf_v1(8192, 3, 0) GRANULARITY 4
) ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (deployment_id, source, seq)
TTL toDateTime(ts) + INTERVAL 30 DAY;
```

### 7.3 analytics
```sql
CREATE DATABASE IF NOT EXISTS analytics;

CREATE TABLE analytics.events (
  event_id        UUID,
  app             LowCardinality(String),
  app_id          UUID,
  deployment_id   UUID,
  route_kind      LowCardinality(String),    -- production | preview | immutable
  ts              DateTime64(3, 'UTC'),
  type            LowCardinality(String),    -- pageview | custom | web_vital
  name            LowCardinality(String),    -- custom event name or vital name (LCP, INP, CLS, FCP, TTFB)
  path            String,
  referrer_domain LowCardinality(String),
  source          LowCardinality(String),    -- search | social | direct | referral | campaign
  utm_source      LowCardinality(String),
  utm_medium      LowCardinality(String),
  utm_campaign    LowCardinality(String),
  country         LowCardinality(String),
  region          LowCardinality(String),
  city            String,
  browser         LowCardinality(String),
  os              LowCardinality(String),
  device          LowCardinality(String),    -- desktop | mobile | tablet
  screen_w        UInt16,
  visitor_id      UInt64,
  session_id      UInt64,
  value           Nullable(Float64),
  props           Map(String, String)
) ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(ts)
ORDER BY (app, toDate(ts), type, event_id)
TTL toDateTime(ts) + INTERVAL 13 MONTH;

CREATE TABLE analytics.traffic_hourly (
  app LowCardinality(String), route_kind LowCardinality(String), hour DateTime('UTC'),
  path String, source LowCardinality(String), country LowCardinality(String), device LowCardinality(String),
  pageviews AggregateFunction(count),
  visitors  AggregateFunction(uniq, UInt64),
  sessions  AggregateFunction(uniq, UInt64)
) ENGINE = AggregatingMergeTree
ORDER BY (app, route_kind, hour, path, source, country, device);

CREATE MATERIALIZED VIEW analytics.traffic_hourly_mv TO analytics.traffic_hourly AS
SELECT app, route_kind, toStartOfHour(ts) AS hour, path, source, country, device,
       countState() AS pageviews, uniqState(visitor_id) AS visitors, uniqState(session_id) AS sessions
FROM analytics.events WHERE type = 'pageview'
GROUP BY app, route_kind, hour, path, source, country, device;

CREATE TABLE analytics.vitals_hourly (
  app LowCardinality(String), deployment_id UUID, hour DateTime('UTC'),
  path String, metric LowCardinality(String), device LowCardinality(String),
  q AggregateFunction(quantiles(0.5, 0.75, 0.95), Float64),
  n AggregateFunction(count)
) ENGINE = AggregatingMergeTree
ORDER BY (app, metric, hour, deployment_id, path, device);

CREATE MATERIALIZED VIEW analytics.vitals_hourly_mv TO analytics.vitals_hourly AS
SELECT app, deployment_id, toStartOfHour(ts) AS hour, path, name AS metric, device,
       quantilesState(0.5, 0.75, 0.95)(value) AS q, countState() AS n
FROM analytics.events WHERE type = 'web_vital' AND value IS NOT NULL
GROUP BY app, deployment_id, hour, path, metric, device;

CREATE TABLE analytics.deploy_markers (
  app LowCardinality(String), deployment_id UUID, ts DateTime('UTC'),
  kind LowCardinality(String), commit_sha String, commit_message String
) ENGINE = ReplacingMergeTree ORDER BY (app, ts, deployment_id);
```
Note: the materialized views aggregate on insert; with `ReplacingMergeTree` dedupe on `events`, a duplicate insert is counted once in `events` (after merge) but may be counted twice in rollups. `processor` MUST dedupe within its batch and the window between retries is small; Insights numbers are allowed a 2% tolerance (00-product §6).

## 8. Retention summary
| Data | Retention |
|---|---|
| Postgres business data | Until deleted by the owner |
| `processed_events`, published `outbox` | 7 days |
| `webhook_deliveries` | 30 days |
| Build/runtime logs | 30 days |
| Analytics raw events | 13 months; rollups kept indefinitely |
| Kafka topics | per `03-conventions.md` §6.2 |
| Traces | 3 days · Metrics: 15 days |
| Daily visitor salts | Deleted after 24 h |
| Images in registry | Last 10 per app + any image referenced by a non-terminal or live deployment |
