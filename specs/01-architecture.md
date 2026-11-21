# 01 — Architecture

Launchpad is **13 independent services**, each in its own repository, written in the language that suits it, plus a Next.js dashboard and a Go CLI. Services own their data, expose gRPC for synchronous calls, and use events on Redpanda for everything asynchronous. **No service reads another service's database.**

## 1. Topology

```
                                  ┌──────────────────────── Edge (Traefik 3.7) ────────────────────────┐
 Browser / CLI ── HTTPS ─▶ Traefik ─▶ gateway (REST+SSE, authn, rate limit) ──gRPC──▶ services
 GitHub ─── webhook ─────▶ Traefik ─▶ scm   (path /webhooks/github on the API host)
 Visitors ── HTTPS ──────▶ Traefik ─▶ app containers      (/_lp/* on every app host ─▶ ingest)
                                  └─────────────────────────────────────────────────────────────────────┘
 ┌──────────── Control plane ────────────┐ ┌────────── Data plane ──────────┐ ┌──────── Insights ────────┐
 │ identity  users, sessions, tokens,    │ │ builder  clone + Railpack/      │ │ ingest     collect      │
 │           internal JWTs (Go)          │ │          Dockerfile via BuildKit│ │            (Rust)       │
 │ projects  apps, settings, secrets (Go)│ │          → local registry (Go)  │ │ processor  enrich → CH  │
 │ scm       GitHub App, webhooks (TS)   │ │ runtime-agent containers,       │ │            (Rust)       │
 │ deployer  deploy FSM + saga (Go)      │ │          health, runtime logs   │ │ analytics  queries, ask,│
 │ notifier  Telegram/email alerts (TS)  │ │          (Go, Docker socket)    │ │            vitals (Py)  │
 │ gateway   public API (Go)             │ │ router   routes → Traefik YAML  │ └─────────────────────────┘
 └───────────────────────────────────────┘ │          (Go)                   │
                                           │ logs     build/runtime logs →   │
                                           │          ClickHouse (Go)        │
                                           └─────────────────────────────────┘
 Stores: Postgres 18 (one DB per service) · ClickHouse 26.8 (logs, analytics) · Redis (cache, sessions-of-visitors, delayed jobs)
 Bus:    Redpanda 26.1 — domain topics lp.* + events.raw + events.dlq
 Build:  buildkitd (rootless) + registry:2 (local image registry)
 Telemetry: OTel SDKs → OTel Collector → Jaeger (traces), Prometheus (metrics) + cAdvisor
```

## 2. Service catalog

| Service | Lang | Responsibility | gRPC API | Publishes | Consumes | Owns |
|---|---|---|---|---|---|---|
| gateway | Go | Public REST+SSE; authn; rate limit; REST→gRPC | — (HTTP) | — | `deployment.status_changed` | — |
| identity | Go | GitHub OAuth, sessions, CLI tokens, JWKS, service tokens | IdentityService | `token.revoked` | — | `identity` DB |
| projects | Go | Apps, settings, encrypted env vars | ProjectsService | `app.*`, `env.changed` | — | `projects` DB |
| scm | TS | GitHub App, webhook verify+dedupe, clone tokens | ScmService | `scm.push`, `scm.branch_deleted` | — | `scm` DB |
| deployer | Go | Deployment FSM + saga; rollback; cancel | DeployerService | `deployment.*`, `build.requested` | `scm.*`, `build.*`, `app.deleted`, `vitals.regressed`, `container.exited` | `deployer` DB |
| builder | Go | Clone, Railpack/Dockerfile build via BuildKit, push to registry | BuilderService | `build.*`, `build.log` | `build.requested` | — |
| runtime-agent | Go | Container lifecycle, health, runtime logs | RuntimeAgentService | `runtime.log`, `container.exited` | — | — (Docker) |
| router | Go | Routes, Traefik config rendering, host resolution | RouterService | `route.changed` | `app.deleted`, `app.updated` | `router` DB |
| logs | Go | Store/serve build+runtime logs | LogsService | — | `build.log`, `runtime.log` | CH `logs` |
| notifier | TS | Alert rules → Telegram/email | NotifierService | — | `deployment.failed`, `vitals.regressed`, `container.exited` | `notifier` DB |
| ingest | Rust | `/_lp/script.js`, `/_lp/e`; validate; produce | — (HTTP) | `insights.event` | `route.changed` | — |
| processor | Rust | Bot filter, geo, UA, visitor hash, sessions → CH | — | `dlq` | `insights.event` | CH `analytics` (writer) |
| analytics | Python | Queries, funnels, Ask, deploy markers, vitals checks | AnalyticsService | `vitals.regressed` | `deployment.live`, `app.created`, `app.deleted` | CH `analytics` (reader, markers, per-app Ask users) |
| dashboard | TS/Next.js | UI; talks only to gateway | — | — | — | — |
| cli (`launch`) | Go | CLI; talks only to gateway | — | — | — | — |

## 3. Communication rules
1. **Sync = gRPC**, contracts in `launchpad-contracts` (buf). Every call has a deadline (default 3 s; streams and builds excepted) and propagates W3C trace context.
2. **Async = events** on Redpanda in the envelope from `03-conventions.md` §6. Something that *happened* is an event; something that needs an answer *now* is gRPC.
3. **Outbox** for every service that changes its DB and publishes (identity, projects, scm, deployer, router). **Idempotent consumers** everywhere (at-least-once delivery).
4. **Partition key = `app_id`** for domain topics, so per-app ordering holds.
5. **Internal auth:** gateway authenticates users via `identity.Authenticate`, then calls services with a short-lived user JWT; services call each other with service JWTs from `identity.IssueServiceToken`. `projects.GetRuntimeEnv` accepts only the `deployer` service identity.
6. **Discovery:** Docker DNS names (`projects:9000`). gRPC port 9000, HTTP (health/metrics) port 8080 in every service.

## 4. Deploy saga (orchestrated by `deployer`)

```
scm.push ──▶ deployer: dedupe; create deployment(queued); cancel older in-flight deploys for (app, branch)
           ├▶ projects.GetApp                                → build settings
           └▶ outbox: build.requested                        → builder
builder:   scm.GetCloneCredentials → clone → railpack prepare / Dockerfile → BuildKit build
           → push registry:5000/launchpad/<app>:<sha> → build.log* → build.completed(image digest, effective config)
deployer on build.completed:
           ├▶ projects.GetRuntimeEnv(app, scope)             → env (never stored)
           ├▶ runtime-agent.StartContainer(image, env, limits) → container + upstream
           ├▶ runtime-agent.CheckHealth  (poll ≤ 60 s, 2 consecutive OK)
           ├▶ router.SetRoute(host, upstream, flags) per hostname → Traefik reload confirmed
           ├▶ status=live; outbox: deployment.live
           └▶ after 10 s drain: runtime-agent.StopContainer(previous) ; previous → superseded
Failure at any step → compensate: stop new container, keep old routes, status=failed, deployment.failed
```
`deployments.saga_step` is persisted after each step; on restart `deployer` resumes or compensates every non-terminal deployment.

Hostnames per deploy: production → `<app>.apps.<domain>`; preview → `<branch-slug>--<app>.apps.<domain>`; always → `d-<short-id>--<app>.apps.<domain>`.

## 5. Insights integration (built in, zero setup)
- `router` renders, for every route with `insights=true`, a high-priority router `Host(h) && PathPrefix(/_lp/)` → `ingest`, and (if `inject=true`) the HTML injection middleware chain (`07-infrastructure.md` §5).
- `ingest` resolves `app` + `deployment_id` + `route_kind` from the `Host` header via `router.ResolveHost` (cached; invalidated by `route.changed`).
- `analytics` consumes `deployment.live` → writes deploy markers, schedules vitals checks at +30 min and +2 h → publishes `vitals.regressed` → `deployer` flags the deployment, `notifier` alerts.

## 6. Failure isolation
- Insights down → deploys unaffected (apps still serve; tracker requests fail silently).
- `logs` down → builds continue; log lines wait in Redpanda (retention 7 d) and are stored on recovery.
- `router` down → existing Traefik config keeps serving; new swaps wait (saga retries with backoff, then compensates).
- Redpanda down → outbox rows accumulate; relays retry; gateway still serves reads.
- `deployer` restart → saga resumes from `saga_step`.
- Launchpad platform services are deployed by `infra-sync` (pull-based GitOps), **never by Launchpad itself**.

## 7. Multi-node readiness (not built in v1)
`runtime-agent` and `builder` are per-node; `deployments.node` records placement; registry is network-reachable. A second node = run those two + join networks over WireGuard (stretch).
