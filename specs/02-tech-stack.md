# 02 — Tech Stack (pinned, verified 21 Nov 2026)

Agents MUST use these major/minor versions. Patch versions float to latest within the line (Renovate manages them). Changing a major/minor line is a medium-risk PR with an ADR.

## 1. Languages and runtimes
| Item | Version | Status on 21 Nov 2026 | Notes |
|---|---|---|---|
| Go | **1.27.x** | Released 19 Aug 2026 | Generic methods, `encoding/json/v2`. Go 1.25 is out of support. `go.mod`: `go 1.27` |
| Node.js | **26.x LTS** | Active LTS since 28 Oct 2026 (EOL Apr 2029) | Node 24 is Maintenance LTS; don't start new code on it |
| TypeScript | 5.x latest | — | `strict: true` |
| Python | **3.14.x** | Bugfix line (3.15.0 released 9 Oct 2026) | 3.14 chosen for mature arm64 wheels (grpcio, confluent-kafka, polars); revisit 3.15 in Q2 2027 (ADR-010) |
| Rust | stable (latest) | — | Edition 2024 |
| Next.js | **16.4.x** | Released 6 Oct 2026 | App Router, React 19.x; requires Node ≥ 20.9 |

## 2. Infrastructure components
| Component | Version / image | Notes |
|---|---|---|
| Traefik | **v3.7.x** (pin exact patch in `versions.env`) | File provider with `watch: true`. Community reports ACME/Cloudflare issues on some 3.7.6+ patches — M0 must prove issuance on the pinned patch |
| Rewrite-body plugin | `github.com/kelnei/rewrite-body` **v1.3.0** | Maintained fork; verified by its author against Traefik 3.7.9. The original `traefik/plugin-rewritebody` and `packruler/rewrite-body` have had no commits since Nov 2022 |
| PostgreSQL | **18.x** | Built-in `uuidv7()` |
| ClickHouse | **26.8 LTS** (`clickhouse/clickhouse-server:26.8`) | Supported until Aug 2027. arm64 image requires ARMv8.2-A + RCpc (Ampere Altra/Neoverse N1 class — confirm on first boot) |
| Redpanda | **v26.1.x** (`redpandadata/redpanda`) | arm64 images available; single node with `--smp 1 --memory 1G --overprovisioned` |
| Redis | 8.x | Cache, visitor sessions, salts, arq jobs |
| BuildKit | `moby/buildkit` latest stable, **rootless** variant | Required by Railpack |
| Railpack | latest release (CLI `railpack` + frontend `ghcr.io/railwayapp/railpack-frontend`) | Successor to Nixpacks (Nixpacks is in maintenance mode). Production pattern: `railpack prepare` → BuildKit frontend |
| Image registry | `registry:2` (CNCF Distribution) | Local, internal network only |
| OpenTelemetry Collector | `otel/opentelemetry-collector-contrib` latest | |
| Jaeger | v2.x all-in-one (Badger storage) | 3-day trace retention |
| Prometheus + cAdvisor | latest stable | 15-day metric retention |
| Docker Engine | 29.x, Compose v5 | On the server |
| OS | Ubuntu 24.04 LTS (arm64) | Oracle Always Free Ampere A1 |

## 3. Libraries per language
| Language | Libraries |
|---|---|
| Go | `chi` (HTTP), `google.golang.org/grpc`, `connectrpc` NOT used (plain gRPC), `pgx/v5`, `sqlc`, `goose`, `twmb/franz-go` (Kafka), `ClickHouse/clickhouse-go/v2`, `docker/docker/client` (runtime-agent), `moby/buildkit/client` (builder), `go-redis/v9`, `golang-jwt/jwt/v5`, `google/uuid` (NewV7), OpenTelemetry Go SDK, `prometheus/client_golang`, `log/slog`, `spf13/cobra` (CLI), `testify`, `testcontainers-go` |
| Rust | `tokio`, `axum`, `tonic`, `prost`, `rdkafka`, `clickhouse`, `maxminddb`, `uaparser`, `siphasher`, `redis`, `serde`, `opentelemetry` + `tracing`, `prometheus`, `proptest`, `testcontainers` |
| Python | `uv` (packaging), `grpcio` + `grpcio-tools`, `fastapi` (health/metrics only), `clickhouse-connect`, `confluent-kafka`, `polars`, `arq` (delayed jobs), `anthropic` SDK, `pydantic` v2, `structlog`, `opentelemetry-sdk`, `pytest`, `hypothesis`, `testcontainers` |
| TypeScript (services) | `@grpc/grpc-js`, `@bufbuild/protobuf` generated code, `@octokit/app`, `@octokit/webhooks`, `kafkajs`, `pg`, `pino`, OTel JS SDK, `vitest`, `testcontainers` |
| Dashboard | Next.js 16.4, React 19, Tailwind CSS 4, shadcn/ui, Recharts, TanStack Query, Playwright, axe-core |
| Tracker | TypeScript → esbuild, `web-vitals` **v6** (`onLCP`, `onINP`, `onCLS`, `onFCP`, `onTTFB`; FID was removed in v5) |
| Contracts | `buf` CLI (lint, breaking, generate) |

## 4. GitHub / CI
| Item | Choice |
|---|---|
| Agent runtime | `anthropics/claude-code-action@v1` (inputs: `prompt`, `claude_args`, `plugin_marketplaces`, `plugins`, `settings`, `allowed_bots`, `anthropic_api_key` or `claude_code_oauth_token`) |
| Runners | `ubuntu-24.04` (x64) and **`ubuntu-24.04-arm`** (native arm64; free for public repos with 4 vCPU; private repos 2 vCPU billed to plan minutes) |
| Images | Built natively per arch and merged into a multi-arch manifest; pushed to GHCR with provenance |
| Releases | release-please (Conventional Commits) |
| Dependencies | Renovate |
| Security scans | gitleaks, semgrep, trivy, govulncheck, cargo-deny, pip-audit, npm audit/osv-scanner, hadolint, actionlint |

## 5. Upgrade policy
- Patch: Renovate auto-PR, low risk, auto-merge on green.
- Minor: Renovate PR, low/medium risk.
- Major or LTS line change: issue + ADR + medium/high risk.
- Re-verify this file every quarter (`technical-researcher` agent, scheduled).
