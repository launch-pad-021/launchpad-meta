# 00 — Product

## 1. Vision
Launchpad lets its owner deploy any side project with `git push` to a server they control, and see how each deploy affects real users — without paying for a hosted platform.

Push to GitHub → the app is built into a container → it's live at `https://<app>.apps.<domain>` with HTTPS, logs, metrics, preview URLs per branch, one-click rollback, a CLI, and privacy-friendly analytics with Core Web Vitals per deploy.

## 2. Users
- **Owner (single user):** a full-stack developer deploying personal projects (Node/Next.js, static sites, Go, Python). Logs in with GitHub. Multi-user and teams are out of scope.
- **Visitors:** people using the deployed apps. They never interact with Launchpad directly; Insights measures their visits anonymously.

## 3. Goals
1. Deploy a typical Next.js / Node / Go / Python / static app from a GitHub repo with zero config (Railpack auto-detection) or a Dockerfile.
2. Production deploys are zero-downtime; a failed health check never replaces a working version.
3. Every branch gets a preview URL; every deploy gets an immutable URL.
4. Rollback to any previous successful deploy in under 10 seconds, without rebuilding.
5. Analytics is on automatically for every app, with no code change, no cookies and no stored IP addresses.
6. Web Vitals are compared per deploy, and a regression is flagged and alerted.
7. Runs on one free ARM server (Oracle Always Free, 2 OCPU / 12 GB).
8. Serves as a learning project: Go, Rust, Python, gRPC, event-driven design, sagas, outbox, Kafka-compatible streaming, OLAP, distributed tracing, BuildKit, reverse proxying, ACME.

## 4. Non-goals (v1)
Multiple users, teams or RBAC · billing · Kubernetes · serverless/edge functions · managed databases for apps · multi-node scheduling (designed for, not built) · Windows apps · build-time secrets · custom domains per app (stretch).

## 5. Feature list (v1)

| Area | Features |
|---|---|
| Apps | Create from a GitHub repo; settings (port, health path, resources, build strategy, root dir); encrypted env vars with scopes (all/production/preview); delete |
| Deploys | Auto on push; manual deploy; branch previews; immutable deploy URLs; cancel; rollback; live build logs; FSM timeline; zero-downtime swap; automatic cleanup when a branch is deleted |
| Runtime | Runtime logs (live + search); CPU/memory/network charts; crash alerts |
| Insights | Visitors, pageviews, sessions, bounce rate, duration; sources, pages, countries, devices; realtime; custom events; funnels; Web Vitals (LCP, INP, CLS, FCP, TTFB) per route and per deploy; regression detection; "Ask your data" (natural language → SQL) |
| Platform | Dashboard (Next.js), CLI (`launch`), Telegram alerts, Platform health page, distributed traces |

## 6. Success criteria
- A fresh fixture Next.js app goes from `git push` to live in ≤ 3 minutes on the target server (cold cache) and ≤ 90 s (warm cache).
- A production swap under `hey -z 60s` load has 0 failed requests.
- Rollback completes in < 10 s.
- Insights numbers match raw-table queries within 2%.
- Idle platform memory (no user apps) ≤ 7.5 GB, leaving ≥ 4.5 GB for apps.

## 7. Glossary
| Term | Meaning |
|---|---|
| App | A GitHub repo registered in Launchpad (one per repo + root dir) |
| Deployment | One build+run of an app at one commit on one branch |
| Route | Hostname → deployment mapping owned by `router` |
| Production / preview / immutable | Route kinds: default branch / other branches / one specific deployment |
| Saga | The multi-service deploy workflow orchestrated by `deployer` |
| Outbox | Table where a service writes events in the same DB transaction as its state change |
| Insights | Launchpad's built-in analytics module (`ingest`, `processor`, `analytics`) |
| Tracker | `/_lp/script.js`, injected into app HTML |
| Vitals regression | p75 of a Web Vital ≥ 20% worse than the previous production deploy with ≥ 50 samples |
| G1/G2/G3 | Human gates in the agentic system (milestone plan, high-risk PR, escalation) |
