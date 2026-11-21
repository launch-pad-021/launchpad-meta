# Service: builder

**Repo:** `launchpad-builder` · **Language:** Go 1.27 · **Ports:** 9000 / 8080 · **Owns:** no database · **Risk:** high (sandboxing, registry, BuildKit connection)

## 1. Purpose
Turns a commit into an image in the local registry, streaming build logs.

## 2. Inputs / outputs
- Consumes `build.requested.v1` (group `builder`, **concurrency 1** per instance).
- Produces `build.started.v1`, `build.log.v1` (batched), `build.completed.v1`, `build.failed.v1` (topic `lp.builds` / `lp.build-logs`, key `app_id`).
- gRPC `CancelBuild(deployment_id)` → cancels the context of the running build; idempotent.

## 3. Pipeline
1. Emit `build.started`.
2. `scm.GetCloneCredentials(repo)` → `git clone --depth 1 --no-tags` then `git fetch --depth 1 origin <sha>` + `checkout <sha>` into `/work/<deployment_id>` (tmpfs-backed volume, size limit 2 GB). Credentials passed via `GIT_ASKPASS` helper, never in the URL/logs.
3. Detect in `root_dir`: if `build_strategy=dockerfile` or (`auto` and `Dockerfile` exists) → Dockerfile build; else Railpack.
4. **Railpack:** `railpack prepare <dir> --plan-out plan.json --info-out info.json` (no secrets; env only `RAILPACK_*` if the repo's `railpack.json` asks). Read `info.json` for detected provider and start command.
5. **Build via BuildKit** (`moby/buildkit/client`, address `tcp://buildkitd:1234` with mTLS):
   - Railpack: frontend `gateway.v0`, `source=ghcr.io/railwayapp/railpack-frontend:<pinned>`, local `context` = app dir, local `dockerfile` = dir containing `plan.json`, build-arg `cache-key=<app_id>`.
   - Dockerfile: frontend `dockerfile.v0`.
   - Output: `type=image,name=registry:5000/launchpad/<app_name>:<sha>,push=true` with `registry.insecure=true` (internal network).
   - Platform: native (`linux/arm64` on the server).
   - Progress: stream `SolveStatus` vertex logs → log lines.
6. Effective config: start from `build.requested` app settings; if a `launchpad.toml` exists at root_dir, apply allowed overrides (`port`, `health_path`, `[resources] cpu, memory_mb` within project limits) — report in `build.completed.effective_config`.
7. Emit `build.completed` {image_ref, image_digest, duration_ms, provider, effective_config}.
8. Cleanup work dir always.

Failure → `build.failed` {reason: `timeout|cancelled|clone_error|detect_error|build_error|push_error|internal`, message (≤ 2 KB, no secrets)}.

## 4. Logs
- Each line: `{seq, ts, stream: system|stdout|stderr, line}`; `seq` monotonic per deployment starting at 1; lines > 8 KB truncated.
- Batch publish every 250 ms or 100 lines; final flush before `build.completed/failed`.
- Redact any string matching the clone token or `ghs_`/`github_pat_` patterns.

## 5. Limits
Timeout 15 min (`LP_BUILD_TIMEOUT`); one build at a time; BuildKit cache GC keeps 20 GB; repo size limit 1 GB (abort clone).

## 6. Registry hygiene
Nightly job: for each app keep last 10 tags + tags referenced by non-terminal/live deployments (asks `deployer.ListDeployments`); delete others via registry API; trigger `registry garbage-collect` via infra cron.

## 7. Config
`LP_BUILDKIT_ADDR`, `LP_BUILDKIT_CA_FILE`, `LP_BUILDKIT_CERT_FILE`, `LP_BUILDKIT_KEY_FILE`, `LP_REGISTRY=registry:5000`, `LP_RAILPACK_FRONTEND=ghcr.io/railwayapp/railpack-frontend:<pin>`, `LP_BUILD_TIMEOUT=15m`, `LP_SCM_ADDR` + common.

## 8. Tests
Detection table (Dockerfile vs railpack per fixture); clone credential never logged; log batching/seq; cancel mid-build (integration with real buildkitd in Testcontainers on arm64 runner); timeout; push to a test registry; effective config overrides and limit enforcement; cleanup on failure.

## 9. Acceptance
`next-basic`, `node-express`, `static-site`, `go-api`, `python-fastapi`, `dockerfile-custom` fixtures all build and push; build logs stream within 1 s; cancel stops the build within 5 s.
