# Event catalog

Every event is wrapped in the envelope (`envelope.schema.json`, `specs/03-conventions.md` §6). `data` is validated against `<type>.schema.json`. Producers MUST validate in tests; consumers MUST tolerate unknown fields.

| Type | Topic | Key | Producer | Consumers | Meaning |
|---|---|---|---|---|---|
| `scm.push.v1` | `lp.scm` | repo_full_name | scm | deployer | A branch was pushed |
| `scm.branch_deleted.v1` | `lp.scm` | repo_full_name | scm | deployer | A branch was deleted |
| `app.created.v1` | `lp.projects` | app_id | projects | analytics | An app was registered |
| `app.updated.v1` | `lp.projects` | app_id | projects | router, analytics | App settings changed |
| `app.deleted.v1` | `lp.projects` | app_id | projects | deployer, router, analytics | An app was deleted |
| `env.changed.v1` | `lp.projects` | app_id | projects | — | Env var keys changed (never values) |
| `token.revoked.v1` | `lp.identity` | token_id | identity | gateway | A CLI token was revoked |
| `build.requested.v1` | `lp.deployments` | app_id | deployer | builder | Build this commit |
| `deployment.status_changed.v1` | `lp.deployments` | app_id | deployer | gateway | Deployment FSM transition |
| `deployment.live.v1` | `lp.deployments` | app_id | deployer | analytics | A deployment started serving traffic |
| `deployment.failed.v1` | `lp.deployments` | app_id | deployer | notifier | A deployment failed (or a live one is crash-looping: stage=runtime) |
| `build.started.v1` | `lp.builds` | app_id | builder | deployer | Builder picked up a build |
| `build.completed.v1` | `lp.builds` | app_id | builder | deployer | Image built and pushed |
| `build.failed.v1` | `lp.builds` | app_id | builder | deployer | Build failed |
| `build.log.v1` | `lp.build-logs` | app_id | builder | logs | Batch of build log lines |
| `runtime.log.v1` | `lp.runtime` | app_id | runtime-agent | logs | Batch of runtime log lines (seq assigned by logs) |
| `container.exited.v1` | `lp.runtime` | app_id | runtime-agent | deployer, notifier | An app container exited |
| `route.changed.v1` | `lp.routes` | app_id | router | ingest | A hostname route was set or removed |
| `vitals.regressed.v1` | `lp.insights` | app_id | analytics | deployer, notifier | A deployment's Web Vitals p75 regressed |
| `insights.event.v1` | `events.raw` | app_id | ingest | processor | Raw tracker event (contains IP + UA; processor discards IP) |
| `dlq.v1` | `events.dlq` | original key | any consumer | (alerting, manual replay) | A message that failed processing 5 times |

## Rules
- Events never contain secrets, env var values or tokens. Only `insights.event.v1` contains an IP address, and only until `processor` handles it.
- Breaking a schema means a new `.v2` type; producers emit both until all consumers move.
- Domain events from DB-backed services are written through the outbox.
