# 07 — Infrastructure

## 1. Server
- Oracle Cloud Always Free **Ampere A1: 2 OCPU / 12 GB RAM** (the allowance was halved from 4/24 on 15 Jun 2026), Ubuntu 24.04 arm64, ~100 GB boot volume. Fallback: Hetzner CAX31 (16 GB).
- Oracle reclaims idle Always Free instances; the platform's background load keeps it above idle thresholds — monitor.
- Hardening (bootstrap script, run once by the developer): non-root sudo user, SSH keys only, `PasswordAuthentication no`, ufw allow 22/80/443, unattended-upgrades, fail2ban, Docker 29 + Compose v5, `vm.max_map_count` and `nofile` limits for ClickHouse/Redpanda, swap 4 GB (safety net, `vm.swappiness=10`), timezone UTC.

## 2. Domain and DNS
| Record | Target |
|---|---|
| `launchpad.<domain>` | server IP — dashboard |
| `api.launchpad.<domain>` | server IP — gateway; `/v1/webhooks/github` → scm |
| `*.apps.<domain>` | server IP — app routes |
DNS on Cloudflare, records **DNS-only (grey cloud)**: Cloudflare's free edge certificates cover only one subdomain level, so `*.apps.<domain>` must be terminated by Traefik. Wildcard cert via ACME DNS-01 (Cloudflare token: Zone:Read + DNS:Edit on the zone).

## 3. Compose layout (`launchpad-infra`)
```
launchpad-infra/
├── compose.yml                 # all services, images pinned by tag from versions.env
├── compose.dev.yml             # local dev overrides (localtest.me, self-signed TLS)
├── versions.env                # LP_<SERVICE>_IMAGE=ghcr.io/<org>/launchpad-<svc>:<semver>
├── traefik/static.yml          # entrypoints, providers, ACME, plugins
├── traefik/dynamic/_shared.yml # ingest service, middlewares (router writes <app>.yml next to it)
├── postgres/init.sql           # databases, users, grants (per service)
├── clickhouse/                 # users.d/, config.d/, schemas
├── redpanda/topics.sh          # topic creation (idempotent)
├── otel/collector.yaml  prometheus/prometheus.yml  prometheus/alerts.yml
├── bootstrap/server.sh         # one-time host setup (developer runs)
├── sync/infra-sync.sh  sync/infra-sync.service  sync/infra-sync.timer
└── secrets/README.md           # list of required secret files (never the values)
```

## 4. Networks
| Network | Members | Purpose |
|---|---|---|
| `lp_edge` | traefik, gateway, scm, ingest, dashboard | Traefik → public-facing services |
| `lp_internal` | all Launchpad services, postgres, redis, redpanda, clickhouse, registry, buildkitd, otel, jaeger, prometheus, cadvisor | Internal traffic; `internal: true` (no egress) except where noted |
| `lp_apps` | traefik, app containers, runtime-agent | Traefik → apps; runtime-agent health checks. runtime-agent binds gRPC only on its `lp_internal` IP |
| `lp_egress` | traefik, builder, buildkitd, scm, identity, notifier, analytics, geoipupdate, backup jobs | Outbound internet (ACME/Cloudflare, GitHub, registries, Telegram, LLM API, MaxMind, R2) |

App containers can reach the internet (bridge default) but **cannot reach any Launchpad service or store**.

## 5. Traefik
Static config essentials:
```yaml
entryPoints:
  web: { address: ":80", http: { redirections: { entryPoint: { to: websecure, scheme: https } } } }
  websecure: { address: ":443" }
  traefik: { address: ":8080" }              # internal API/dashboard entrypoint: NOT published; reachable only on Docker networks (router uses it)
providers:
  file: { directory: /etc/traefik/dynamic, watch: true }
api: { dashboard: true, insecure: true }      # served on the internal :8080 entrypoint only; humans reach it via SSH tunnel
certificatesResolvers:
  cf:
    acme:
      email: <owner email>
      storage: /data/acme.json
      dnsChallenge: { provider: cloudflare, resolvers: ["1.1.1.1:53", "1.0.0.1:53"] }
experimental:
  plugins:
    rewrite-body: { moduleName: "github.com/kelnei/rewrite-body", version: "v1.3.0" }
```
Env: `CF_DNS_API_TOKEN_FILE=/run/secrets/cf_dns_token`.

Shared dynamic config (`_shared.yml`), rendered once:
```yaml
http:
  services:
    ingest: { loadBalancer: { servers: [{ url: "http://ingest:8080" }] } }
  middlewares:
    lp-compress: { compress: {} }
    lp-identity-encoding:                 # ask upstream for uncompressed HTML so the injector can rewrite it
      headers: { customRequestHeaders: { Accept-Encoding: "identity" } }
    lp-inject:
      plugin:
        rewrite-body:
          rewrites:
            - regex: "</head>"
              replacement: "<script defer src=\"/_lp/script.js\"></script></head>"
          monitoring: { types: ["text/html"] }
    lp-security-headers:
      headers: { stsSeconds: 31536000, stsIncludeSubdomains: true, contentTypeNosniff: true, referrerPolicy: "strict-origin-when-cross-origin" }
```
Per-app router chain when `inject=true`: `[lp-security-headers, lp-compress, lp-identity-encoding, lp-inject]` — request flows left→right (compress reads the client's `Accept-Encoding` before it is replaced), response flows right→left (inject, then compress). When `inject=false`: `[lp-security-headers]`. M9 MUST verify with a fixture app that serves gzip/brotli by default; if injection is unreliable for an app, the owner sets `insights_inject=false` and adds the script tag manually (collection still works).

Router-rendered per-app file — see `services/router.md` §4.

## 6. Build infrastructure
- `buildkitd`: `moby/buildkit:rootless` with `--oci-worker-no-process-sandbox`, listens on `tcp://buildkitd:1234` (mTLS certs from bootstrap) on `lp_internal`; cache volume `buildkit-cache`; GC keep 20 GB.
- `registry`: `registry:2` on `lp_internal` at `registry:5000` (HTTP, internal only — Docker daemon configured with `insecure-registries: ["registry:5000"]` via the host's `daemon.json`, reachable as `127.0.0.1:5000` published on loopback only). Garbage collection weekly (`registry garbage-collect`) after builder untags old images.
- The builder never touches the Docker socket. Only `runtime-agent` mounts `/var/run/docker.sock`.

## 7. Memory budget (12 GB)
| Component | Limit |
|---|---|
| 13 services (8 Go ≈ 40 MB, 2 Rust ≈ 30 MB, Python ≈ 150 MB, 2 Node ≈ 120 MB) | ~1.0 GB |
| Traefik 150 MB, Redis 128 MB, registry 64 MB | ~0.35 GB |
| Postgres (`shared_buffers=256MB`) | 0.5 GB |
| Redpanda (`--smp 1 --memory 1G --reserve-memory 0M --overprovisioned`) | 1.3 GB |
| ClickHouse (`max_server_memory_usage=2.5GB`) | 2.5 GB |
| buildkitd (idle ~100 MB; during build up to 2 GB) | 0.1–2 GB |
| OTel Collector + Jaeger (Badger, 3 d) | 0.4 GB |
| Prometheus + cAdvisor | 0.5 GB |
| Dashboard (Next.js standalone) | 0.25 GB |
| **Platform total (idle)** | **~7 GB** |
| **Left for apps (idle) / during a build** | **~5 GB / ~3 GB** |
Every container has `mem_limit` set in compose; app containers get their configured `mem_limit_mb`.

## 8. GitOps deploy (`infra-sync`)
- systemd timer every 60 s on the server: `git fetch` `launchpad-infra` (read-only deploy key) → if `main` moved: validate (`docker compose config`), diff `versions.env`, for each changed service in dependency order: run its migration job (if any) → `docker compose pull <svc>` → `docker compose up -d <svc>` → wait `/readyz` (90 s) → run smoke check for that service.
- Reports a GitHub commit status `infra-sync/deploy` (pending/success/failure) on the infra commit using a fine-grained token with only `statuses:write` on `launchpad-infra`.
- On failure: does **not** auto-revert by itself (the `incident-responder` agent opens the revert PR, which `infra-sync` then applies) — except if `/readyz` never passes within 90 s, in which case it restarts the previous image immediately and marks failure (fast local safety net).
- Dependency order: stores → identity → projects → scm → router → runtime-agent → logs → builder → deployer → notifier → gateway → dashboard → ingest → processor → analytics.

## 9. Backups
| What | How | Where | Retention |
|---|---|---|---|
| Postgres (each DB) | nightly `pg_dump -Fc`, encrypted with `age` | Cloudflare R2 (free 10 GB) | 14 daily + 8 weekly |
| ClickHouse | weekly `BACKUP DATABASE analytics, logs TO S3(...)` (R2 S3 API) | R2 | 4 weekly |
| Secrets bundle | on change, `age`-encrypted tarball | R2 + developer's password manager | latest 5 |
| Traefik `acme.json` | nightly, encrypted | R2 | 7 |
Monthly automated **restore drill** into a scratch compose project; result posted to `launchpad-meta` as an issue comment (`13-runbooks.md` §4).

## 10. Local development
`compose.dev.yml` runs the full stack on a laptop or CI runner with `*.localtest.me` (resolves to 127.0.0.1) and Traefik's default certificate; `make dev SERVICE=<name> PATH=<checkout>` swaps one service for a local build with live reload. CI E2E (`launchpad-e2e`) runs this stack on `ubuntu-24.04-arm` runners (16 GB on public repos).
