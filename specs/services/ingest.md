# Service: ingest (+ tracker)

**Repo:** `launchpad-ingest` · **Language:** Rust (tokio, axum, rdkafka, tonic client; `launchpad-rust-kit`); tracker in `tracker/` (TypeScript + esbuild) · **Ports:** HTTP 8080 (public via Traefik `/_lp/*`), metrics on internal 8081 · **Owns:** none · **Risk:** high for input handling, medium otherwise

## 1. Tracker (`tracker/`, served as `/_lp/script.js`)
- Size budget: **≤ 4 KB gzipped** including `web-vitals` v6 (CI check).
- On load: send `pageview`. SPA: patch `history.pushState`/`replaceState`, listen to `popstate`; send `pageview` when `location.pathname+search` changes (debounce 100 ms).
- Web Vitals: `onLCP`, `onINP`, `onCLS`, `onFCP`, `onTTFB` (v6 API); each reports once per page view (final value) as `web_vital` with `n` = metric name, `v` = value.
- Custom events: `window.lp('event', name, props?)` — name `[a-z0-9_]{1,40}`, ≤ 10 props, keys ≤ 40 chars, values ≤ 200 chars (strings/numbers/booleans).
- Payload (JSON): `{ "t": "pageview|custom|web_vital", "u": "<path+query>", "r": "<document.referrer>", "w": <innerWidth>, "n": "<name>", "v": <number>, "p": {<props>} }`.
- Transport: `navigator.sendBeacon('/_lp/e', blob)`; fallback `fetch(..., {keepalive: true, method:'POST'})`. Batch vitals on `visibilitychange=hidden`.
- Respect `navigator.doNotTrack === '1'` → send nothing. No cookies, no storage APIs, no fingerprinting.
- Script served with `Cache-Control: public, max-age=3600` and an ETag (content hash).

## 2. HTTP endpoints
| Endpoint | Behavior |
|---|---|
| `GET /_lp/script.js` | Embedded bundle (compiled at image build) |
| `POST /_lp/e` | Content-Type `text/plain` or `application/json`; body ≤ 8 KB; validate schema; resolve host; enrich server-side; produce; **always** reply `204` quickly (even when dropped, to avoid leaking validity), except `413` for oversize |

## 3. Processing per request
1. `Host` → `router.ResolveHost` via local cache (`moka`, TTL 5 min, invalidated by `route.changed.v1` consumer). Unknown host or `insights=false` → drop (metric `dropped{reason=unknown_host}`).
2. Validate payload strictly (types, lengths: `u` ≤ 2048, `r` ≤ 2048, props per tracker rules); invalid → drop.
3. Client IP = first IP in `X-Forwarded-For` appended by Traefik (configure Traefik `forwardedHeaders.trustedIPs` = none from internet; ingest trusts only the last hop added by Traefik).
4. Rate limit: 50 req/s per IP (in-memory GCRA); 2,000 req/s per app.
5. Produce `insights.event.v1` to `events.raw` (key = app_id) with `received_at`, `app_id`, `app_name`, `deployment_id`, `route_kind`, `ip`, `user_agent` (≤ 512 chars), and the payload. Producer: `acks=all`, idempotent, `linger.ms=20`, compression `zstd`.
6. If Redpanda is unavailable: bounded in-memory queue (10k events) then drop with metric.

## 4. Config
`LP_KAFKA_BROKERS`, `LP_ROUTER_ADDR`, `LP_SERVICE_SECRET_FILE` + common.

## 5. Performance targets
p99 handler latency < 5 ms (excluding produce ack, which is async); 5k events/s on 1 core; memory < 64 MB.

## 6. Tests
Payload validation property tests (`proptest`); oversize; unknown host; cache invalidation on `route.changed`; rate limits; DNT respected (tracker unit test with jsdom); bundle size check; SPA navigation tests (Playwright in `launchpad-e2e`); k6 throughput.

## 7. Acceptance
Unmodified `next-basic` app produces pageview + web vitals events with correct `app_id`/`deployment_id`/`route_kind`; script size within budget.
