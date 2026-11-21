# Service: router

**Repo:** `launchpad-router` · **Language:** Go 1.27 · **Ports:** 9000 / 8080 · **Owns:** Postgres `router` (`05-data.md` §5) + writes `/etc/traefik/dynamic/<app>.yml` · **Risk:** high (all changes)

## 1. Purpose
Owns hostname → deployment routing, renders Traefik configuration, and resolves hosts for Insights.

## 2. gRPC API (`launchpad.router.v1.RouterService`)
| RPC | Caller | Behavior |
|---|---|---|
| `SetRoute(hostname, app_id, app_name, deployment_id, kind, upstream, health_path, insights, inject)` | deployer | Validate hostname (§3); upsert; re-render that app's file; **wait until Traefik reports the router + service** (`GET http://traefik:8080/api/http/routers/<name>@file`, poll 100 ms, timeout 10 s); outbox `route.changed.v1` {action:set} |
| `RemoveRoute(hostname)` | deployer | Delete; re-render; outbox `route.changed.v1` {action:removed} |
| `RemoveRoutesForApp(app_id)` | internal (`app.deleted`) | Delete all; delete file |
| `ResolveHost(hostname)` | ingest | `{found, app_id, app_name, deployment_id, kind, insights}` from an in-memory map (loaded at start, updated on writes) |
| `ListRoutes(app_id?)` | gateway | |

## 3. Hostname rules
- Must end with `.apps.<base_domain>`; label part:
  - production: `<app_name>`
  - preview: `<branch_slug>--<app_name>`
  - immutable: `d-<short_id>--<app_name>`
- The part after the last `--` (or the whole label for production) MUST equal `app_name` of the request (prevents one app claiming another's host).
- Label ≤ 63 chars (else truncate branch slug and append 4-char hash).

## 4. Rendering
One file per app: `/etc/traefik/dynamic/<app_name>.yml`, written atomically (write `.tmp` → fsync → rename). Template (Go `text/template`, golden-file tested):
```yaml
http:
  routers:
{{- range .Routes }}
    {{ .RouterName }}:                       # e.g. myapp-prod, myapp-pv-feat-x, myapp-d-7f3a1b2c
      rule: "Host(`{{ .Hostname }}`)"
      service: {{ .ServiceName }}            # <app>-<short_id>
      entryPoints: [websecure]
      middlewares: [{{ if .Inject }}lp-security-headers@file, lp-compress@file, lp-identity-encoding@file, lp-inject@file{{ else }}lp-security-headers@file{{ end }}]
      tls: { certResolver: cf, domains: [{ main: "apps.{{ $.BaseDomain }}", sans: ["*.apps.{{ $.BaseDomain }}"] }] }
{{- if .Insights }}
    {{ .RouterName }}-lp:
      rule: "Host(`{{ .Hostname }}`) && PathPrefix(`/_lp/`)"
      priority: 1000
      service: ingest@file
      entryPoints: [websecure]
      middlewares: [lp-security-headers@file]
      tls: { certResolver: cf }
{{- end }}
{{- end }}
  services:
{{- range .Services }}
    {{ .Name }}:
      loadBalancer:
        servers: [{ url: "{{ .Upstream }}" }]
        healthCheck: { path: "{{ .HealthPath }}", interval: "10s", timeout: "3s" }
{{- end }}
```
- Services referenced by multiple routers are emitted once. Router names are sanitized to `[a-z0-9-]`.
- On startup: re-render all apps from DB (self-healing); delete files for apps with no routes.

## 5. Events
Publishes `route.changed.v1` (topic `lp.routes`, key = app_id). Consumes `app.deleted.v1` (remove all), `app.updated.v1` (if `insights_enabled`/`insights_inject` changed → update flags on all the app's routes + re-render).

## 6. Config
`LP_PG_DSN_FILE`, `LP_TRAEFIK_DYNAMIC_DIR=/etc/traefik/dynamic`, `LP_TRAEFIK_API=http://traefik:8080`, `LP_BASE_DOMAIN` + common.

## 7. Tests
Golden files (production only; production + preview + immutable; insights off; inject off); hostname validation table incl. hijack attempts; atomic write (crash between write and rename leaves old file valid); Traefik confirmation using a real Traefik container; ResolveHost after writes and after restart; app.updated flag propagation.

## 8. Acceptance
Swap under load with 0 failed requests (E2E 2); a route for `other--myapp` requested with `app_name=evil` is rejected; Traefik config always parses (traefik `--configfile` validation in CI on golden files).
