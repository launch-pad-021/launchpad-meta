# 09 — Observability

## 1. Pipeline
Services → OTLP gRPC → OTel Collector → Jaeger (traces) · Prometheus scrapes `/metrics` of every service + cAdvisor + Traefik + Redpanda + ClickHouse + Postgres exporter. Logs: stdout JSON → Docker `json-file` driver (rotation 10 MB × 3); platform logs are viewed with `docker logs`/Jaeger correlation (app runtime logs go through `logs`).

## 2. SLOs (single-owner platform, measured over 30 days)
| SLO | Target | SLI |
|---|---|---|
| Gateway availability | 99.5% | non-5xx / all requests (excl. 429) |
| Deploy success (excluding user build errors) | 98% | deployments reaching `live` / deployments not failed at `build` with exit code from user code |
| Push-to-live latency (warm cache, fixture app) | p90 ≤ 120 s | `live_at - created_at` |
| Rollback latency | p99 ≤ 10 s | |
| Ingest acceptance | 99.9% | 2xx / valid requests |
| Insights freshness | p95 ≤ 10 s | event `received_at` → visible in ClickHouse |

## 3. Alerts (Prometheus rules in `launchpad-infra/prometheus/alerts.yml` → Alertmanager-lite: Prometheus webhook to `notifier`)
| Alert | Condition | Severity |
|---|---|---|
| ServiceDown | `up == 0` for 2 m | critical |
| ReadyzFailing | readyz probe failing 3 m | critical |
| GatewayErrorRate | 5xx ratio > 5% for 5 m | critical |
| ConsumerLagHigh | lag > 1000 for 10 m (any domain topic) | warning |
| IngestLagHigh | `events.raw` lag > 50k for 10 m | warning |
| OutboxBacklog | `lp_*_outbox_pending` > 100 for 5 m | warning |
| DLQNotEmpty | DLQ produce rate > 0 in 15 m | warning |
| SagaStuck | deployment non-terminal > 20 m | warning |
| DiskHigh | disk > 80% | warning; > 90% critical |
| MemoryHigh | host available < 800 MB for 5 m | critical |
| CertExpiry | cert expires < 14 d | warning |
| BackupMissed | no successful backup in 26 h | warning |
| ClickHouseInsertErrors | insert errors > 0 for 5 m | warning |

Alerts reach the owner via `notifier` (Telegram) and trigger the `incident-responder` agent through `repository_dispatch` for critical ones.

## 4. Platform page (dashboard `/platform`)
Per service: version, `/readyz` checks, p95 latency, error rate; per topic: consumer lag; outbox backlog; DLQ depth; non-terminal deployments with age; disk/memory; cert expiry; last backup; links to Jaeger for recent failed deploys (by `deployment_id` tag).

## 5. Tracing rules
- Root spans: HTTP requests at gateway/scm/ingest, consumed events.
- Deploy trace: `scm` webhook span is the root; `deployment_id` attribute on all spans; event `traceparent` continues the trace across async hops so one Jaeger trace shows webhook → deployer → builder → runtime-agent → router.
- Sampling: 100% for control plane; 1% for ingest/processor hot path (tail-based sampling keeps errors).
