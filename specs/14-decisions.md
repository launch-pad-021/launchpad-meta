# 14 — Architecture Decision Records

Format: Context · Decision · Consequences · Revisit when. New ADRs go in `launchpad-meta/docs/adr/NNN-<slug>.md`; this file is the initial log.

| # | Decision | Context / reason | Consequences | Revisit when |
|---|---|---|---|---|
| 001 | **Multiple services, one repo each** | Owner's learning goal: microservices, independent releases | More plumbing (contracts, kits, infra); mitigated by agents | Never for v1 |
| 002 | **Mixed languages:** Go (orchestration), Rust (ingest/processor), Python (analytics), TS (scm, notifier, dashboard) | Fit per job + learning | Four toolchains, four CI templates, kits for Go/Rust/TS | A language causes repeated escalations |
| 003 | **gRPC for sync, Redpanda events for async** | Typed contracts; Kafka concepts; replay | Broker is critical infra; outbox needed | — |
| 004 | **Redpanda** (Kafka API) over NATS JetStream | Kafka ecosystem learning; one broker for domain + analytics | ~1.3 GB RAM | Memory pressure on 12 GB server |
| 005 | **Transactional outbox + idempotent consumers** | No lost/phantom events | Extra tables + relay | — |
| 006 | **Orchestrated saga in deployer** (not choreography) | One place to see/resume deploy state | deployer is central; must be resilient | — |
| 007 | **One Postgres instance, one DB + user per service** | Data ownership without memory cost of many instances | Shared instance is a single point of failure | Multi-node |
| 008 | **Railpack + BuildKit** for auto-detected builds (Dockerfile supported) | Nixpacks is in maintenance mode; Railpack is its successor and runs on BuildKit | buildkitd service; Railpack CLI in builder image | Railpack instability |
| 009 | **Local `registry:2`**, builder never touches the Docker socket | Least privilege; multi-node readiness | Registry GC needed | — |
| 010 | **Python 3.14** (not 3.15) for analytics | 3.15 released 9 Oct 2026; arm64 wheel availability for grpcio/confluent-kafka/polars is mature on 3.14 | Upgrade later | Q2 2027 |
| 011 | **Node 26 LTS**, **Go 1.27**, **Postgres 18**, **ClickHouse 26.8 LTS**, **Traefik 3.7** | Current supported lines on 21 Nov 2026 | Renovate keeps patches current | Quarterly verification |
| 012 | **Per-app read-only ClickHouse users for "Ask your data"** | Custom-setting-based row policies could be overridden by generated SQL (`readonly=2` allows SET) or would block per-request settings (`readonly=1`); fixed per-user row policies don't depend on the SQL | analytics needs limited ACCESS MANAGEMENT; user lifecycle tied to app events | — |
| 013 | **Traefik file provider + rewrite-body fork `kelnei/rewrite-body` v1.3.0** for tracker injection | Original plugin unmaintained since 2022; fork verified on Traefik 3.7.9; compression handled by forcing identity encoding upstream and re-compressing | Third-party plugin risk; owner can disable injection per app | Plugin breaks on a Traefik upgrade |
| 014 | **Pull-based GitOps (`infra-sync`)**; Launchpad never deploys itself | No SSH keys in CI; a broken Launchpad can't block its own repair | 60 s deploy latency | — |
| 015 | **Single owner; GitHub OAuth allowlist** | Personal platform | No RBAC | Sharing with others |
| 016 | **Oracle Always Free A1 (2 OCPU/12 GB)**, Hetzner CAX31 fallback | ₹0 hosting; allowance halved June 2026 | Tight memory budget (07 §7) | Sustained memory pressure |
| 017 | **Agents run in GitHub Actions via claude-code-action@v1**, agent kit distributed as a Claude Code plugin | Ephemeral sandboxes, no prod access, one versioned kit for all repos | Actions minutes; plugin release process | — |
| 018 | **UUIDv7 IDs** | Time-ordered, index-friendly; native in Postgres 18 | — | — |
| 020 | **Adopt maintained skills/plugins (Anthropic official marketplace incl. superpowers, Trail of Bits, anthropics/skills); custom skills only for Launchpad glue** | Widely used skills are better tested than new ones; less to maintain | Third-party review + SHA pinning; interactive superpowers skills excluded from headless runs | A plugin degrades or changes behavior on update |
| 019 | **Cookieless analytics with daily-rotating salt** | Privacy; no consent banner needed for the tracker itself (verify for your jurisdiction) | Visitors can't be tracked across days by design | — |
