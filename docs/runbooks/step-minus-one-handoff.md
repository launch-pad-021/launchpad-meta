# Step −1 handoff

**Date:** 21 November 2026  
**Branch:** `agent/step-minus-one-environment`

## Delivered

- Promoted the supplied specification pack to the `launchpad-meta` repository root.
- Preserved the externally revised canonical pack and verified every imported file by SHA-256.
- Added concise `CLAUDE.md` and `AGENTS.md`, mise tool requests, repository hygiene, validation, preflight, bootstrap automation, and tests.
- Seeded an independent `launchpad-agent-kit` repository from `bootstrap/agent-kit` without completing A0 functionality.
- Added a non-secret copy of the human setup checklist and phase/issue readiness gates.

## A0 boundary

Step −1 performs the mechanical import and starter seed named in A0-01/A0-02. Those delivery-plan items remain open: A0 must verify/refine the assets, complete the agent system, and attach acceptance evidence rather than duplicate the import.

## Verification record

The final one-pass verification on 21 November 2026 recorded:

| Command | Exit | Outcome |
|---|---:|---|
| `make test` | 0 | Environment unit suite passed |
| `make validate` | 0 | Specification, JSON, shell, catalog, executable, and placeholder checks passed |
| `make test-agent-kit` | 0 | All 16 risk-classifier tests passed |
| `make preflight` | 0 | Step −1 local readiness passed |
| `make preflight-a0` | 2 | Local checks passed; A0 owner actions remain |
| `scripts/bootstrap-local.sh --install` | 0 | Strict preflight passed with Docker running |
| `git diff --check` in both repositories | 0 | No whitespace errors |
| `gitleaks dir --no-banner --redact .` in both repositories | 0 | No leaks found |

Resolved tools were mise 2026.11.11, Go 1.27.4, Node 26.13.1, Python 3.14.10, Rust 1.100.0 stable, uv 0.13.9, Buf 1.47.2, and Docker client/server 28.1.1. The only skipped local values were the organization, owner login, and base domain; they are intentionally unset until the owner supplies them.

The meta branch contains the Step −1 series `fa816e7` through `e62275b` plus the final environment commit. The sibling repository is `/Users/tejas.ko/orca/projects/launchpad-agent-kit` at `0fac467`. Neither repository has a remote configured. Expected unresolved external work is reported as `OWNER ACTION`; no checklist item is marked complete without owner confirmation.

## Owner actions before automated A0 workflows

Complete the A0 section of `setup/human-setup-status.md`: GitHub organization and visibility, emergency admin, four GitHub Apps, organization secrets/variables, both control repositories/remotes, Project fields, Telegram bot, and the agent provider credential.

No production secrets, server access, DNS mutation, or cloud mutation is performed by Step −1.
