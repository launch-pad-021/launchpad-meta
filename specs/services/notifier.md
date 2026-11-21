# Service: notifier

**Repo:** `launchpad-notifier` · **Language:** TypeScript on Node 26 (`launchpad-ts-kit`) · **Ports:** 9000 / 8080 · **Owns:** Postgres `notifier` (`05-data.md` §5) · **Risk:** medium

## 1. Purpose
Delivers alerts to the owner (Telegram; email optional) from platform events and Prometheus alerts.

## 2. Inputs
- Events: `deployment.failed.v1`, `vitals.regressed.v1`, `container.exited.v1` (only when `restart_count ≥ 3` or `oom_killed`).
- HTTP `POST /internal/alerts` (Prometheus webhook format; only reachable on `lp_internal`; shared-secret header `X-LP-Alert-Token`).
- gRPC (`launchpad.notifier.v1.NotifierService`): `ListChannels`, `UpsertChannel`, `DeleteChannel`, `SendTest(channel_id)`.

## 3. Rules
- A channel receives an event if its `events[]` contains the event type (or `alert.<severity>` for Prometheus alerts).
- Dedupe key: `<type>:<deployment_id|alertname+labels hash>`; same key suppressed for 30 min.
- Global rate limit: 20 messages/hour; overflow summarized in one message.
- Message content: title, app, branch, short commit, stage/error (≤ 300 chars), links (dashboard deployment page, Jaeger trace if `trace_id`). No secrets, no env values, no IPs.
- Telegram: Bot API `sendMessage` with `parse_mode=MarkdownV2` (escape all dynamic text); retry 3× on 5xx/429 honoring `retry_after`.
- Critical Prometheus alerts additionally trigger `repository_dispatch` (`event_type: lp-incident`) on `launchpad-meta` using a token with only `contents:read`+`metadata` and dispatch permission (stored as `meta_dispatch_token`).

## 4. Config
`LP_PG_DSN_FILE`, `LP_TELEGRAM_BOT_TOKEN_FILE`, `LP_ALERT_TOKEN_FILE`, `LP_META_DISPATCH_TOKEN_FILE`, `LP_DASHBOARD_URL` + common.

## 5. Tests
Routing per channel; dedupe window; rate limit summary; MarkdownV2 escaping (fuzz with fast-check); Telegram mock 429 handling; alert webhook auth.

## 6. Acceptance
`crash-on-start` deploy → one Telegram message within 30 s; repeated failures within 30 min → no duplicates.
