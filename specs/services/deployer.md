# Service: deployer

**Repo:** `launchpad-deployer` · **Language:** Go 1.27 · **Ports:** 9000 / 8080 · **Owns:** Postgres `deployer` (`05-data.md` §4) · **Risk:** medium; high for saga compensation/rollback changes

## 1. Purpose
Owns the deployment lifecycle: creates deployments, runs the deploy saga across builder, runtime-agent and router, handles cancellation, rollback and cleanup.

## 2. State machine
```
queued ─▶ building ─▶ starting ─▶ health_checking ─▶ routing ─▶ live ─▶ superseded
   │          │           │              │              │
   └──────────┴───────────┴──────────────┴──────────────┴─▶ failed | cancelled
```
- Transitions only via `internal/fsm` (table-driven; invalid → error). Terminal: `live`(until superseded), `superseded`, `failed`, `cancelled`.
- Each transition: update row + outbox `deployment.status_changed.v1` in one transaction.
- `saga_step` values: `created → build_requested → built → env_fetched → container_started → healthy → routed → previous_drained`.

## 3. Saga (see `01-architecture.md` §4)
| Step | Action | Timeout / retries | On failure |
|---|---|---|---|
| request build | outbox `build.requested.v1` | — | — |
| await build | consume `build.started/completed/failed` | build timeout owned by builder (15 min); deployer watchdog 20 min | `failed` (stage `build`) |
| fetch env | `projects.GetRuntimeEnv(app_id, kind)` | 3 retries | `failed` (stage `env`) |
| start | `runtime-agent.StartContainer` (idempotent by deployment_id) | 3 retries | `failed` (stage `start`) |
| health | `runtime-agent.CheckHealth` every 1 s; success = 2 consecutive 2xx/3xx | 60 s (configurable per app later) | stop container; `failed` (stage `health`) |
| route | `router.SetRoute` for each hostname (production or preview host + immutable host) | 3 retries | remove new routes, stop container; `failed` (stage `route`) |
| live | status `live`; outbox `deployment.live.v1` | — | — |
| drain | after 10 s: previous deployment of same (app, kind[, branch]) → `superseded`; `StopContainer(previous)` | best effort, retried by janitor | logged, alert if > 3 failures |

Recovery: on startup and every 30 s, a reconciler loads non-terminal deployments and continues from `saga_step` (or compensates if the step's deadline passed). Only one deployer instance runs (Postgres advisory lock `pg_try_advisory_lock(42)`; others idle).

## 4. Triggers and rules
- `scm.push.v1`: `projects.FindAppsByRepo`; for each app: if branch == default → production; else if `previews_enabled` → preview; else ignore. Dedupe by event id. Before creating: cancel non-terminal deployments for same (app, branch).
- Manual `CreateDeployment(app_id, branch?, commit_sha?)`: resolve sha via `scm.GetCommit` if missing.
- `Rollback(deployment_id)`: only `kind=production` and status `live|superseded` with `image_digest` present; creates a new deployment with `trigger=rollback`, `rollback_of`, skips build (`saga_step=built`, image copied).
- `Cancel(id)`: if `queued|building` → `builder.CancelBuild`; if `starting|health_checking` → stop container; status `cancelled`. Not allowed after `routing`.
- `scm.branch_deleted.v1`: for preview deployments of that branch: `router.RemoveRoute` for preview host, stop live container, mark `superseded`.
- `app.deleted.v1`: cancel active, stop all containers for the app, routes removed by router itself (it consumes `app.deleted`).
- `container.exited.v1` for a `live` deployment: increment counter; if ≥ 3 in 10 min → outbox `deployment.failed.v1` with stage `runtime` (status stays `live`; alert only). 
- `vitals.regressed.v1`: set `vitals_regressed=true`.

## 5. gRPC API (`launchpad.deployer.v1.DeployerService`)
`CreateDeployment`, `GetDeployment`, `ListDeployments(app_id, branch?, status?, page)`, `Rollback`, `Cancel`, `GetCurrentProduction(app_id)`.

## 6. Events
Publishes (topic `lp.deployments`, key `app_id`): `deployment.status_changed.v1`, `deployment.live.v1`, `deployment.failed.v1`, `build.requested.v1`.
Consumes: `scm.push.v1`, `scm.branch_deleted.v1`, `build.started.v1`, `build.completed.v1`, `build.failed.v1`, `app.deleted.v1`, `container.exited.v1`, `vitals.regressed.v1`.

## 7. Config
`LP_PG_DSN_FILE`, `LP_PROJECTS_ADDR`, `LP_SCM_ADDR`, `LP_BUILDER_ADDR`, `LP_RUNTIME_ADDR`, `LP_ROUTER_ADDR`, `LP_HEALTH_TIMEOUT=60s`, `LP_DRAIN_DELAY=10s` + common.

## 8. Tests
Exhaustive FSM table; saga happy path with fakes; each failure stage compensates correctly; idempotent handling of duplicate events; resume after crash at every `saga_step` (kill between steps in integration test); cancel in each state; rollback rules; preview vs production selection; branch-delete cleanup; advisory lock single-active.

## 9. Acceptance
`10-testing.md` §4 scenarios 1–7 pass; no orphan containers or routes after any failure scenario (janitor check).
