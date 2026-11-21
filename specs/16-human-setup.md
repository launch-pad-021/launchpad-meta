# 16 — Developer One-Time Setup (Day 0)

Agents can't create accounts, hold production secrets or touch the server. Do these once, in order. Estimated time: 3–4 hours. Tick each box in a copy of this file in `launchpad-meta`.

## 1. Accounts
- [ ] Domain registered; DNS on Cloudflare (free plan).
- [ ] Oracle Cloud account (card verification); home region chosen with Ampere A1 capacity. Create VM: Ampere A1, 2 OCPU / 12 GB, Ubuntu 24.04 arm64, 100 GB boot volume. Open ingress 80/443 (and 22 from your IP) in the VCN security list.
- [ ] Cloudflare R2 bucket `launchpad-backups` + access key (Object Read & Write on that bucket only).
- [ ] MaxMind account + GeoLite2 license key.
- [ ] Telegram bot via @BotFather; note bot token and your chat ID.
- [ ] Anthropic credential for agents: Console API key (recommended for org-wide use, supports budget caps) **or** `claude setup-token` subscription token.

## 2. GitHub
- [ ] Create organization `<org>` (free). Decide public vs private repos (public = free unlimited Actions minutes incl. arm64 4-vCPU runners).
- [ ] Separate admin account (2FA) for emergencies; your daily account is not allowed to bypass rulesets.
- [ ] Create **four GitHub Apps** (org-owned, not public):
  | App | Repository permissions | Install on |
  |---|---|---|
  | `launchpad-dev` | Contents RW, Pull requests RW, Issues RW, Metadata R — **no Workflows, no Administration** | all launchpad repos |
  | `launchpad-review` | Contents R, Pull requests RW, Commit statuses RW, Metadata R | all launchpad repos |
  | `launchpad-release` | Contents RW, Pull requests RW, Metadata R | `launchpad-infra` (+ service repos for release-please) |
  | `launchpad-scm` (the product's GitHub App) | Contents R, Metadata R; webhooks: push, delete, installation; webhook URL `https://api.launchpad.<domain>/v1/webhooks/github` + secret | repos you'll deploy |
  Also create an OAuth App (or use `launchpad-scm`'s user auth) for dashboard login; callback `https://api.launchpad.<domain>/v1/auth/github/callback`.
- [ ] Org secrets (limited to launchpad repos): `ANTHROPIC_API_KEY` (or `CLAUDE_CODE_OAUTH_TOKEN`), `LP_DEV_APP_ID` + `LP_DEV_APP_KEY`, `LP_REVIEW_APP_ID` + `LP_REVIEW_APP_KEY`, `LP_RELEASE_APP_ID` + `LP_RELEASE_APP_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- [ ] Org variables: `AGENTS_ENABLED=true`, `AGENTS_DAILY_BUDGET_USD=<n>`, `LP_ORG=<org>`, `LP_OWNER_LOGIN=<your GitHub login>`, `LP_BASE_DOMAIN=<domain>`.
- [ ] Create `launchpad-meta` and `launchpad-agent-kit` repos (empty). Copy this pack into `launchpad-meta`; copy `bootstrap/launchpad-meta/CLAUDE.md` to its root; copy `bootstrap/agent-kit/*` into `launchpad-agent-kit`.
- [ ] GitHub Project (v2) "Launchpad" with fields: Status (Backlog, Ready, In progress, In review, Merged, Deployed, Verified, Done, Blocked, Failed, On hold), Risk, Milestone, Repo.
- [ ] After A0-08 lands: run `scripts/create-repos.sh` (creates all repos from templates and applies rulesets + CODEOWNERS).

## 3. Server
- [ ] SSH in; run `launchpad-infra/bootstrap/server.sh` after M0-01 is merged (agents write it; you review and run it).
- [ ] Create `/opt/launchpad/secrets/` files per `08-security.md` §4 (generate keys with the commands in `launchpad-infra/secrets/README.md`). Back up the `age` identity file in your password manager — it's the only way to decrypt backups.
- [ ] Install the read-only deploy key for `launchpad-infra` and the `infra-sync` status token; enable `infra-sync.timer`.

## 4. DNS
- [ ] A records (DNS-only): `launchpad`, `api.launchpad`, `*.apps` → server IP.
- [ ] Cloudflare API token: Zone:Read + DNS:Edit for the zone → `cf_dns_token` secret.

## 5. Final checks
- [ ] `AGENTS_ENABLED=true`; start with autonomy phase **P0** (you merge everything).
- [ ] Follow `bootstrap/KICKOFF.md`.
