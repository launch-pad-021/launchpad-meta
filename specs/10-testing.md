# 10 — Testing

## 1. Portfolio
| Layer | What | Where | Gate |
|---|---|---|---|
| Unit | Pure logic: FSM, slugging, crypto round-trips, URL normalization, risk rules, rendering (golden files) | each repo | PR |
| Integration | Service + its real stores via Testcontainers (Postgres 18, Redis, Redpanda, ClickHouse); gRPC deps faked with in-process fakes generated from contracts | each repo | PR |
| Contract | `buf breaking`; event payloads validated against `contracts/events` schemas in producer tests; consumer tests parse fixture events | contracts + each repo | PR |
| E2E | Full stack via `launchpad-infra/compose.dev.yml` on an arm64 runner; deploy fixture apps end to end | `launchpad-e2e` | nightly + infra PRs + release |
| UI | Playwright flows + axe accessibility + screenshots at 375/768/1280 | dashboard | PR |
| Load | `hey`/`vegeta` swap test; `k6` ingest throughput | `launchpad-e2e` | weekly + perf issues |
| Chaos-lite | Kill a service mid-deploy; drop Redpanda 30 s; fill outbox | `launchpad-e2e` | weekly |
| Post-deploy smoke | Per-service smoke checks run by `infra-sync` | `launchpad-infra/sync/smoke/` | every deploy |

## 2. Per-language tooling
| Lang | Unit/integration | Property/fuzz | Coverage (informational) |
|---|---|---|---|
| Go | `go test -race ./...`, testify, testcontainers-go | `testing/quick` / native fuzzing for parsers | `go test -cover` |
| Rust | `cargo test`, testcontainers | `proptest`, `cargo fuzz` for payload parsing | `cargo llvm-cov` |
| Python | `pytest`, testcontainers | `hypothesis` (SQL guard, query builders) | `pytest-cov` |
| TS | `vitest`, testcontainers | `fast-check` (webhook parsing) | `vitest --coverage` |
Coverage is reported, not gated; reviewers check that changed behavior has tests.

## 3. Fixture apps (`launchpad-fixtures` repo, one directory per app, each also a branch-able example)
| Fixture | Purpose |
|---|---|
| `next-basic` | Next.js 16 app, Railpack auto-detect, gzip+brotli responses (injection test) |
| `node-express` | Plain Node with `PORT` |
| `static-site` | HTML only |
| `go-api` | Go HTTP with `/healthz` |
| `python-fastapi` | Python with uv |
| `dockerfile-custom` | Custom Dockerfile path |
| `slow-start` | Healthy after 30 s (health timeout behavior) |
| `crash-on-start` | Exits 1 (compensation path) |
| `never-healthy` | Returns 500 on health path |
| `slow-lcp` | Adds 2 s render delay (vitals regression) |
| `env-echo` | Prints selected env vars to an endpoint (env scopes; never secrets in logs) |

## 4. Required E2E scenarios (`launchpad-e2e`)
1. Create app → push `next-basic` → live within budget → HTTP 200 → tracker injected → pageview in ClickHouse.
2. Second push under load → 0 failed requests.
3. `never-healthy` push → old version keeps serving; deployment `failed` at `health_checking`; Telegram (mock) alert.
4. Preview branch → preview URL → delete branch → route + container removed.
5. Rollback → < 10 s → old commit served.
6. Cancel during build → build stops; status `cancelled`.
7. Kill `deployer` during `health_checking` → restart → saga completes or compensates.
8. Stop `logs` → deploy still succeeds → logs appear after restart.
9. `slow-lcp` deploy with synthetic vitals → `vitals.regressed` → badge + alert.
10. Ask "top pages last 24h" → correct rows; Ask on app A cannot see app B rows.

## 5. Test data rules
- No real secrets in tests; generated keys per run.
- Deterministic time via injected clocks; UUIDv7 generators injectable.
- Each integration test uses unique DB/topic names; containers reused per package for speed.
