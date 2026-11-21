# Service: projects

**Repo:** `launchpad-projects` · **Language:** Go 1.27 · **Ports:** 9000 / 8080 · **Owns:** Postgres `projects` (`05-data.md` §2) · **Risk:** high for crypto/`GetRuntimeEnv`, medium otherwise

## 1. Purpose
Source of truth for apps, their settings, and encrypted environment variables.

## 2. gRPC API (`launchpad.projects.v1.ProjectsService`)
| RPC | Authz | Behavior |
|---|---|---|
| `CreateApp(App fields)` | user JWT | Validate (slug, repo format `owner/name`, port, limits); unique `name` and (`repo_full_name`,`root_dir`); outbox `app.created.v1` |
| `GetApp(id \| name)` | user JWT or any service JWT | |
| `ListApps(page)` | user JWT or service JWT | |
| `FindAppsByRepo(repo_full_name)` | service JWT (deployer) | All apps for a repo (multiple root dirs possible) |
| `UpdateApp(id, field_mask, fields)` | user JWT | `name` and `repo_full_name` are immutable; outbox `app.updated.v1` with `changed_fields` |
| `DeleteApp(id)` | user JWT | Delete row (env vars cascade); outbox `app.deleted.v1`; returns immediately |
| `SetEnvVar(app_id, key, value, scope)` | user JWT | Encrypt, upsert; outbox `env.changed.v1` (keys only) |
| `DeleteEnvVar(app_id, key, scope)` | user JWT | outbox `env.changed.v1` |
| `ListEnvVars(app_id, reveal)` | user JWT | Masked values unless `reveal=true` (gateway requires a fresh session < 10 min or explicit `?reveal=1`) |
| `GetRuntimeEnv(app_id, kind)` | **service JWT `svc:deployer` only** | Merge: `all` then `production` or `preview` (scope-specific wins). Return map; audit-log the access (no values) |

## 3. Encryption
- AES-256-GCM, 12-byte random nonce, AAD = `app_id || 0x00 || key || 0x00 || scope`.
- Stored: `0x01` (key version) || nonce || ciphertext||tag. Key version enables rotation (`13-runbooks.md` §5).
- Master key from `/run/secrets/projects_master_key` (32 bytes base64); refuse to start if missing/short.
- Values never logged, never in events, never returned by any RPC except `ListEnvVars(reveal)` and `GetRuntimeEnv`.

## 4. Events (via outbox, topic `lp.projects`, key `app_id`)
`app.created.v1`, `app.updated.v1`, `app.deleted.v1`, `env.changed.v1`. Consumes none.

## 5. Config
`LP_PG_DSN_FILE`, `LP_PROJECTS_MASTER_KEY_FILE` + common.

## 6. Tests
Validation table tests; uniqueness conflicts → ALREADY_EXISTS; encryption round trip; AAD tamper (moving a ciphertext to another key/app fails); `GetRuntimeEnv` denied for `svc:builder` and user JWT; scope merge; outbox rows written in the same transaction (simulate failure after insert → no event); field-mask updates.

## 7. Acceptance
Apps CRUD via gateway; env vars encrypted at rest (DB inspection shows no plaintext); only deployer can fetch runtime env; events appear for every change.
