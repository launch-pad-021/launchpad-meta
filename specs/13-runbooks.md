# 13 — Runbooks

Each runbook says who performs it: **agent** (automated, via workflows), **server** (`infra-sync`/cron on the host) or **developer**.

## 1. Deploy a platform service (agent → server)
1. Service PR merged → release-please PR merged → tag → images built (arm64+amd64) → GHCR.
2. `release-manager` opens a `versions.env` bump PR in `launchpad-infra` with changelog, migration note, rollback target.
3. Risk script: pure bump = low → auto-merge (high if the release includes a high-risk change).
4. `infra-sync` applies within 60 s: migration job → pull → up → `/readyz` (90 s) → smoke → status `infra-sync/deploy`.
5. `release-manager` watches 15 min: readyz, smoke, SLO metrics vs previous version → issue moves to `Verified`.

## 2. Roll back a platform service (agent; always allowed)
1. `incident-responder` opens a revert of the bump commit in `launchpad-infra`, label `rollback` → auto-merge without review (the only exception).
2. `infra-sync` redeploys the previous image (expand-only migrations keep the schema compatible).
3. If verification fails again → escalate G3 and freeze that service's deploys (`agent:hold` on its open release PRs).
**Developer fallback (SSH):** `cd /opt/launchpad && git revert --no-edit HEAD && docker compose up -d <svc>`.

## 3. Roll back a user app (developer or agent via API)
`POST /v1/deployments/{previous_id}/rollback` or `launch rollback`. Target < 10 s. If the previous image was garbage-collected, a rebuild is required (registry keeps the last 10 per app).

## 4. Restore from backup (server; drill monthly)
1. Pick backup set from R2 (`age` decrypt with the developer-held identity file).
2. Start a scratch compose project `lp-restore` with Postgres 18 + ClickHouse 26.8 on alternate ports.
3. `pg_restore` each DB; ClickHouse `RESTORE DATABASE ... FROM S3(...)`.
4. Validate: row counts within expected ranges, schema version table matches, sample queries succeed.
5. Post result to the `restore-drill` issue in `launchpad-meta`; tear down.
Real restore = same steps against the production project during a maintenance window (developer-led).

## 5. Rotate secrets (developer; agents prepare the PR/checklist)
| Secret | Procedure |
|---|---|
| `projects_master_key` | Add new key as `projects_master_key_v2`; projects supports key IDs (prefix byte); background re-encrypt job; remove old after 100% migrated |
| identity signing key | `identity` creates new active key (JWKS serves both); old retired after max token TTL (15 min) + 1 h |
| Service credentials | Replace file, `docker compose up -d <svc>`, update hash in identity (rotation script `scripts/rotate-svc-secret.sh`) |
| GitHub App key / webhook secret | Generate in GitHub, update files, restart scm; webhook secret rotation: GitHub supports one secret — rotate during low traffic |
| Cloudflare token | Create new scoped token, replace file, restart Traefik, revoke old |
| DB passwords | `ALTER ROLE`, replace file, restart service |
| Anthropic key (agents) | Replace org secret; (analytics) replace file, restart |

## 6. Incident response (agent-led)
1. Alert (Prometheus → notifier → `repository_dispatch`) or failed verification.
2. `incident-responder`: stabilize (rollback if a deploy happened in the last 2 h), then gather evidence (Jaeger, logs, metrics, recent changes), open `incident` issue with timeline and impact.
3. Bug flow for the fix (`12-agentic-system.md` §10.4).
4. Postmortem in `launchpad-meta/docs/incidents/YYYY-MM-DD-<slug>.md` if user-visible or > 30 min.

## 7. Disk full
Order: `docker image prune` (dangling) → registry GC → BuildKit cache prune (`buildctl prune --keep-storage 10GB`) → shorten ClickHouse logs TTL temporarily → Redpanda retention check. Alert threshold 80%.

## 8. Add a new app (owner)
Install the GitHub App on the repo → dashboard "New app" (or `launch init`) → set env vars → push. First deploy happens on the next push or via "Deploy now".

## 9. Certificate problems
Check Traefik logs for ACME errors; verify `CF_DNS_API_TOKEN` scope; use Let's Encrypt staging to test (`caServer`); pinned Traefik patch must be one where DNS-01 issuance was proven in M0.
