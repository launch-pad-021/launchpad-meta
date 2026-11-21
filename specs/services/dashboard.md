# App: dashboard

**Repo:** `launchpad-dashboard` · **Stack:** Next.js 16.4 (App Router), React 19, TypeScript strict, Tailwind CSS 4, shadcn/ui, TanStack Query, Recharts · **Runtime:** Node 26, `output: 'standalone'` · **Talks only to:** gateway (`06-public-api.md`) · **Risk:** low (auth/CSRF handling: medium)

## 1. Pages
| Route | Content |
|---|---|
| `/login` | "Sign in with GitHub" → `/v1/auth/github/start` |
| `/` | App grid: status dot (last production deploy), production URL, last deploy time, CPU/mem sparkline, visitors-today sparkline, vitals badge |
| `/apps/new` | Form: repo (picker from `GET /v1/repos`, i.e. repos where the GitHub App is installed), name, root dir, port, health path |
| `/apps/[id]` | Tabs: **Deployments** (list, filters by branch/status, previews, URLs) · **Logs** (runtime live + search) · **Metrics** · **Insights** · **Env** · **Settings** |
| `/deployments/[id]` | FSM timeline with step durations; live build log viewer (ANSI colors, virtualized list, auto-scroll with "jump to bottom", resume on reconnect); runtime logs; vitals vs previous deploy; actions: Rollback, Cancel, Visit, Copy URL |
| `/apps/[id]/insights` | KPI header with deltas; visitors/pageviews chart with deploy markers (hover: commit message); breakdown tables; countries map; Speed Insights (p75 gauges with good/needs-improvement/poor thresholds, per-route table, per-deploy comparison); funnels builder; realtime counter; Ask box with chart + "Show SQL" |
| `/settings` | CLI tokens (create shows value once), notification channels (+ test), GitHub App installation link |
| `/platform` | `09-observability.md` §4 |

## 2. Design rules (anti-AI-slop skill applies)
- Product-specific, information-dense layout; neutral palette with one accent; status colors only for status; no decorative gradients/glass; system font stack + a monospace for logs and SHAs.
- Every data view has loading, empty, error and partial states; destructive actions confirm with the app name typed.
- Accessibility: WCAG 2.2 AA; keyboard navigable; focus visible; charts have table alternatives; `prefers-reduced-motion` respected.
- Responsive: usable at 375 px (read-only views + rollback), full at ≥ 1024 px.

## 3. Data and security
- Server Components fetch with the session cookie forwarded to gateway (server-side `fetch` to internal gateway URL); client mutations via TanStack Query with CSRF header.
- Never render raw analytics strings as HTML (paths, referrers, props are escaped text).
- No secrets in the client bundle; env values shown only after explicit "Reveal".

## 4. Tests
Playwright: login (mocked gateway), create app, env reveal flow, deployment page live logs (SSE mock), rollback confirm, Insights renders with fixture data, Ask shows SQL; axe on every page; screenshots at 375/768/1280 attached to PRs.
