# Service: analytics

**Repo:** `launchpad-analytics` · **Language:** Python 3.14 (uv, grpcio, clickhouse-connect, confluent-kafka, arq, polars, anthropic SDK, pydantic v2, structlog) · **Ports:** gRPC 9000; HTTP 8080 (FastAPI: health/metrics only) · **Owns:** reads `analytics.*`, writes `analytics.deploy_markers`, manages `ask_*` ClickHouse users · **Risk:** high for Ask and user management, low/medium for queries

## 1. Purpose
Answers Insights queries, maintains deploy markers, detects Web Vitals regressions, and runs "Ask your data".

## 2. gRPC API (`launchpad.analytics.v1.AnalyticsService`)
All query RPCs take `Filter {app_id, from, to, interval (HOUR|DAY), path?, source?, country?, device?, route_kind (default PRODUCTION)}`; the service maps `app_id → app slug` via a cache fed by `app.created/app.deleted` (and `projects.GetApp` on miss).
| RPC | Source | Returns |
|---|---|---|
| `Overview` | `traffic_hourly` (+ `events` for bounce/duration) | visitors, pageviews, sessions, bounce_rate, avg_session_seconds, deltas vs previous equal period |
| `Timeseries` | `traffic_hourly` | buckets + `deploy_markers` in range |
| `Breakdown(by: PATH\|SOURCE\|REFERRER\|COUNTRY\|DEVICE\|BROWSER\|OS, limit≤100)` | rollups or `events` | rows |
| `Realtime` | `events` last 5 min | visitors, top pages |
| `Vitals(metric)` | `vitals_hourly` | p50/p75/p95 by path and by deployment |
| `DeploymentVitals(deployment_id)` | `vitals_hourly` | this vs previous production deployment per metric, `regressed` flags |
| `Funnel(steps[≤5], window_seconds)` | `events` with `windowFunnel` | step counts and conversion |
| `Ask(app_id, question)` | §6 | `{sql, chart, title, columns, rows, truncated}` |
Query user: `analytics_rw`. Every query parameterized (`{app:String}`, `{from:DateTime64(3)}`…); never string-formatted. Query timeout 5 s; results cached in Redis 30 s keyed by RPC+filter.

Bounce rate = sessions with exactly one pageview / sessions. Session duration = max(ts) − min(ts) per session (sessions with one event count as 0 s).

## 3. Deploy markers and vitals checks
- Consume `deployment.live.v1` → insert `deploy_markers` row → enqueue arq jobs `vitals_check(deployment_id)` at +30 min and +2 h.
- `vitals_check`: for each metric in (LCP, INP, CLS) and overall + top 10 paths: compare p75 of this deployment vs previous production deployment (same app) over equal windows; regression if p75 ≥ 1.2× previous AND both sides have n ≥ 50 → publish `vitals.regressed.v1` (topic `lp.insights`, key app_id), once per (deployment, metric, path).
- Preview deployments: compute but don't publish (shown in UI only).

## 4. Ask-user lifecycle (ADR-012)
- `app.created.v1` → create ClickHouse user `ask_<slug_with_underscores>` `IDENTIFIED WITH sha256_password BY '<derived>'` where the password is derived as `HMAC-SHA256(ask_key, app_id)` (hex) — nothing to store, re-derivable after restarts; grant `SELECT ON analytics.*`; assign settings profile `ask_profile`; create row policies `ask_<slug>_<table> ON analytics.<table> USING app = '<slug>' TO ask_<slug>` for `events`, `traffic_hourly`, `vitals_hourly`, `deploy_markers`.
- `app.deleted.v1` → drop user and its row policies.
- Startup reconciliation: ensure every app has its user/policies; remove orphans.
- `analytics_rw` holds only the minimal `ACCESS MANAGEMENT` grants needed for this (configured in infra).

## 5. Config
`LP_CH_ADDR`, `LP_CH_USER=analytics_rw`, `LP_CH_PASSWORD_FILE`, `LP_ASK_KEY_FILE` (HMAC key for derived ask passwords), `LP_REDIS_ADDR`, `LP_KAFKA_BROKERS`, `LP_LLM_API_KEY_FILE`, `LP_LLM_MODEL` (configurable; default a current Claude Sonnet model — check the model list at configuration time), `LP_PROJECTS_ADDR` + common.

## 6. Ask your data
1. Rate limit 10 questions/hour/app; question ≤ 500 chars.
2. Prompt: system instructions + schema description of the four tables (columns, meanings, example queries) + rules: single `SELECT` statement, ClickHouse dialect, must filter by time range, `LIMIT` ≤ 1000, no `SETTINGS` clause, no table functions, output JSON `{sql, chart: line|bar|table|number, title}`. Data values that appear in results are never fed back into a subsequent prompt.
3. Validate before executing: parse with `sqlglot` (ClickHouse dialect) → exactly one `SELECT`; only tables in `analytics.{events,traffic_hourly,vitals_hourly,deploy_markers}`; no `SETTINGS`, `INTO OUTFILE`, `FORMAT`, table functions or `system.*`; add `LIMIT 1000` if missing.
4. Execute as `ask_<slug>` (readonly=1 profile enforces limits; row policies enforce the app filter regardless of SQL).
5. On ClickHouse error: one retry with the error message given to the LLM; else return a friendly error.
6. Log (without result rows): question, SQL, duration, rows, outcome → audit table in Redis stream `ask:audit` (7 days) and metrics.

## 7. Tests
Query correctness vs raw `events` aggregates (fixture data); parameterization (no f-strings in SQL — lint rule); vitals regression thresholds and minimum samples; user lifecycle + reconciliation; **isolation test: as `ask_a`, `SELECT count() FROM analytics.events` returns only app A rows, and `SET`/`SETTINGS`/`url()`/`file()` attempts fail**; SQL validator property tests (`hypothesis`); prompt-injection fixtures (questions and stored page paths containing instructions).

## 8. Acceptance
Insights numbers within 2% of raw queries; `slow-lcp` deploy produces `vitals.regressed`; Ask answers "top pages last 24 hours" correctly and cannot read another app's data.
