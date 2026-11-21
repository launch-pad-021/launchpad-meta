# 11 — Delivery Plan (milestones, issues, dependencies)

This is the backlog the **planner** turns into GitHub issues (one milestone plan PR per milestone → G1 approval → issues created). Each row becomes one issue using the template in `bootstrap/templates/ISSUE_TEMPLATE/agent-task.yml`; the planner fills acceptance criteria from the referenced service spec section and this file's milestone acceptance.

Risk levels follow `12-agentic-system.md` §11 (the risk script has the final say on the PR). `cfg` = `agent-config` (developer merges).

## 0. Dependency graph and parallel tracks

```
A0 (agent kit) ─▶ M0 (infra) ─▶ M1 (contracts & kits) ─┬─▶ M2 (identity/projects/gateway/UI shell) ─▶ M3 (scm/deployer) ─┐
                                                        ├─▶ M5-01 runtime-agent ─┐                                          │
                                                        ├─▶ M5-02 router ────────┼──────────────────────────────────────────┤
                                                        ├─▶ M4-01 builder (vs. fixture events) ─────────────────────────────┤
                                                        ├─▶ M9-02 ingest (fake router) ─┐                                   ▼
                                                        └─▶ M10-01 processor ───────────┤                 M4 integration ─▶ M5-03 saga ─▶ M6 ─▶ M7 ─▶ M8
                                                                                        └──────────────▶ M9 integration (needs M5-02) ─▶ M10 ─▶ M11 ─▶ M12 ─▶ H1
```
Max parallel implementers: 3 (conductor). Preferred parallel tracks after M1: **Control** (M2→M3), **Edge** (runtime-agent, router), **Insights** (ingest, processor). UI issues follow the gateway endpoints they need.

## A0 — Agent kit and control repo (autonomy phase P0: agents open PRs, developer merges everything)
| ID | Repo | Title | Depends | Risk |
|---|---|---|---|---|
| A0-01 | launchpad-meta | Import this spec pack; CLAUDE.md; issue/PR templates; labels + Project fields setup script (`scripts/setup-project.sh` via `gh`) | — | cfg |
| A0-02 | launchpad-agent-kit | Plugin skeleton from `bootstrap/agent-kit/`; marketplace.json; core agents (planner, implementer, code-reviewer, correctness-verifier, ci-fixer); glue skills `spec-to-issues`, `implement-issue`, `launchpad-review-gate`. **Review and pin** the adopted plugins in 12-agentic-system §8.1 (record SHAs + review notes in `ADOPTED_PLUGINS.md`) | A0-01 | cfg |
| A0-03 | launchpad-agent-kit | Hooks (session-start, guard-bash, guard-paths, stop-checks) with tests | A0-02 | cfg |
| A0-04 | launchpad-agent-kit | `scripts/risk.py` classifier + unit tests for every rule in §11.1 of 12-agentic-system | A0-02 | cfg |
| A0-05 | launchpad-agent-kit | Reusable workflows: agent-implement, agent-review, ci-fix, release; CI templates go/rust/python/node/next | A0-03, A0-04 | cfg |
| A0-06 | launchpad-agent-kit | Remaining agents as thin wrappers over adopted plugins (security, architecture, database, design, docs, deps, release, incident, debugging, research, test, perf) + glue skills `release-and-deploy`, `incident-response` | A0-02 | cfg |
| A0-07 | launchpad-meta | conductor.yml, planner.yml, metrics.yml, weekly-audits.yml | A0-05 | cfg |
| A0-08 | launchpad-meta | Repo templates (go, rust, python, node, next) + `scripts/create-repos.sh` (developer runs) | A0-05 | cfg |
| A0-09 | launchpad-meta | Acceptance drills: protected-path PR rejected, kill switch, prompt-injection issue ignored, 5 golden tasks baseline | A0-07, A0-08 | cfg |
**Done when:** 12-agentic-system §21 items for P0 pass; all repos exist from templates with rulesets applied.

## M0 — Infrastructure foundation (`launchpad-infra`)
| ID | Title | Depends | Risk |
|---|---|---|---|
| M0-01 | `bootstrap/server.sh` idempotent host setup (07 §1); developer runs it | A0 | high |
| M0-02 | Stores in compose: Postgres 18 + `init.sql` per service, Redis, Redpanda + `topics.sh`, ClickHouse 26.8 + users/profiles/schemas, registry, buildkitd + mTLS cert script; mem limits, healthchecks | M0-01 | high |
| M0-03 | Traefik static/dynamic, ACME DNS-01 Cloudflare, rewrite-body plugin pinned, whoami test route | M0-01 | high |
| M0-04 | Observability: otel-collector, jaeger, prometheus + alerts skeleton, cadvisor, postgres-exporter | M0-02 | medium |
| M0-05 | `infra-sync` (script, systemd units, status reporting, readyz wait, local fallback, smoke hook) | M0-02 | high |
| M0-06 | Backups (pg_dump+age→R2, ClickHouse BACKUP→R2, secrets bundle, acme.json) + restore script | M0-02 | high |
| M0-07 | `compose.dev.yml`, Makefile, CI: compose validation + stores stack up on `ubuntu-24.04-arm` | M0-02 | medium |
**Done when:** `https://hello.apps.<domain>` has a valid wildcard cert; all stores healthy; topics exist; idle memory recorded in `launchpad-meta/perf/idle.md`; infra-sync deploys a version bump.

## M1 — Contracts, conventions, kits
| ID | Repo | Title | Depends | Risk |
|---|---|---|---|---|
| M1-01 | launchpad-contracts | Import `contracts/`; buf config; lint/breaking CI; codegen Go/TS/Python/Rust + event types; release v0.1.0 | A0 | medium |
| M1-02 | launchpad-conventions | CONVENTIONS.md from 03-conventions; examples per language | A0 | low |
| M1-03 | launchpad-go-kit | config (`*_FILE`), slog, OTel, gRPC server/client (deadlines, retries, JWT interceptors with JWKS cache), health/readyz/metrics server, bus (franz-go, envelope, DLQ), outbox relay + processed_events (pgx), test helpers | M1-01 | medium |
| M1-04 | launchpad-rust-kit | config, tracing+OTel, health/metrics server, rdkafka consumer/producer with envelope + DLQ | M1-01 | medium |
| M1-05 | launchpad-ts-kit | config, pino, OTel, grpc-js server helpers with JWT auth, kafkajs bus with envelope/outbox (pg) | M1-01 | medium |
| M1-06 | launchpad-e2e | Cross-language smoke: Go ping → TS pong (gRPC) → event → Rust consumer; one Jaeger trace | M1-03..05 | low |

## M2 — Identity, projects, gateway, dashboard shell
| ID | Repo | Title | Depends | Risk |
|---|---|---|---|---|
| M2-01 | identity | Full service per `services/identity.md` | M1-03 | high |
| M2-02 | projects | Full service per `services/projects.md` | M1-03, M2-01 (service tokens) | high |
| M2-03 | gateway | Server, auth/CSRF/rate-limit/idempotency middleware, problem+json, `/me` `/apps` `/env` `/tokens`, OpenAPI | M2-01, M2-02 | high |
| M2-04 | dashboard | Shell, login, apps list/create/settings/env, tokens; design tokens; Playwright+axe | M2-03 | low |
| M2-05 | infra | Add identity/projects/gateway/dashboard; Traefik routes; smoke checks | M2-01..04 | medium |
**Done when:** login works; create app → `app.created` in `lp.projects`; env var set, masked, encrypted at rest.

## M3 — SCM and deployer core
| ID | Repo | Title | Depends | Risk |
|---|---|---|---|---|
| M3-01 | scm | GitHub App auth, webhook HMAC+dedupe, `scm.push`/`scm.branch_deleted`, `GetCloneCredentials`, `GetCommit`, `ListBranches` | M1-05 | high |
| M3-02 | deployer | Schema, FSM (exhaustive tests), CreateDeployment, `scm.push` consumer, cancel-older, `build.requested` via outbox, status events, Get/List | M1-03, M2-02 | medium |
| M3-03 | gateway | Deployment endpoints + `/deployments/{id}/events` SSE | M3-02 | medium |
| M3-04 | dashboard | Deployments list, deployment page with FSM timeline | M3-03 | low |
| M3-05 | infra | Add scm, deployer; webhook route | M3-01, M3-02 | medium |
**Done when:** a push creates a `queued` deployment; killing deployer between DB write and publish still delivers `build.requested`.

## M4 — Builder and logs
| ID | Repo | Title | Depends | Risk |
|---|---|---|---|---|
| M4-01 | builder | Per `services/builder.md` (Railpack + BuildKit + registry) | M1-03 | high |
| M4-02 | logs | Per `services/logs.md` | M1-03 | medium |
| M4-03 | gateway | Logs endpoints + SSE stream | M4-02 | low |
| M4-04 | dashboard | Live build log viewer (ANSI, virtualized, resume) | M4-03 | low |
| M4-05 | deployer | Consume `build.*` → statuses | M4-01, M3-02 | medium |
| M4-06 | infra | Add builder, logs; buildkit certs; registry GC job | M4-01, M4-02 | medium |
**Done when:** push of `next-basic` → image in registry; build streams live in the dashboard.

## M5 — Runtime, routing, full saga (first live deploy)
| ID | Repo | Title | Depends | Risk |
|---|---|---|---|---|
| M5-01 | runtime-agent | Per `services/runtime-agent.md` | M1-03 | high |
| M5-02 | router | Per `services/router.md` (routes, rendering, ResolveHost) | M1-03 | high |
| M5-03 | deployer | Saga after build: env, start, health, route, drain, compensate, resume | M4-05, M5-01, M5-02 | high |
| M5-04 | e2e | Scenarios 1–3 (`10-testing.md` §4) | M5-03 | low |
| M5-05 | infra | Add runtime-agent, router; smoke | M5-01, M5-02 | high |
**Done when:** `git push` → live with valid TLS; 0 failed requests during swap; `never-healthy` leaves old version serving.

## M6 — Previews, immutable URLs, rollback, cancellation, cleanup
| ID | Repo | Title | Depends | Risk |
|---|---|---|---|---|
| M6-01 | deployer | Previews, immutable hostnames, rollback (reuse image), cancel, `scm.branch_deleted` + `app.deleted` cleanup | M5-03 | medium |
| M6-02 | router | `RemoveRoutesForApp`, preview hostnames, short_id collision check | M5-02 | medium |
| M6-03 | dashboard | URLs, rollback/cancel actions, branch filter | M6-01 | low |
| M6-04 | e2e | Scenarios 4–6 | M6-01..03 | low |

## M7 — Runtime logs, metrics, notifications
| ID | Repo | Title | Depends | Risk |
|---|---|---|---|---|
| M7-01 | notifier | Per `services/notifier.md` | M1-05 | medium |
| M7-02 | gateway | Metrics (PromQL templates), runtime logs SSE, notification endpoints | M7-01 | medium |
| M7-03 | dashboard | Logs tab (live + search), metrics charts, notification settings | M7-02 | low |
| M7-04 | infra | Complete `alerts.yml`; Prometheus → notifier webhook | M7-01 | medium |
| M7-05 | deployer | `container.exited` handling (crash loop → mark + event) | M5-03 | medium |
**Done when:** `crash-on-start` triggers a Telegram alert; metrics chart shows CPU under load.

## M8 — CLI, Platform page, resilience tests
| ID | Repo | Title | Depends | Risk |
|---|---|---|---|---|
| M8-01 | cli | Per `services/cli.md` + goreleaser | M6-01 | low |
| M8-02 | gateway + dashboard | `/platform` aggregation and page | M7-04 | low |
| M8-03 | e2e | Scenarios 7–8 (chaos) + nightly schedule | M5-03 | low |
| M8-04 | fixtures | All fixtures in `10-testing.md` §3 | M0 | low |

## M9 — Ingest, tracker, auto-wiring
| ID | Repo | Title | Depends | Risk |
|---|---|---|---|---|
| M9-01 | ingest | Tracker (`tracker/`, TS + esbuild, web-vitals v6, SPA routes, beacon; ≤ 4 KB gzipped) | M1-04 | medium |
| M9-02 | ingest | Rust service per `services/ingest.md` | M1-04 | high |
| M9-03 | router | Render `/_lp/*` routers and injection chain per flags | M5-02 | high |
| M9-04 | infra + e2e | Add ingest; verify injection on gzip/br fixture; events carry correct app/deploy | M9-01..03 | medium |

## M10 — Processor
| ID | Repo | Title | Depends | Risk |
|---|---|---|---|---|
| M10-01 | processor | Per `services/processor.md` | M1-04 | medium |
| M10-02 | infra | processor + weekly `geoipupdate` | M10-01 | medium |
**Done when:** kill mid-batch loses 0 events; freshness p95 ≤ 10 s.

## M11 — Analytics, Insights UI, vitals regressions
| ID | Repo | Title | Depends | Risk |
|---|---|---|---|---|
| M11-01 | analytics | Per `services/analytics.md` §1–5 (queries, markers, vitals checks, Ask-user lifecycle) | M1-01, M10-01 | high |
| M11-02 | deployer + notifier | `vitals.regressed` handling and alert | M11-01 | low |
| M11-03 | gateway + dashboard | Insights endpoints, Insights tab, deploy vitals, sparkline | M11-01 | low |
| M11-04 | e2e | Scenario 9 | M11-01..03 | low |

## M12 — Ask your data
| ID | Repo | Title | Depends | Risk |
|---|---|---|---|---|
| M12-01 | analytics | Ask pipeline per `services/analytics.md` §6 | M11-01 | high |
| M12-02 | dashboard | Ask UI with chart + "show SQL" | M12-01 | low |
| M12-03 | e2e | Scenario 10 + data-borne prompt-injection cases | M12-01 | low |

## H1 — Hardening and go-live
| ID | Title | Risk |
|---|---|---|
| H1-01 | Full security audit across repos; fix or accept findings | high |
| H1-02 | Automated monthly restore drill; runbook verification | medium |
| H1-03 | Rollback drill ×2 and incident game day ×2 (autonomy P3/P4 graduation) | medium |
| H1-04 | Performance baselines (push-to-live, ingest throughput, idle memory) in `launchpad-meta/perf/` | low |
| H1-05 | Docs pass: every README complete; owner guide | low |
