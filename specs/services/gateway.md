# Service: gateway

**Repo:** `launchpad-gateway` · **Language:** Go 1.27 (`chi`) · **Ports:** HTTP 8080 (public API + health/metrics on a separate internal listener 8081) · **Owns:** Redis keys `gw:*` · **Risk:** high for auth/CSRF/rate limiting, low/medium for routes

## 1. Purpose
The only API the dashboard and CLI use. Authenticates, enforces limits, translates REST to gRPC, and serves SSE streams. Implements `06-public-api.md` exactly.

## 2. Middleware chain (order)
1. Request ID (`X-Request-Id` accept-or-generate, UUIDv7) + OTel span.
2. Recover → problem+json 500.
3. Body limit 1 MB (env var values are additionally limited to 32 KB by projects).
4. CORS: allow only `https://launchpad.<domain>` with credentials.
5. Auth: cookie `lp_session` or `Authorization: Bearer lp_…` → `identity.Authenticate` (cache result 30 s in-process keyed by token hash; drop cache entry on `token.revoked` event); attach user JWT to outgoing gRPC metadata.
6. CSRF for cookie-authenticated mutating requests (double-submit `lp_csrf` cookie + `X-CSRF-Token`).
7. Rate limit: Redis token bucket 20 rps / burst 40 per principal; 5 rps for `/insights/ask`.
8. Idempotency: for mutating requests with `Idempotency-Key`, store `{status, body}` 24 h in Redis keyed by principal+key; concurrent duplicate → 409 `idempotency-in-progress`.

## 3. Routes
All endpoints in `06-public-api.md` §3. gRPC deadlines: 3 s default, 10 s for Ask, streams unbounded. gRPC → HTTP error mapping per `03-conventions.md` §4.

## 4. SSE
- `/deployments/{id}/logs/stream` and `/apps/{id}/runtime-logs/stream`: proxy `logs.TailLogs`; translate lines to `event: log`; close build streams on terminal status.
- `/deployments/{id}/events`: gateway consumes `deployment.status_changed.v1` (group `gateway-<instance>`, start at latest) into an in-memory hub keyed by deployment_id; first send current status from `deployer.GetDeployment`.
- Heartbeat 15 s; `X-Accel-Buffering: no`; max 10 streams per principal.

## 5. Metrics endpoint for apps
`/apps/{id}/metrics?range=` builds PromQL from fixed templates (cAdvisor `container_cpu_usage_seconds_total`, `container_memory_working_set_bytes`, network rx/tx, restarts) filtered by label `container_label_lp_app_id="<uuid>"` — the app ID is validated as a UUID; no client-provided PromQL.

## 6. Platform endpoint
`/platform`: fan-out `/readyz` to every service (internal URLs from config, 1 s timeout), Prometheus queries for lag/outbox/DLQ/cert expiry/disk/memory; cached 10 s.

## 7. OpenAPI
Route definitions generate `openapi.yaml` (OpenAPI 3.1) in CI (`make openapi`); CI fails if it differs from the committed file; dashboard and CLI may generate clients from it.

## 8. Config
`LP_REDIS_ADDR`, `LP_IDENTITY_ADDR`, `LP_PROJECTS_ADDR`, `LP_DEPLOYER_ADDR`, `LP_LOGS_ADDR`, `LP_ANALYTICS_ADDR`, `LP_NOTIFIER_ADDR`, `LP_SCM_ADDR`, `LP_PROMETHEUS_URL`, `LP_DASHBOARD_ORIGIN`, `LP_READYZ_TARGETS` + common.

## 9. Tests
Auth (cookie, bearer, revoked, expired); CSRF required/optional paths; rate limit; idempotency replay and concurrency; error mapping table; SSE resume with `Last-Event-ID`; PromQL template injection attempts rejected; OpenAPI drift check.

## 10. Acceptance
Every endpoint in `06-public-api.md` implemented with the documented shapes; security tests pass; p95 < 100 ms for non-streaming reads on the server (excluding Ask).
