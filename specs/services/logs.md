# Service: logs

**Repo:** `launchpad-logs` · **Language:** Go 1.27 · **Ports:** 9000 / 8080 · **Owns:** ClickHouse `logs.lines` (`05-data.md` §7.2) · **Risk:** medium

## 1. Purpose
Stores and serves build and runtime logs, including live tailing.

## 2. Ingestion
- Consumes `build.log.v1` (topic `lp.build-logs`) and `runtime.log.v1` (topic `lp.runtime`), group `logs`.
- Batch insert into ClickHouse (flush at 2,000 lines or 500 ms) using async-insert-off, native protocol; commit offsets after successful insert.
- Runtime logs get `seq` assigned here per (deployment_id, source) from an in-memory counter seeded from `max(seq)` on first use.
- After insert, push lines to the in-memory **tail hub** (per deployment_id+source ring buffer of last 2,000 lines + subscriber channels).

## 3. gRPC API (`launchpad.logs.v1.LogsService`)
| RPC | Behavior |
|---|---|
| `GetLogs(deployment_id, source, after_seq, limit≤1000)` | Ordered by seq |
| `TailLogs(deployment_id, source, after_seq)` → stream `LogLine` | Replay from ClickHouse (`seq > after_seq`) then switch to the hub; de-dup by seq at the seam; heartbeat every 15 s; the stream ends when the client disconnects (the gateway closes build-log SSE streams when it sees a terminal `deployment.status_changed`) or after 10 min without new lines |
| `SearchLogs(app_id, query, from, to, limit≤500)` | `hasToken(line, ...)` for single-word tokens else `positionCaseInsensitive`; max range 7 days; query length ≤ 200 |

## 4. Config
`LP_CH_ADDR`, `LP_CH_USER=logs_rw`, `LP_CH_PASSWORD_FILE` + common.

## 5. Tests
Batching and offset commit after insert; replay+live seam without gaps/duplicates; slow subscriber does not block ingestion (drop + signal `resync` to client); search limits; restart resumes seq correctly.

## 6. Acceptance
Build logs visible in the dashboard < 1 s after emission; `logs` restart during a build loses no lines (E2E 8).
