# Local development environment

This repository is `launchpad-meta`; `launchpad-agent-kit` is a separate sibling repository. Product service repositories are created later by A0-08.

## Bootstrap

Inspect the workstation without changing it:

```bash
make bootstrap
```

Install mise through Homebrew on macOS, resolve the requested Go 1.27, Node 26, Python 3.14, Rust stable and uv versions, write `mise.lock`, then run strict preflight:

```bash
make bootstrap-install
```

The installer never uses `curl | sh`, logs in to GitHub, starts Docker, writes secrets, or changes global Git configuration. If you manage tools another way, activate versions matching `.mise.toml` and run `make preflight-strict`. Prefix a command with `mise exec --` when shell activation is unavailable.

The mise configuration follows its current [configuration](https://mise.jdx.dev/configuration), [core tools](https://mise.jdx.dev/core-tools.html), and [version request](https://mise.jdx.dev/dev-tools/versions) documentation, checked 21 November 2026.

## Repository layout

Keep the control repositories beside each other:

```text
workspace/launchpad-meta/
workspace/launchpad-agent-kit/
```

Seed the agent kit safely from the starter in this repository:

```bash
scripts/bootstrap-local.sh --seed-agent-kit ../launchpad-agent-kit
```

The command refuses an unrecognized non-empty destination and never overwrites an already seeded repository.

## Commands

| Command | Purpose |
|---|---|
| `make bootstrap` | Detect the platform and run non-mutating Step −1 preflight |
| `make bootstrap-install` | Install/resolve the pinned local toolchain, then strict preflight |
| `make validate` | Validate specs, JSON, event catalog, placeholders, shell, and optional Buf configuration |
| `make test` | Run environment unit tests |
| `make test-agent-kit` | Run the sibling risk-classifier tests |
| `make preflight` | Check Step −1 local readiness |
| `make preflight-a0` | Check A0 readiness, including required owner actions |
| `make preflight-strict` | Require every pinned tool, Buf, and a reachable Docker daemon |

Preflight status meanings:

- `PASS`: observed and ready.
- `FAIL`: local blocking problem; exit code 1.
- `OWNER ACTION`: account or external configuration remains. It is informational for Step −1 and blocking with exit code 2 when due for the requested phase.
- `SKIP`: optional for the requested phase; strict mode may make it blocking.

Progress for external setup is recorded only in `setup/human-setup-status.md`. Never put account values, tokens, keys, domains, or secrets in that file.

## Docker and GitHub

The Docker CLI and daemon are checked separately. Start Docker Desktop (or another compatible daemon) before container drills; the bootstrap script does not start it.

If GitHub authentication is unavailable, run `gh auth login --hostname github.com` interactively. Never paste its token into chat, logs, issues, or repository files. A0 also needs the organization, Apps, secrets, variables, control-repository remotes, and Project fields listed in the human setup status.

## Milestone boundaries

- Step −1 imports the pack and seeds the starter. A0-01/A0-02 verify, refine, and provide acceptance evidence for those assets; they do not recreate them.
- A0 automation starts only after its GitHub owner actions are complete.
- M0 account/server/DNS items become blocking at the issue shown in the status file.
- M1 requires Buf, Docker, and the language toolchain used by the selected issue.
