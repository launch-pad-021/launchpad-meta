# 15 — Verification Log (21 November 2026)

Claims in earlier drafts were checked against primary or authoritative sources. "Changed" lists what this pack does differently because of the check.

| # | Claim checked | Finding | Changed | Source |
|---|---|---|---|---|
| 1 | Nixpacks as the auto-builder | Nixpacks README: maintenance mode, not under active development; Railway recommends **Railpack**. Railpack builds via BuildKit (LLB); production use: `railpack prepare` + BuildKit frontend | Builder uses Railpack + rootless buildkitd; config file `railpack.json` | github.com/railwayapp/nixpacks · railpack.com/platforms/running-railpack-in-production |
| 2 | Traefik rewrite-body plugin | `traefik/plugin-rewritebody` and `packruler/rewrite-body` have no commits since Nov 2022; maintained fork `kelnei/rewrite-body` v1.3.0 verified against Traefik 3.7.9; community reports decompression bugs in the old fork | Pinned fork; force `Accept-Encoding: identity` upstream + `compress` middleware; per-app opt-out | pkg.go.dev/github.com/kelnei/rewrite-body |
| 3 | "Ask your data" isolation via `getSetting('custom_app')` row policy | ClickHouse: custom settings need a declared prefix; `readonly=1` forbids changing settings (unless `changeable_in_readonly`); `readonly=2` allows SET, so generated SQL could override the filter | **Security fix:** per-app `ask_<slug>` users with fixed row policies + `readonly=1` profile (ADR-012) | clickhouse.com/docs/.../permissions-for-queries · settings-query-level · constraints-on-settings |
| 4 | Oracle Always Free 4 OCPU / 24 GB | Halved to **2 OCPU / 12 GB** on 15 Jun 2026 | Memory budget rebuilt for 12 GB | infoq.com/news/2026/07/oracle-cloud-free-tier-limits |
| 5 | Go version | **Go 1.27** released 19 Aug 2026 (Go 1.25 out of support) | Go 1.27 | go.dev/blog/go1.27 |
| 6 | Node 22 for services | Node 22 is maintenance; **Node 26 Active LTS since 28 Oct 2026**; Node 24 maintenance since 20 Oct 2026; Node 27+ moves to one release/year | Node 26 | nodejs.org/en/blog/announcements/evolving-the-nodejs-release-schedule · Node release schedule |
| 7 | Python 3.12 | Python **3.15.0** released 9 Oct 2026; 3.14 in bugfix | Python 3.14 (ADR-010) | python.org/downloads |
| 8 | Postgres 16 | **Postgres 18** has built-in `uuidv7()` | Postgres 18, UUIDv7 IDs | postgresql.org/docs/18/functions-uuid.html |
| 9 | ClickHouse version / arm64 | **26.8 LTS** (Aug 2026, support to Aug 2027); arm64 image needs ARMv8.2-A + RCpc | Pinned 26.8; first-boot check on Ampere | endoflife.date/clickhouse · hub.docker.com/r/arm64v8/clickhouse |
| 10 | Redpanda on a small arm64 host | v26.1.2 images include arm64; `--mode dev-container` bundles `--overprovisioned`; `--smp`/`--memory` flags | Explicit flags in compose | docs.redpanda.com rpk-redpanda-start · hub.docker.com/r/redpandadata/redpanda |
| 11 | Next.js version | **16.4** (6 Oct 2026); Node ≥ 20.9 | Next.js 16.4 | nextjs.org/blog/next-16-4 |
| 12 | Traefik version / Cloudflare DNS-01 | **3.7.x** current (3.7.12 seen); community thread on ACME/Cloudflare issues after 3.7.6 | Pin exact patch; M0 must prove issuance | traefik.io/blog/traefik-proxy-3-7-is-available · community.traefik.io |
| 13 | web-vitals FID | FID deprecated in v4, removed in v5; current **v6** exports onLCP/onINP/onCLS/onFCP/onTTFB | Tracker uses v6, no FID | github.com/GoogleChrome/web-vitals |
| 14 | Claude Code hooks | PreToolUse exit 2 blocks; `Stop` supports `{"decision":"block","reason"}` to keep Claude working; PostToolUse can't block | Hook table updated | code.claude.com/docs/en/hooks |
| 15 | Claude Code plugins | Only `plugin.json` inside `.claude-plugin/`; components at plugin root; `hooks/hooks.json`; `${CLAUDE_PLUGIN_ROOT}` | Agent-kit layout | code.claude.com/docs/en/plugins-reference |
| 16 | claude-code-action v1 | Automation mode via `prompt`; `claude_args`; `plugin_marketplaces` + `plugins`; `allowed_bots`; OAuth token tied to one person's subscription — API key recommended for secrets shared across repos | Workflows use these inputs | code.claude.com/docs/en/github-actions |
| 17 | Headless Claude Code flags | `-p`, `--max-turns`, `--max-budget-usd`, `--permission-mode`, `--allowedTools`, `--output-format json`, `--json-schema`, `--bare`, worktrees | Run limits in §6.2 of 12 | code.claude.com/docs/en/headless · cli-reference |
| 18 | GitHub App can't edit workflows without `workflows` permission | Confirmed ("refusing to allow a GitHub App to create or update workflow … without `workflows` permission") | Guardrail relies on it | github.blog changelog 2020-04-07 |
| 19 | arm64 CI runners | `ubuntu-24.04-arm` free in public repos (4 vCPU); private repos since Jan 2026 (2 vCPU, billed) | Native arm64 builds; E2E on arm64 | github.blog changelog 2025-08-07, 2026-01-29 |
| 21 | Existing skills/plugins to adopt | `claude-plugins-official` (registered by default) includes superpowers, code-review, pr-review-toolkit, security-guidance, feature-dev, frontend-design, commit-commands, skill-creator, LSP plugins; the old `anthropics/claude-code` marketplace is deprecated. `trailofbits/skills` marketplace has static-analysis, variant-analysis, differential-review, fix-review, insecure-defaults, sharp-edges, agentic-actions-auditor (CC-BY-SA-4.0). `anthropics/skills` has webapp-testing, skill-creator | Custom skills cut from 17 planned to 5 glue skills (12-agentic-system §8, ADR-020) | code.claude.com/docs/en/discover-plugins · github.com/obra/superpowers · github.com/trailofbits/skills · github.com/anthropics/skills |
| 20 | Hetzner pricing (fallback) | Prices raised 15 Jun 2026; cheap lines often unavailable | Fallback named, price not promised | docs.hetzner.com price-adjustment |

## Not verified in this session (agents must verify before relying on them)
- Cloudflare free Universal SSL covering only one subdomain level (widely documented; re-check).
- MaxMind GeoLite2 license terms and `geoipupdate` usage.
- Exact GitHub ruleset behavior for CODEOWNERS + auto-merge with GitHub App reviewers (design uses status checks to avoid depending on it).
- Subagent frontmatter field names (`tools`, `model`).
- `buf` remote plugin availability for Rust (prost/tonic) — fallback: generate Rust code in the consuming repo with `tonic-build`.
