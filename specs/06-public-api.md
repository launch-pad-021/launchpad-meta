# 06 — Public API (gateway)

Base URL: `https://api.launchpad.<domain>/v1`. JSON over HTTPS. Used only by the dashboard and the CLI. The gateway also generates `openapi.yaml` (OpenAPI 3.1) from its route definitions in CI; that file must match this document.

## 1. Auth
- **Dashboard:** `lp_session` cookie (HttpOnly, Secure, SameSite=Lax, 14-day sliding). CSRF: double-submit token — `GET /v1/csrf` sets `lp_csrf` cookie; mutating requests must send `X-CSRF-Token` equal to it.
- **CLI:** `Authorization: Bearer lp_<token>`.
- OAuth flow: `GET /v1/auth/github/start?redirect=/apps` → 302 to GitHub → `GET /v1/auth/github/callback?code&state` → sets cookie → 302 to redirect (only relative paths allowed). `POST /v1/auth/logout`.

## 2. Common
- Pagination: `?page_size=50&page_token=...` → `{"items":[...],"next_page_token":"..."}` (max 200).
- Idempotency: `Idempotency-Key` header on POST/PUT/PATCH/DELETE.
- Errors: RFC 9457 problem+json (`03-conventions.md` §4).
- Rate limits: 20 req/s per session/token (burst 40); `429` with `Retry-After`.
- Every response carries `X-Request-Id` (also in traces/logs).

## 2.1 Representations
```json
// App
{ "id":"uuid","name":"myapp","repo_full_name":"tejas/myapp","root_dir":".","default_branch":"main",
  "build_strategy":"auto","port":3000,"health_path":"/","cpu_limit":0.5,"mem_limit_mb":512,
  "previews_enabled":true,"insights_enabled":true,"insights_inject":true,
  "production_url":"https://myapp.apps.example.com",
  "current_production": { "deployment_id":"uuid","short_id":"7f3a1b2c","commit_sha":"...","live_at":"..." } | null,
  "created_at":"...","updated_at":"..." }

// Deployment
{ "id":"uuid","short_id":"7f3a1b2c","app_id":"uuid","app_name":"myapp","branch":"main","kind":"production",
  "commit_sha":"...","commit_message":"...","trigger":"push","rollback_of":null,
  "status":"live","saga_step":"routed","urls":["https://myapp.apps.example.com","https://d-7f3a1b2c--myapp.apps.example.com"],
  "build_ms":61234,"vitals_regressed":false,"error_stage":null,"error":null,
  "created_at":"...","started_at":"...","live_at":"...","finished_at":"..." }

// EnvVar (value masked unless ?reveal=1)
{ "key":"DATABASE_URL","scope":"production","value":"••••••","updated_at":"..." }

// LogLine
{ "seq":42,"ts":"...","source":"build","stream":"stdout","line":"Compiled successfully" }
```

## 3. Endpoints
| Method | Path | Backend | Notes |
|---|---|---|---|
| GET | `/v1/me` | identity | `{user, scopes}` |
| GET | `/v1/repos` | scm.ListInstalledRepos | Repos the GitHub App can access (for the new-app picker) |
| GET | `/v1/repos/{owner}/{name}/branches` | scm.ListBranches | |
| GET | `/v1/apps` | projects (+deployer for current_production) | |
| POST | `/v1/apps` | projects | body: App create fields (`name`, `repo_full_name` required) |
| GET/PATCH/DELETE | `/v1/apps/{id}` | projects | DELETE is async: returns 202; cleanup via `app.deleted` |
| GET | `/v1/apps/{id}/env` | projects | masked |
| PUT | `/v1/apps/{id}/env/{key}` | projects | `{value, scope}` |
| DELETE | `/v1/apps/{id}/env/{key}?scope=` | projects | |
| GET | `/v1/apps/{id}/deployments?branch=&status=` | deployer | |
| POST | `/v1/apps/{id}/deployments` | deployer | `{branch?, commit_sha?}` → 202 Deployment |
| GET | `/v1/deployments/{id}` | deployer | |
| POST | `/v1/deployments/{id}/rollback` | deployer | Only `live`/`superseded` production deploys; → 202 new Deployment |
| POST | `/v1/deployments/{id}/cancel` | deployer | |
| GET | `/v1/deployments/{id}/logs?source=build&after_seq=&limit=` | logs | |
| GET | `/v1/deployments/{id}/logs/stream?source=build&after_seq=` | logs.TailLogs | **SSE** |
| GET | `/v1/deployments/{id}/events` | gateway (consumer) | **SSE** of status changes |
| GET | `/v1/apps/{id}/runtime-logs/stream` | logs.TailLogs(source=runtime, live deployment) | **SSE** |
| GET | `/v1/apps/{id}/logs/search?q=&from=&to=` | logs | |
| GET | `/v1/apps/{id}/metrics?range=1h` | Prometheus (PromQL built server-side, never from client input) | CPU, memory, net rx/tx, restarts |
| GET | `/v1/apps/{id}/insights/overview` · `/timeseries` · `/breakdown?by=` · `/realtime` · `/vitals?metric=` · `/funnels?steps=&window=` | analytics | Query params: `from,to,interval,path,source,country,device,route_kind` |
| GET | `/v1/deployments/{id}/vitals` | analytics | |
| POST | `/v1/apps/{id}/insights/ask` | analytics | `{question}` → `{sql, chart, title, columns, rows}` |
| GET/POST/DELETE | `/v1/tokens` · `/v1/tokens/{id}` | identity | Token value returned once on POST |
| GET/PUT/DELETE | `/v1/notifications/channels` · `/{id}`; POST `/{id}/test` | notifier | |
| GET | `/v1/platform` | gateway (aggregates `/readyz`, Prometheus) | Service health, consumer lag, outbox backlog |

## 4. SSE format
```
event: log            data: {"seq":43,"ts":"...","source":"build","stream":"stdout","line":"..."}
event: status         data: {"deployment_id":"...","from":"building","to":"starting","saga_step":"built","at":"..."}
event: heartbeat      data: {}          (every 15 s)
event: end            data: {"reason":"deployment_finished"}
```
`id:` = `seq` for logs so `Last-Event-ID` resumes. Max 10 concurrent streams per session.
