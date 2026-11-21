# Service: runtime-agent

**Repo:** `launchpad-runtime-agent` · **Language:** Go 1.27 (Docker Engine API client) · **Ports:** 9000 (bound to `lp_internal` IP only) / 8080 · **Owns:** none (Docker is the source of truth) · **Risk:** high (all changes)

## 1. Purpose
Runs app containers on its node: start, stop, health-check, watch exits, and stream runtime logs.

## 2. gRPC API (`launchpad.runtime.v1.RuntimeAgentService`) — callers: deployer only (service JWT check)
| RPC | Behavior |
|---|---|
| `StartContainer(deployment_id, app_id, app_name, short_id, image_ref, env, port, cpu, memory_mb, kind)` | Idempotent: if a container with label `lp.deployment_id=<id>` exists, return it. Pull `image_ref` from `127.0.0.1:5000` (host-published registry). Create `lp-<app>-<short_id>` with settings in §3; start; return `container_id`, `container_name`, `upstream=http://lp-<app>-<short_id>:<port>` |
| `StopContainer(container_id \| deployment_id, grace_seconds=10)` | SIGTERM, wait, SIGKILL, remove. Idempotent |
| `CheckHealth(deployment_id, path)` | HTTP GET `upstream+path` via `lp_apps`, 2 s timeout, no redirects followed; returns `healthy (2xx/3xx)`, `status_code`, `latency_ms`, `container_running` |
| `ListContainers(app_id?)` | Containers with `lp.*` labels and state |
| `GetNodeStats` | CPU count, memory total/available, disk free, running app containers |

## 3. Container settings (MUST)
- Network `lp_apps` only. Hostname = container name.
- Env: decrypted env from request + `PORT`, `LAUNCHPAD_DEPLOYMENT_ID`, `LAUNCHPAD_ENV=production|preview`, `LAUNCHPAD_APP`. Env is held in memory only for the call; never logged.
- `NanoCPUs = cpu × 1e9`, `Memory = memory_mb MiB`, `MemorySwap = Memory`, `PidsLimit = 256`, `Ulimits nofile 4096`.
- `SecurityOpt: ["no-new-privileges"]`, `CapDrop: ["ALL"]`, `CapAdd: ["NET_BIND_SERVICE"]` only if port < 1024.
- `RestartPolicy: on-failure, MaximumRetryCount 3`.
- Labels: `lp.app_id`, `lp.app_name`, `lp.deployment_id`, `lp.kind`, `lp.managed=true`.
- Log driver `json-file`, `max-size=10m`, `max-file=3`.
- Never privileged, never host network, never mounts.

## 4. Watchers
- Docker events stream (filter `label=lp.managed=true`, event `die`) → `container.exited.v1` {exit_code, oom_killed, restart_count}.
- Runtime logs: for each running managed container, follow logs (stdout/stderr, timestamps) → batch → `runtime.log.v1` (250 ms / 100 lines); **redact** secrets: keep the env values longer than 6 characters that were passed at start in memory for the container's lifetime (never persisted), and replace any occurrence in a log line with `[redacted]` (multi-pattern match, e.g. Aho-Corasick). Resume from last timestamp after restart.
- Janitor (every 5 min): containers labelled `lp.managed` whose deployment is terminal (asks deployer `GetDeployment`) for > 10 min → stop + remove; report count metric.

## 5. Config
`LP_DOCKER_HOST=unix:///var/run/docker.sock`, `LP_REGISTRY_PULL=127.0.0.1:5000`, `LP_APPS_NETWORK=lp_apps`, `LP_NODE_NAME=node-1`, `LP_GRPC_BIND=<lp_internal ip>:9000` + common.

## 6. Tests
Integration with Docker-in-Docker or the runner's Docker: start idempotency; limits applied (inspect); security options applied; health check against fixture images (`never-healthy`, `slow-start`); stop idempotent; exit events emitted; log redaction (env-echo fixture prints a secret → appears as `[redacted]`); janitor removes orphans; RPCs reject non-deployer callers.

## 7. Acceptance
App containers cannot reach `postgres:5432`, `redpanda:9092`, `runtime-agent:9000` (network test from inside a fixture container); all container settings in §3 verified by inspection test.
