# Service: identity

**Repo:** `launchpad-identity` · **Language:** Go 1.27 (`launchpad-go-kit`) · **Ports:** gRPC 9000, HTTP 8080 (health/metrics) · **Owns:** Postgres `identity` (`05-data.md` §1) · **Risk class:** high (all changes)

## 1. Purpose
Authenticates the owner (GitHub OAuth), manages sessions and CLI tokens, issues JWTs for internal calls, and authenticates services to each other.

## 2. gRPC API (`launchpad.identity.v1.IdentityService`)
| RPC | Caller | Behavior |
|---|---|---|
| `BeginOAuth(redirect_to)` | gateway | Create `state` (32 random bytes, b64url) + PKCE verifier (S256); store 10 min; return GitHub authorize URL (scope `read:user`) |
| `CompleteOAuth(code, state)` | gateway | Validate+delete state; exchange code (with verifier); fetch GitHub user; **reject unless `github_id` == `LP_OWNER_GITHUB_ID`**; upsert user; create session (random 32 bytes → cookie value; store sha256); return `session_token`, `expires_at`, `redirect_to` |
| `Authenticate(session_token \| api_token)` | gateway | Look up hash; check expiry/revocation; slide session expiry (if > 1 day since last slide); update `last_used` (async, batched); return `user_id`, `github_login`, `scopes`, and a **user JWT** (Ed25519, 15 min, claims `sub`, `scope`, `typ=user`, `iss=identity`, `aud=launchpad`, `kid`) |
| `Logout(session_token)` | gateway | Delete session |
| `CreateToken(name, scopes, expires_in?)` | gateway (user JWT) | Token = `lp_` + 40 b62 chars; store sha256 + prefix; return plaintext once |
| `ListTokens` / `RevokeToken(id)` | gateway | Revoke sets `revoked_at` + outbox `token.revoked.v1` |
| `IssueServiceToken(service, secret)` | every service at startup / every 10 min | Verify secret against stored Argon2id hash for that service; return **service JWT** (Ed25519, 15 min, `sub=svc:<name>`, `typ=service`) |
| `GetJWKS` | every service | Active + recently retired public keys (cache 5 min in clients) |

## 3. Behavior details
- Signing keys: Ed25519; private key encrypted with `identity_master_key` (AES-256-GCM). One active key; rotation per `13-runbooks.md` §5. On first start with no key → generate.
- Service credentials: list of 13 service names fixed in config; secrets read from `/run/secrets/svc_<name>` *hashes* file `svc_hashes.json` (Argon2id). identity itself verifies its own JWTs locally.
- Rate limit `CompleteOAuth` and `Authenticate` failures: 10/min per source (gateway passes client IP in metadata).
- Expired sessions/states purged hourly.

## 4. Events
Publishes `token.revoked.v1` (topic `lp.identity`, key = token id) via outbox. Consumes none.

## 5. Config
`LP_PG_DSN_FILE`, `LP_IDENTITY_MASTER_KEY_FILE`, `LP_GITHUB_OAUTH_CLIENT_ID`, `LP_GITHUB_OAUTH_CLIENT_SECRET_FILE`, `LP_OWNER_GITHUB_ID`, `LP_SVC_HASHES_FILE`, `LP_PUBLIC_API_BASE` (for callback URL) + common vars.

## 6. Security
Constant-time comparisons; tokens never logged (log only `prefix`); OAuth redirect must be a relative path; session cookie attributes set by gateway; JWT `aud`/`iss`/`exp`/`nbf` validated by go-kit interceptors in every service; clock skew 30 s.

## 7. Observability
Metrics: `lp_identity_auth_total{method,result}`, `lp_identity_tokens_active`, `lp_identity_service_tokens_issued_total{service}`.

## 8. Tests (required)
OAuth happy path with a fake GitHub (httptest); state replay rejected; non-owner rejected; PKCE verifier mismatch; session sliding; token create/list/revoke + event; service token wrong secret; JWT verification incl. key rotation (old key still valid until retired); purge jobs.

## 9. Acceptance
- Owner can log in via GitHub; any other GitHub account gets 403.
- CLI token works until revoked; revocation takes effect within 1 request (gateway doesn't cache token auth > 30 s).
- All services obtain service JWTs at startup and calls without valid JWTs are rejected with UNAUTHENTICATED.
