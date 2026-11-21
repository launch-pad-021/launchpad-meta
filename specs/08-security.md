# 08 — Security

## 1. Assets
| Asset | Where | Impact if compromised |
|---|---|---|
| App env vars (DB URLs, API keys) | `projects` DB (encrypted), in memory of deployer/runtime-agent briefly, in app containers | High |
| Launchpad master keys (projects env key, identity key) | Docker secrets on server | Critical |
| GitHub App private key | `scm` secret | High (code read access to installed repos) |
| Session cookies / CLI tokens | Browser / CLI config; hashed in `identity` | High |
| Docker socket | `runtime-agent` | Critical (root on host) |
| Visitor analytics | ClickHouse | Medium (privacy) |
| Cloudflare DNS token | Traefik secret | High (domain takeover/certs) |
| Anthropic API credential | GitHub org secret (agents), `analytics` secret (Ask) | Medium (cost) |

## 2. Actors and trust boundaries
- **Owner** (trusted, authenticated via GitHub allowlist).
- **Internet visitors** → only app containers and `/_lp/*` (untrusted input).
- **GitHub** → webhooks (verified by HMAC) and API (trusted after auth).
- **App code** (semi-trusted: the owner's code, but treat as untrusted to the platform) → runs in containers isolated from platform networks.
- **LLM output** (untrusted) → only executes as SQL under a per-app read-only ClickHouse user.
- **Agents** (CI) → no production access (see `12-agentic-system.md` §14).

Boundaries: Internet↔Traefik; Traefik↔services; app containers↔platform; services↔stores; builder↔user repo contents (untrusted build scripts run inside BuildKit sandbox); LLM↔ClickHouse.

## 3. Threats and controls (STRIDE summary)
| Threat | Control | Owner |
|---|---|---|
| Forged webhook triggers deploy | HMAC-SHA256 `X-Hub-Signature-256`, constant-time compare, delivery dedupe, repo must be a registered app | scm |
| Session theft / CSRF | HttpOnly+Secure+SameSite cookies, CSRF double-submit, short tokens hashed at rest, revocation event | identity, gateway |
| OAuth abuse | `state` + PKCE, allowlisted GitHub ID, relative redirect only | identity |
| Env var leakage | AES-256-GCM with AAD, master key only in projects, `GetRuntimeEnv` only for deployer identity, values never in events/logs, runtime log redaction | projects, deployer, runtime-agent |
| Malicious build script | Rootless BuildKit, no secrets at build, no Docker socket in builder, build timeout 15 min, network egress only | builder |
| Container escape / lateral movement | Apps only on `lp_apps`; `no-new-privileges`; cap drop ALL + minimal adds; PidsLimit 256; memory/CPU limits; read-only rootfs optional | runtime-agent |
| Route hijack (one app serving another's hostname) | Router validates hostname belongs to app (`<app>` suffix rules), short_id collision check | router |
| Tracker abuse (spam, injection) | Unknown host dropped, 8 KB limit, per-IP rate limit, strict JSON schema, no HTML rendering of raw values in dashboard (escape) | ingest, dashboard |
| Analytics de-anonymization | IP discarded after geo lookup; daily-rotating salt (deleted after 24 h); no cookies | processor |
| LLM-generated SQL reading other apps / exfiltrating | Per-app `ask_<slug>` user, `readonly=1` profile, row policies, query limits, no table functions; prompt treats data as untrusted | analytics |
| Prometheus query injection | PromQL built from fixed templates with validated app IDs | gateway |
| SSRF | Only builder (git/registries) and notifier/analytics (fixed hosts) have egress; no user-supplied URLs fetched | builder, notifier |
| DoS | Traefik rate limits on gateway; ingest limits; build concurrency 1; container limits | gateway, ingest, builder |
| Supply chain | Pinned digests, Renovate, gitleaks/semgrep/trivy/osv in CI, provenance attestations, reviewed third-party plugins (Traefik plugin pinned) | all |
| Agent misuse | See `12-agentic-system.md` §14 | — |

## 4. Secrets inventory (server, `/opt/launchpad/secrets/`, mode 0400, owned by root, mounted as Docker secrets)
| Secret file | Used by |
|---|---|
| `pg_<service>_password` (6) | each DB-owning service, postgres init |
| `projects_master_key` (32 bytes, base64) | projects |
| `identity_master_key` | identity (encrypts signing keys) |
| `svc_<service>` (13 service credentials) | each service (for IssueServiceToken); identity stores their hashes |
| `github_app_private_key.pem`, `github_webhook_secret`, `github_oauth_client_secret` | scm, identity |
| `cf_dns_token` | traefik |
| `ch_<user>_password` (logs_rw, processor_w, analytics_rw) | logs, processor, analytics |
| `buildkit_client_{ca,cert,key}` | builder |
| `telegram_bot_token`, `smtp_password` (optional) | notifier |
| `llm_api_key` | analytics |
| `maxmind_license_key` | geoipupdate |
| `r2_backup_key`, `age_backup_recipient` | backup jobs |
| `infra_sync_status_token`, `infra_deploy_key` | infra-sync |
Rotation procedures: `13-runbooks.md` §5.

## 5. Security review triggers
`security-auditor` reviews every PR touching: identity, projects crypto/GetRuntimeEnv, scm webhook handling, router rendering, runtime-agent container options, builder sandboxing, ingest input handling, analytics Ask path, gateway auth/CSRF/rate limits, infra networks/secrets. Weekly full scan; quarterly re-verification of OWASP Top 10 / ASVS applicability.
