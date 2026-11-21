# Launchpad Step −1 Environment Design

## Intent

Prepare the empty `launch-pad` workspace as the control plane for building Launchpad with agents, before any product milestone is implemented. The specification pack is the source of truth. Step −1 ends with a reproducible local toolchain, a spec-aligned `launchpad-meta` repository, a separately seeded `launchpad-agent-kit` repository, and explicit preflight checks showing what is ready and what still requires the owner.

This setup is for Tejas, who will operate the project as its single owner. It exists to make later agent work repeatable, reviewable, and unable to silently diverge from the specification.

## Current State

- The repository contains one initial commit and an untracked `launchpad-spec-pack/` directory.
- Both `main` and `master` point at the initial commit; the active branch is `master`.
- No Git remote is configured.
- Installed locally: Git, GitHub CLI, Claude Code, Go 1.25.2, Node 22, npm 10, Python 3.11, Docker CLI 28, jq 1.7.1, Buf 1.47.2, and Make.
- Required but absent or mismatched: Go 1.27, Node 26, Python 3.14, Rust stable/edition 2024 support, and `uv`.
- GitHub CLI authentication for `Tejas021` is invalid.
- The Docker daemon cannot currently be reached from this workspace.
- The GitHub organization, GitHub Apps, organization secrets/variables, DNS, cloud account, and production server are owner-controlled prerequisites and cannot be fabricated by agents.

## Goals

1. Make this repository the spec-defined `launchpad-meta` control repository.
2. Seed `launchpad-agent-kit` as a distinct sibling Git repository, preserving the polyrepo architecture from the beginning.
3. Pin and document the local language/tool versions used by later agents.
4. Provide idempotent bootstrap and preflight commands that report facts without claiming unavailable external systems are ready.
5. Establish concise root instructions for Codex, Claude Code, and other agents.
6. Validate the imported specifications, contracts, starter kit, shell scripts, JSON, YAML, and risk-classifier tests.
7. Produce a clear owner handoff for GitHub, credentials, Docker, DNS, and server work.

## Non-goals

- Implementing A0 or any product milestone.
- Creating production infrastructure, DNS records, cloud accounts, secrets, or GitHub Apps on the owner's behalf.
- Creating the service repositories before A0-08.
- Changing product architecture, contracts, service behavior, or the delivery backlog.
- Pretending local macOS validation is equivalent to the required Ubuntu arm64 CI and production validation.
- Enabling autonomous merging; the system starts at autonomy phase P0.

Step −1 intentionally performs the mechanical import and seed work named in A0-01 and A0-02, but it does not declare those issues complete. The A0 planner must treat the imported pack and seeded starter as existing inputs, then make A0-01/A0-02 verify, refine, and provide acceptance evidence for them rather than duplicating files. The normative delivery plan remains unchanged; this boundary is recorded in the Step −1 handoff and referenced by the A0 plan.

## Constraints

- Specification precedence remains: `contracts/` > service spec > `specs/03-conventions.md` > other specs.
- `launchpad-meta` and `launchpad-agent-kit` are agent configuration and remain human-merge-only.
- The current workspace is writable, but its sibling directory is outside the declared writable root; creating the sibling repository requires an explicit permission escalation.
- Installing or upgrading host-level tools changes the user's machine and may require network access and explicit approval.
- Secrets must never be requested in chat, printed, committed, or stored in repository files.
- The checked-in setup must work without secrets; external readiness is represented as a failed/skipped preflight item with remediation text.

## Approaches Considered

### 1. Strict polyrepo bootstrap — selected

Promote this repository to `launchpad-meta` and seed `../launchpad-agent-kit` as its own Git repository. This matches the specification, keeps permissions and releases independent, and avoids a later history/path migration. It requires permission to write one sibling directory and leaves remote creation to the owner until GitHub authentication and organization details are available.

### 2. Temporary bootstrap monorepo

Place `launchpad-meta/` and `launchpad-agent-kit/` beneath this repository and split them later. It is easy to create inside the current sandbox, but workflow paths, plugin marketplace references, CODEOWNERS, Git history, and local commands would all need migration. This is rejected because the spec already commits to polyrepo operation.

### 3. Local environment only

Pin tools and add preflight scripts without restructuring repositories. It avoids external prerequisites but leaves Step −1 incomplete and makes A0 begin with repository-topology work. This is rejected because topology is a foundational environment decision, not product implementation.

## Selected Design

### A. `launchpad-meta` repository layout

The contents of `launchpad-spec-pack/` move to the repository root so the result matches `specs/12-agentic-system.md` §20 and `bootstrap/launchpad-meta/CLAUDE.md`:

```text
launchpad-meta/
├── README.md
├── CLAUDE.md
├── AGENTS.md
├── specs/
├── contracts/
├── bootstrap/
├── docs/{adr,incidents,security,runbooks,superpowers/specs}/
├── plans/
├── perf/
├── metrics/
├── setup/human-setup-status.md
├── scripts/{bootstrap-local.sh,preflight.sh,validate-spec-pack.sh}
├── scripts/placeholder-allowlist.txt
├── .mise.toml
├── .editorconfig
├── .gitattributes
├── .gitignore
└── Makefile
```

The import is a move, not a lossy rewrite. File counts and hashes are checked before and after. `.DS_Store` is ignored and removed from the working tree. The active development branch becomes `main`; the existing `master` reference is preserved unless the owner later chooses to delete it.

`CLAUDE.md` is copied from the supplied bootstrap file. `AGENTS.md` is a portable, short companion containing the same repository map, commands, precedence, protected-path policy, evidence rules, and secret-handling rules. Neither file duplicates long skill instructions.

### B. Local toolchain management

Use `mise` as the declarative local version manager because the project spans Go, Node, Python, Rust, and utility CLIs. `.mise.toml` pins the spec-required language lines:

- Go 1.27.x
- Node 26.x
- Python 3.14.x
- Rust stable
- `uv` current stable

Buf and other utilities remain externally installed initially, but `preflight.sh` checks their presence and minimum/spec-compatible versions. Exact infrastructure image patches do not belong in the local toolchain file; A0/M0 will pin them in their owning repositories.

`scripts/bootstrap-local.sh` is idempotent and conservative:

1. Detects macOS/Linux and required base commands.
2. Installs nothing unless invoked with an explicit `--install` flag.
3. With `--install`, installs `mise` through the platform's supported package manager, then runs `mise install`.
4. Never logs in to GitHub, starts Docker, writes secrets, creates cloud resources, or changes global Git configuration.
5. Finishes by running the preflight and printing actionable owner steps.

The repository remains usable by people who do not adopt `mise`: preflight validates active binaries, and the README documents equivalent manual version requirements.

### C. `launchpad-agent-kit` sibling repository

With explicit filesystem approval, seed `../launchpad-agent-kit` from `bootstrap/agent-kit/` and initialize it as an independent Git repository on `main`. Add only environment-level files that are necessary before A0: a root `AGENTS.md`, `.gitignore`, `.editorconfig`, `.gitattributes`, `.mise.toml` for Python/Node utilities used by tests/workflows, and a small Makefile exposing validation commands.

The supplied starter remains semantically unchanged in Step −1. Known placeholders such as `LP_ORG`, the incomplete conductor, and A0 follow-ups stay visible. Step −1 validates the existing risk tests and starter structure; A0 remains responsible for completing the plugin, workflows, agents, skills, templates, trigger tests, and acceptance drills.

No GitHub remote is created until the owner supplies the organization name and restores GitHub CLI authentication. The preflight reports this as `OWNER ACTION`, not as a setup failure.

### D. Validation and commands

The root Makefile exposes stable commands for humans and agents:

```text
make bootstrap        # non-mutating detection by default
make bootstrap-install
make preflight
make validate
make test-agent-kit   # runs the sibling risk-classifier tests when present
```

`validate-spec-pack.sh` checks:

- required files and directories from the pack index;
- JSON parsing for event schemas, plugin manifests, hook config, and review schema;
- JSON Schema metadata consistency for event title/filename/type catalog entries;
- duplicate or missing event catalog entries;
- protobuf formatting/lint when `buf` is available, otherwise an explicit skip;
- shell syntax for bootstrap scripts and hooks;
- executable bits for shell/Python entrypoints where applicable;
- unresolved placeholders, reported by category (allowed until owner setup/A0 versus unexpected);
- `python -m pytest` for `scripts/test_risk.py` using an isolated environment when `uv` is available.

`preflight.sh` emits a concise table with `PASS`, `FAIL`, `SKIP`, or `OWNER ACTION`. It checks:

- repository layout and active branch;
- tool versions;
- Docker client and daemon separately;
- GitHub CLI installation and authentication separately;
- absence of tracked secret-like files;
- presence of the sibling agent-kit;
- external values only by presence, never by printing values;
- human-setup checklist state without modifying it.

Preflight supports `--phase step-minus-one|a0|m0|m1` and `--strict`. Its result matrix is explicit:

| Check | Step −1 | A0 | M0 | M1 |
|---|---|---|---|---|
| Root meta layout, sibling agent-kit, Git, Bash, Make, jq, Claude Code | blocking local failure | blocking | blocking | blocking |
| Python capable of running risk tests, `uv`, risk tests | blocking local failure | blocking | blocking | blocking |
| Spec/JSON/shell validation | blocking local failure | blocking | blocking | blocking |
| Go 1.27, Node 26, Python 3.14, Rust stable | blocking in `--strict`; otherwise reported | informational | informational | blocking for the languages used by the selected M1 issue |
| Buf | blocking in `--strict`; otherwise reported | informational | informational | blocking |
| Docker daemon | blocking in `--strict`; otherwise reported | required only for A0 acceptance drills that use containers | blocking | blocking |
| Valid `gh` auth, GitHub org, meta/agent-kit remotes | `OWNER ACTION` | blocking owner action | blocking | blocking |
| GitHub Apps, org secrets/variables, Project fields | `OWNER ACTION` | blocking owner action before automated A0 workflows/drills | blocking | blocking |
| Domain/cloud/DNS/server | deferred owner action | deferred | blocking at the issue specified by `16-human-setup.md` | unchanged |

Exit codes are `0` when the requested phase is ready, `1` for a local blocking failure, and `2` when local checks pass but owner actions block the requested phase. Plain `make preflight` uses `--phase step-minus-one`; `make preflight-a0` checks A0 readiness. `--strict` additionally requires every pinned language tool, Buf, and the Docker daemon so a developer can prove the complete workstation is ready even before those tools become milestone blockers.

The committed source checklist in `specs/16-human-setup.md` is never edited to represent environment state. Step −1 creates `setup/human-setup-status.md` as the spec-requested working copy, with the same stable item identifiers and no secret values. The owner checks items there. Preflight parses only checkbox state, reports incomplete items by identifier and milestone, and never infers completion from credentials or environment variables.

Placeholder validation is deterministic. `scripts/placeholder-allowlist.txt` contains path glob, literal token/pattern, reason, and expiry milestone for every intentional placeholder category, including `LP_ORG`, `<org>`, `<domain>`, `<service>`, template-only angle-bracket fields, and documented A0 scaffolding. Validation fails on any unresolved placeholder not matched by the allowlist, reports allowed matches separately, and fails when an allowlist entry remains beyond its expiry milestone in the relevant repository. The initial allowlist is generated from and reviewed against the imported pack, not from a blanket angle-bracket regex exemption.

### E. Documentation and owner handoff

The root README remains the specification index and gains a short environment section linking to a dedicated `docs/runbooks/local-development.md`. That runbook documents:

- one-command local setup;
- manual toolchain alternatives;
- how the two repositories should be cloned side by side;
- Docker Desktop/daemon requirement;
- GitHub CLI reauthentication without exposing tokens;
- how to run preflight and interpret statuses;
- exactly which `specs/16-human-setup.md` items block A0, M0, or later milestones.
- how Step −1 work changes A0-01/A0-02 from file creation into verification/refinement without changing the normative delivery plan.

No secret values or account identifiers are committed. A `.env.example` is not added because the platform convention requires secret files and organization secrets rather than a shared dotenv workflow.

## Safety and Rollback

- Before moving the spec pack, record its file list and hashes; validate the same content at the root afterward.
- Do not overwrite an existing sibling `launchpad-agent-kit`; stop and report if it exists and is non-empty.
- Do not alter GitHub repositories, organization settings, secrets, DNS, or cloud resources during Step −1.
- Host tool installation occurs only after explicit user approval and through the documented bootstrap flag.
- Every generated repository file is reviewable in Git before commit.
- If the root import must be undone before commit, move the same files back using the recorded manifest; do not use destructive Git resets.

## Verification Criteria

Step −1 is complete when:

1. This repository has the `launchpad-meta` root layout and no duplicate nested spec pack.
2. `../launchpad-agent-kit` exists as an independent Git repository seeded from the supplied starter.
3. `make validate` passes, with optional-tool skips explicitly listed.
4. The agent-kit risk-classifier tests pass.
5. `make preflight` accurately reports local readiness and owner actions.
6. Required tool versions are active, or installation is the only remaining action awaiting explicit host-change approval.
7. Git contains no `.DS_Store`, credentials, private keys, dotenv files, or generated secret material.
8. Root `CLAUDE.md` and `AGENTS.md` agree on commands, repository purpose, precedence, and protected paths.
9. The owner handoff maps every unresolved external prerequisite to `specs/16-human-setup.md` and its milestone deadline.
10. No A0 or product implementation has been performed.

## Builder Decisions Left Open

The implementer may choose the exact shell function organization, output formatting, and validation helper implementation, provided scripts remain POSIX-friendly where practical, work under the repository's declared shell, are tested, and preserve the behaviors above.
