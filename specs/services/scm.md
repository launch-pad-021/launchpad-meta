# Service: scm

**Repo:** `launchpad-scm` · **Language:** TypeScript on Node 26 (`launchpad-ts-kit`) · **Ports:** gRPC 9000; HTTP 8080 (webhook + health/metrics) · **Owns:** Postgres `scm` (`05-data.md` §3) · **Risk:** high for webhook verification, medium otherwise

## 1. Purpose
Integrates with GitHub as a GitHub App: receives and verifies webhooks, turns them into events, and issues short-lived clone credentials.

## 2. HTTP
`POST /v1/webhooks/github` (routed by Traefik from the API host directly to scm; body limit 5 MB).
1. Verify `X-Hub-Signature-256` with `@octokit/webhooks` `verify` (HMAC-SHA256, constant time) using `github_webhook_secret`. Invalid → 401, metric, no body logged.
2. Dedupe by `X-GitHub-Delivery` (insert into `webhook_deliveries`; conflict → 200 "duplicate").
3. Handle:
   - `push` (not a tag; `deleted=false`) → outbox `scm.push.v1` {repo_full_name, branch, commit_sha (`after`), commit_message (head_commit.message, truncated 500), author_login, pushed_at, forced}.
   - `push` with `deleted=true` or `delete` (ref_type=branch) → `scm.branch_deleted.v1`.
   - `installation`, `installation_repositories` → upsert/delete `installations`.
   - Others → 204 ignored.
4. Respond within 2 s (GitHub timeout is 10 s); work is just DB inserts.

scm does **not** know which repos are registered apps; `deployer` ignores pushes for unknown repos.

## 3. gRPC API (`launchpad.scm.v1.ScmService`)
| RPC | Caller | Behavior |
|---|---|---|
| `GetCloneCredentials(repo_full_name)` | builder | Installation token scoped to that single repo with `contents:read`, expires ≤ 1 h; return `clone_url` (https), `username="x-access-token"`, `token`, `expires_at`. Never log the token |
| `GetCommit(repo_full_name, ref)` | deployer (manual deploys without sha) | Resolve branch → sha + message |
| `ListBranches(repo_full_name)` | gateway (UI) | |
| `ListInstalledRepos()` | gateway (UI) | From `installations` table |

## 4. Events
Publishes (outbox, topic `lp.scm`, key = `repo_full_name`): `scm.push.v1`, `scm.branch_deleted.v1`. Consumes none.
(Key is the repo name because scm doesn't know app IDs; deployer re-keys downstream events by `app_id`.)

## 5. Config
`LP_PG_DSN_FILE`, `LP_GITHUB_APP_ID`, `LP_GITHUB_APP_PRIVATE_KEY_FILE`, `LP_GITHUB_WEBHOOK_SECRET_FILE` + common.

## 6. Tests
Signature valid/invalid/missing; replayed delivery; push → event payload validated against schema; branch delete paths; tag push ignored; installation token request mocked (nock); token not present in logs (log capture assertion).

## 7. Acceptance
A real push to an installed repo produces exactly one `scm.push.v1`; a forged webhook is rejected; builder can clone a private repo with returned credentials.
