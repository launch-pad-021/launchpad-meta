# App: cli (`launch`)

**Repo:** `launchpad-cli` · **Language:** Go 1.27 + Cobra · **Talks only to:** gateway · **Distribution:** goreleaser → GitHub Releases (darwin/linux/windows, arm64/amd64) · **Risk:** low

## 1. Commands
```
launch login [--api https://api.launchpad.<domain>]   # prompts for a token created in the dashboard; stores in OS keychain (fallback ~/.config/launchpad/config.json 0600)
launch whoami
launch apps                                          # table: name, prod URL, status, last deploy
launch init                                          # from git remote: create app, write launchpad.toml
launch deploy [--app X] [--branch B] [--wait]        # --wait streams build logs, exits non-zero on failure
launch status [<deployment-id>]
launch logs [-f] [--build <deployment-id>] [--since 1h]
launch env ls | set KEY=VAL [--scope production|preview|all] | rm KEY [--scope]
launch rollback [<deployment-id>]                    # default: previous production deploy
launch open [--preview <branch>]
launch stats [--range 24h]                           # visitors, top pages, p75 vitals of live deploy
```
App resolution: `--app` flag → `launchpad.toml` `app = "..."` → git remote match via `/v1/apps`.

## 2. `launchpad.toml` (optional, in app repo root_dir)
```toml
app = "myapp"
port = 3000
health_path = "/api/health"
[resources]
cpu = 0.5
memory_mb = 512
```
Builder applies `port`, `health_path`, `[resources]` within project limits (`services/builder.md` §3, step 6).

## 3. Behavior
Human-readable output by default; `--json` on every command; exit codes: 0 ok, 1 error, 2 usage, 3 deploy failed, 4 auth. Respects `NO_COLOR`. Uses SSE for `--wait`/`-f` with reconnect.

## 4. Tests
Golden output tests; HTTP mocked gateway; keychain fallback; deploy --wait exit codes.
