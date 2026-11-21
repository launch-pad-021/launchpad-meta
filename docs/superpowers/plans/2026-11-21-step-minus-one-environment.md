# Launchpad Step −1 Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the empty workspace into a validated `launchpad-meta` control repository, seed a separate sibling `launchpad-agent-kit`, and provide reproducible local bootstrap and phase-aware readiness checks without implementing A0.

**Architecture:** Move the supplied specification pack to the control repository root, then add small Bash entrypoints backed by Python-standard-library validation and preflight modules. Keep the agent kit as an independent sibling Git repository seeded from the supplied starter. External accounts and secrets remain owner actions represented by an explicit status checklist and preflight exit codes.

**Tech Stack:** Bash 3.2+ compatibility, Python 3.11+ standard library for environment tooling, `unittest`, Make, mise, Git, jq, Buf, Docker CLI, GitHub CLI, Claude Code.

**Spec:** `docs/superpowers/specs/2026-11-21-step-minus-one-environment-design.md`

## Global Constraints

- Do not implement A0 or product milestones; Step −1 only imports, seeds, validates, and documents their inputs.
- Preserve specification precedence: `contracts/` > service spec > `specs/03-conventions.md` > other specs.
- Keep `launchpad-meta` and `launchpad-agent-kit` as separate Git repositories; never nest one Git repository inside the other.
- Keep `launchpad-meta` and `launchpad-agent-kit` human-merge-only agent configuration.
- Never request, print, write, or commit secret values, private keys, tokens, `.env` files, or generated credentials.
- Do not mutate GitHub, DNS, cloud, or production-server state in Step −1.
- Use tool requests `go = "1.27"`, `node = "26"`, `python = "3.14"`, `rust = "stable"`, and `uv = "latest"`; add a mise lockfile after installation resolves concrete versions.
- Treat Docker client availability and Docker daemon reachability as separate checks.
- Use preflight exit code `0` for ready, `1` for local blocking failures, and `2` for owner actions blocking the requested phase.
- Preserve the existing `master` ref; make `main` the active working branch without deleting references.
- Use `apply_patch` for authored files; use mechanical move/copy commands only for the supplied pack and sibling seed, with manifests and checksums before and after.

## Review Focus

- A partially moved or interrupted specification import must be detected without losing the original pack; Task 1 tests required files and validates before cleanup.
- An existing non-empty sibling `launchpad-agent-kit` must never be overwritten; Task 6 tests refusal and idempotent recognition.
- Fake or unavailable executables on `PATH` must produce deterministic preflight results without leaking environment values; Task 4 uses controlled command fixtures.
- Legitimate template placeholders must pass while an unexpected placeholder fails with its file and line; Task 3 tests both cases.
- Local checks passing while A0 owner prerequisites are incomplete must return exit code `2`, not a false-ready `0`; Task 4 pins the phase matrix.

---

## File Map

### `launchpad-meta`

- `README.md`: specification index plus short Step −1 entrypoint.
- `CLAUDE.md`: supplied control-repository instructions.
- `AGENTS.md`: portable control-repository instructions aligned with `CLAUDE.md`.
- `.mise.toml`, `mise.lock`: requested and resolved local tool versions.
- `.editorconfig`, `.gitattributes`, `.gitignore`: cross-platform and secret/noise hygiene.
- `Makefile`: stable human/agent command surface.
- `scripts/validate-spec-pack.sh`: Bash entrypoint for validation.
- `scripts/validate_spec_pack.py`: required-file, JSON, catalog, placeholder, shell, and optional Buf validation.
- `scripts/placeholder-allowlist.txt`: reviewed, expiring intentional-placeholder rules.
- `scripts/preflight.sh`: Bash entrypoint for phase-aware readiness.
- `scripts/preflight.py`: phase matrix, command probes, checklist parser, and exit-code calculation.
- `scripts/bootstrap-local.sh`: conservative detection/install orchestrator; mutates host tools only with `--install`.
- `setup/human-setup-status.md`: non-secret working copy of owner actions with stable IDs and milestone tags.
- `docs/runbooks/local-development.md`: local setup and interpretation guide.
- `docs/runbooks/step-minus-one-handoff.md`: completion record and A0-01/A0-02 boundary.
- `tests/test_repository_layout.py`: root import and agent-instruction assertions.
- `tests/test_validate_spec_pack.py`: validator behavior.
- `tests/test_preflight.py`: phase/status/exit-code behavior.
- `tests/test_bootstrap_local.py`: bootstrap dry-run and install gating.
- `tests/test_agent_kit_seed.py`: sibling safety and structure.

### `launchpad-agent-kit` sibling

- Existing starter tree from `bootstrap/agent-kit/`: copied without semantic changes.
- `AGENTS.md`: portable repository scope and validation commands.
- `.mise.toml`, `.editorconfig`, `.gitattributes`, `.gitignore`: local environment metadata.
- `Makefile`: `validate` and `test` entrypoints.

---

### Task 1: Promote the specification pack to the `launchpad-meta` root

**Files:**
- Create: `tests/test_repository_layout.py`
- Move: `launchpad-spec-pack/README.md` → `README.md`
- Move: `launchpad-spec-pack/specs/` → `specs/`
- Move: `launchpad-spec-pack/contracts/` → `contracts/`
- Move: `launchpad-spec-pack/bootstrap/` → `bootstrap/`
- Preserve: `docs/superpowers/specs/2026-11-21-step-minus-one-environment-design.md`
- Preserve: `docs/superpowers/plans/2026-11-21-step-minus-one-environment.md`

**Interfaces:**
- Consumes: the untracked `launchpad-spec-pack/` supplied by the owner.
- Produces: root paths `README.md`, `specs/`, `contracts/`, and `bootstrap/` used by every later task.

- [ ] **Step 1: Write the failing repository-layout test**

Create `tests/test_repository_layout.py` with `unittest.TestCase` methods:

```python
def test_required_spec_pack_paths_are_at_repository_root(self):
    for path in (
        "README.md",
        "specs/00-product.md",
        "specs/12-agentic-system.md",
        "contracts/events/envelope.schema.json",
        "contracts/proto/launchpad/common/v1/common.proto",
        "bootstrap/KICKOFF.md",
        "bootstrap/agent-kit/README.md",
    ):
        self.assertTrue((ROOT / path).is_file(), path)

def test_nested_spec_pack_no_longer_exists(self):
    self.assertFalse((ROOT / "launchpad-spec-pack").exists())
```

- [ ] **Step 2: Run the layout test and confirm the nested layout fails**

Run: `python3 -m unittest tests.test_repository_layout -v`

Expected: `test_required_spec_pack_paths_are_at_repository_root` fails because root `README.md` and `specs/` do not exist.

- [ ] **Step 3: Record a source manifest and hashes outside the repository**

Run from the repository root:

```bash
find launchpad-spec-pack -type f ! -name '.DS_Store' -print0 | sort -z | xargs -0 shasum -a 256 > /tmp/launchpad-spec-pack.before.sha256
find launchpad-spec-pack -type f ! -name '.DS_Store' | sed 's#^launchpad-spec-pack/##' | sort > /tmp/launchpad-spec-pack.before.files
```

Expected: the manifest contains the complete pack and no `.DS_Store`.

- [ ] **Step 4: Move the supplied pack directories and README to the root**

Move only `README.md`, `specs`, `contracts`, and `bootstrap`. Preserve the existing `docs/` tree. Move `.DS_Store` files to a task-specific temporary directory rather than deleting them. Remove `launchpad-spec-pack/` only after it is empty.

- [ ] **Step 5: Verify the imported files match the source hashes**

Generate `/tmp/launchpad-spec-pack.after.sha256` with paths normalized to match the `before` manifest, then run `diff -u` on both file lists and hash lists.

Expected: no differences.

- [ ] **Step 6: Run the layout test**

Run: `python3 -m unittest tests.test_repository_layout -v`

Expected: both tests pass.

- [ ] **Step 7: Make `main` active without deleting `master`**

Run read-only `git worktree list` first. If `main` is not checked out elsewhere, run `git switch main`; otherwise stop and report the branch conflict rather than forcing it.

Expected: `git branch --show-current` prints `main`; `git show-ref --verify refs/heads/master` still succeeds.

- [ ] **Step 8: Commit the root import**

```bash
git add README.md specs contracts bootstrap tests/test_repository_layout.py docs/superpowers
git commit -m "docs: import launchpad specification pack"
```

### Task 2: Add root agent instructions and declarative toolchain metadata

**Files:**
- Create: `CLAUDE.md`
- Create: `AGENTS.md`
- Create: `.mise.toml`
- Create: `.editorconfig`
- Create: `.gitattributes`
- Create: `.gitignore`
- Create: `Makefile`
- Modify: `tests/test_repository_layout.py`

**Interfaces:**
- Consumes: root pack from Task 1 and `bootstrap/launchpad-meta/CLAUDE.md`.
- Produces: standard commands `make bootstrap`, `make bootstrap-install`, `make preflight`, `make preflight-a0`, `make validate`, `make test`, and `make test-agent-kit`.

- [ ] **Step 1: Extend the failing layout test for instructions, commands, and tool pins**

Add assertions that:

- `CLAUDE.md` exactly matches `bootstrap/launchpad-meta/CLAUDE.md` at import time.
- `AGENTS.md` contains `launchpad-meta`, the precedence string, `make validate`, `make preflight`, protected agent-config paths, and the no-secrets rule.
- `.mise.toml` parses with `tomllib` and has `tools == {"go":"1.27", "node":"26", "python":"3.14", "rust":"stable", "uv":"latest"}`.
- `.gitignore` includes `.DS_Store`, `.env`, `.env.*`, `*.pem`, `*.key`, `.venv/`, `mise.local.toml`, and excludes an explicit `!.env.example` rule because no dotenv example is allowed.
- `Makefile` contains all seven public targets listed in the Interfaces block.

- [ ] **Step 2: Run the focused test and verify it fails on missing files**

Run: `python3 -m unittest tests.test_repository_layout -v`

Expected: existing root-layout tests pass; new metadata tests fail.

- [ ] **Step 3: Copy the supplied `CLAUDE.md` and author the portable `AGENTS.md`**

Keep both files under 150 lines. `AGENTS.md` must define repository purpose, map, commands, source precedence, read-before-edit rules, protected paths, untrusted-data policy, evidence rules, and secret rules without copying long skills.

- [ ] **Step 4: Add `.mise.toml` with verified current mise syntax**

Use:

```toml
[tools]
go = "1.27"
node = "26"
python = "3.14"
rust = "stable"
uv = "latest"
```

Do not create `mise.lock` until `mise install` has resolved concrete versions. This syntax was checked against the official mise core-tools, Go, Python, and configuration documentation on 2026-11-21.

- [ ] **Step 5: Add repository hygiene files**

Use UTF-8, LF, final newlines, two-space YAML/JSON indentation, four-space Python indentation, and tabs for Make recipes. Mark `*.sh text eol=lf`; do not mark authored scripts executable until their shebang and syntax tests exist.

- [ ] **Step 6: Add the Makefile command surface**

Targets call repository scripts only:

- `bootstrap`: `scripts/bootstrap-local.sh`
- `bootstrap-install`: `scripts/bootstrap-local.sh --install`
- `preflight`: `scripts/preflight.sh --phase step-minus-one`
- `preflight-a0`: `scripts/preflight.sh --phase a0`
- `validate`: `scripts/validate-spec-pack.sh`
- `test`: `python3 -m unittest discover -s tests -v`
- `test-agent-kit`: run `uv run --with pytest pytest -q ../launchpad-agent-kit/scripts/test_risk.py` after checking the sibling exists.

- [ ] **Step 7: Run the metadata tests**

Run: `python3 -m unittest tests.test_repository_layout -v`

Expected: all tests pass.

- [ ] **Step 8: Commit the repository baseline**

```bash
git add CLAUDE.md AGENTS.md .mise.toml .editorconfig .gitattributes .gitignore Makefile tests/test_repository_layout.py
git commit -m "chore: establish launchpad meta environment"
```

### Task 3: Build deterministic specification and placeholder validation

**Files:**
- Create: `scripts/validate-spec-pack.sh`
- Create: `scripts/validate_spec_pack.py`
- Create: `scripts/placeholder-allowlist.txt`
- Create: `tests/test_validate_spec_pack.py`

**Interfaces:**
- Consumes: root spec pack and tab-separated allowlist rows.
- Produces: `scripts.validate_spec_pack.validate(root: Path, milestone: str) -> list[Finding]` and CLI exit `0` when no error findings exist, otherwise `1`.

Define:

```python
@dataclass(frozen=True)
class AllowRule:
    path_glob: str
    pattern: str
    reason: str
    expires: str

@dataclass(frozen=True)
class Finding:
    level: Literal["error", "warning", "allowed", "skip"]
    check: str
    path: str
    detail: str

def load_allowlist(path: Path) -> list[AllowRule]: ...
def find_placeholders(root: Path, rules: Sequence[AllowRule], milestone: str) -> list[Finding]: ...
def validate(root: Path, milestone: str = "step-minus-one") -> list[Finding]: ...
```

- [ ] **Step 1: Write failing validator unit tests**

Use `tempfile.TemporaryDirectory` fixtures. Cover:

- required root file missing → error;
- malformed JSON → error with relative path;
- event schema filename/title/catalog mismatch → error;
- intentional `<org>` in an allowlisted template → `allowed`;
- `UNEXPECTED_PLACEHOLDER` outside allowlist → error with line number;
- expired rule (`expires=A0`, requested milestone `M0`) → error;
- invalid allowlist row (not four tab-separated fields) → error;
- shell syntax error → error;
- absent Buf → `skip`, not success prose.

- [ ] **Step 2: Run tests and verify the module is missing**

Run: `python3 -m unittest tests.test_validate_spec_pack -v`

Expected: import failure for `scripts.validate_spec_pack`.

- [ ] **Step 3: Implement allowlist parsing and placeholder matching**

Use `fnmatch` for path globs and compiled regular expressions for patterns. Reject malformed rows and invalid regular expressions. Milestone order is `step-minus-one < A0 < M0 < M1`; an allowlist rule is invalid after its expiry milestone.

- [ ] **Step 4: Add the reviewed initial allowlist**

Use four tab-separated fields with a comment header. Add narrow rules for the known starter/template paths and tokens: `LP_ORG`, `<org>`, `<domain>`, `<service>`, `<name>`, `<issue>`, `<milestone>`, language-choice template text, PR-template fields, and deliberate A0 TODO/scaffold comments. Do not allow a repository-wide catch-all placeholder rule.

- [ ] **Step 5: Implement required-file, JSON, catalog, shell, executable-bit, and optional-Buf checks**

Validate every `contracts/events/*.schema.json`, plugin/reviewer/hook JSON, event catalog one-to-one membership, `bash -n` for every `.sh`, expected executable bits for entrypoints, and `buf format --diff`/`buf lint` only when a root `buf.yaml` exists and `buf` is available. The imported contracts do not gain `buf.yaml` until M1, so report a precise skip.

- [ ] **Step 6: Add the Bash wrapper**

`validate-spec-pack.sh` resolves the repository root from its own path and executes `python3 scripts/validate_spec_pack.py "$@"`. It accepts `--milestone` and `--json`; human output groups errors, warnings, allowed placeholders, and skips.

- [ ] **Step 7: Run validator unit tests**

Run: `python3 -m unittest tests.test_validate_spec_pack -v`

Expected: all tests pass.

- [ ] **Step 8: Run validation against the real pack**

Run: `scripts/validate-spec-pack.sh --milestone step-minus-one`

Expected: exit `0`; every intentional placeholder is allowed explicitly; Buf may be skipped only because root `buf.yaml` does not yet exist.

- [ ] **Step 9: Commit the validator**

```bash
git add scripts/validate-spec-pack.sh scripts/validate_spec_pack.py scripts/placeholder-allowlist.txt tests/test_validate_spec_pack.py
git commit -m "test: validate launchpad specification pack"
```

### Task 4: Implement phase-aware preflight and human setup state

**Files:**
- Create: `scripts/preflight.sh`
- Create: `scripts/preflight.py`
- Create: `setup/human-setup-status.md`
- Create: `tests/test_preflight.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: repository root, sibling path, active environment, command probes, and checklist checkbox state.
- Produces: `scripts.preflight.run_checks(context: Context) -> list[CheckResult]`, `scripts.preflight.exit_code(results: Sequence[CheckResult]) -> int`, human/JSON output, and exit codes `0|1|2`.

Define:

```python
class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    OWNER_ACTION = "OWNER ACTION"

@dataclass(frozen=True)
class CheckResult:
    check_id: str
    status: Status
    phase: str
    detail: str
    blocking: bool

@dataclass(frozen=True)
class Context:
    root: Path
    sibling: Path
    phase: str
    strict: bool
    env: Mapping[str, str]
    command_runner: Callable[[Sequence[str]], CompletedProcess[str]]
```

- [ ] **Step 1: Write failing preflight tests**

Test with a fake `command_runner` and temporary repository/checklist:

- all Step −1 local checks pass, owner items pending → exit `0` with `OWNER ACTION` rows;
- local required command missing → exit `1`;
- `--phase a0` with local checks passing but `GITHUB-01` incomplete → exit `2`;
- GitHub auth failure never includes stderr/token text in `detail`;
- Docker client present and daemon unavailable → separate PASS and non-PASS rows;
- strict mode makes Go/Node/Python/Rust/uv/Buf/Docker daemon blocking;
- A0 non-strict reports language mismatch as nonblocking but blocks required owner actions;
- malformed or duplicate checklist IDs → local failure;
- `.env`, `.pem`, `.key`, or `.DS_Store` tracked by Git → local failure;
- output ordering is stable by check ID.

- [ ] **Step 2: Run tests and verify the preflight module is missing**

Run: `python3 -m unittest tests.test_preflight -v`

Expected: import failure for `scripts.preflight`.

- [ ] **Step 3: Create the non-secret human setup status copy**

Create stable identifiers grouped by milestone, for example `ACCOUNT-01`, `GITHUB-01`, `GITHUB-APPS-01`, `SERVER-01`, `DNS-01`. Copy the intent of every checkbox in `specs/16-human-setup.md` without copying or adding values. Add columns/labels identifying the first blocking phase.

- [ ] **Step 4: Implement local probes and redaction**

Probe versions using argument arrays, never `shell=True`. Parse only version lines. For GitHub auth and Docker daemon, keep return status and replace all stderr/stdout with fixed safe details such as `authentication required` or `daemon unavailable`; do not echo tool output.

- [ ] **Step 5: Implement the phase matrix and exit-code calculation**

Encode the exact matrix from the approved design. Local blocking failure wins (`1`); otherwise a blocking owner action returns `2`; otherwise `0`. `SKIP` is nonblocking only when the phase matrix marks the capability optional.

- [ ] **Step 6: Implement repository hygiene and checklist parsing**

Use `git ls-files` for tracked-file checks. Parse only lines matching `- [ ] ID:` or `- [x] ID:`. Fail on duplicate IDs, unknown completion syntax, or missing required IDs. Never infer a checked item from environment-variable presence.

- [ ] **Step 7: Add the Bash wrapper and Make targets**

`preflight.sh` passes `--phase`, `--strict`, and `--json` to the Python module. Add `preflight-strict` to the Makefile while retaining the public targets from Task 2.

- [ ] **Step 8: Run preflight tests**

Run: `python3 -m unittest tests.test_preflight -v`

Expected: all tests pass.

- [ ] **Step 9: Run real preflight in both modes**

Run:

```bash
scripts/preflight.sh --phase step-minus-one
scripts/preflight.sh --phase a0
scripts/preflight.sh --phase step-minus-one --strict
```

Expected now: truthful statuses matching observed tool versions, GitHub authentication, Docker daemon, and sibling state. Do not expect `0` before the sibling and approved tool installation are complete.

- [ ] **Step 10: Commit preflight**

```bash
git add scripts/preflight.sh scripts/preflight.py setup/human-setup-status.md tests/test_preflight.py Makefile
git commit -m "feat: add phase-aware environment preflight"
```

### Task 5: Add conservative local bootstrap automation

**Files:**
- Create: `scripts/bootstrap-local.sh`
- Create: `tests/test_bootstrap_local.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `.mise.toml`, `scripts/preflight.sh`, platform/package-manager detection, explicit `--install`.
- Produces: a no-write default diagnostic mode and an explicitly approved install mode that installs mise/tool requests then creates `mise.lock`.

- [ ] **Step 1: Write failing bootstrap behavior tests**

Run the script under a temporary fake `PATH`. Assert:

- no arguments never invokes `brew`, `apt-get`, `curl`, or `mise install`;
- `--install` with missing mise and fake Homebrew invokes only `brew install mise` then `mise install`;
- `--install` on unsupported platform exits nonzero with manual instructions and performs no install;
- unknown option exits `2`;
- install failure stops before preflight;
- success invokes `mise lock` and `preflight.sh --phase step-minus-one --strict`;
- command output containing token-like strings is not copied into the bootstrap summary.

- [ ] **Step 2: Run tests and verify the script is missing**

Run: `python3 -m unittest tests.test_bootstrap_local -v`

Expected: file-not-found failures.

- [ ] **Step 3: Implement default diagnostic mode**

Use Bash with `set -euo pipefail`. Default mode prints detected OS, architecture, package manager, mise presence, and the exact next command; it then runs non-strict Step −1 preflight. It must not install, log in, start Docker, or change global configuration.

- [ ] **Step 4: Implement explicit install mode**

On macOS with Homebrew, install mise using `brew install mise`. On Linux, support a detected system package only if mise's current official installation documentation names it; otherwise stop with a manual official-doc link. Never use `curl | sh`. After mise exists, run `mise install` and `mise lock`, then strict preflight.

- [ ] **Step 5: Add personal mise files to ignore rules**

Ignore `mise.local.toml`, `.mise.local.toml`, and `.venv/`; keep `.mise.toml` and `mise.lock` tracked.

- [ ] **Step 6: Run bootstrap tests and shell syntax checks**

Run:

```bash
python3 -m unittest tests.test_bootstrap_local -v
bash -n scripts/bootstrap-local.sh scripts/preflight.sh scripts/validate-spec-pack.sh
```

Expected: all pass.

- [ ] **Step 7: Commit bootstrap automation**

```bash
git add scripts/bootstrap-local.sh tests/test_bootstrap_local.py .gitignore
git commit -m "feat: add explicit local tool bootstrap"
```

### Task 6: Seed and validate the separate `launchpad-agent-kit` repository

**Files:**
- Create outside current root: `../launchpad-agent-kit/**` from `bootstrap/agent-kit/**`
- Create outside current root: `../launchpad-agent-kit/AGENTS.md`
- Create outside current root: `../launchpad-agent-kit/.mise.toml`
- Create outside current root: `../launchpad-agent-kit/.editorconfig`
- Create outside current root: `../launchpad-agent-kit/.gitattributes`
- Create outside current root: `../launchpad-agent-kit/.gitignore`
- Create outside current root: `../launchpad-agent-kit/Makefile`
- Create: `tests/test_agent_kit_seed.py`

**Interfaces:**
- Consumes: `bootstrap/agent-kit/` and explicit approval to write the sibling directory.
- Produces: an independent Git repository on `main`, with `make validate` and `make test`.

- [ ] **Step 1: Write failing sibling safety and structure tests**

Test a seed helper invoked through a temporary destination:

- missing destination is seeded with all starter files;
- non-empty destination without a matching marker is refused and unchanged;
- already seeded destination with matching manifest is accepted without overwriting modifications;
- destination `.git` is independent from the meta repository;
- resulting active branch is `main`;
- risk tests run successfully through the Makefile;
- agent-kit environment files contain no `LP_ORG` replacement or secret value.

The test may call a new private helper mode `scripts/bootstrap-local.sh --seed-agent-kit DEST` so production and test code share the same safety logic.

- [ ] **Step 2: Run the seed tests and confirm the helper mode is missing**

Run: `python3 -m unittest tests.test_agent_kit_seed -v`

Expected: failure because `--seed-agent-kit` is not implemented.

- [ ] **Step 3: Implement safe seed behavior**

Add `--seed-agent-kit DEST` with these rules: resolve an absolute destination; reject the meta root or any descendant; refuse any non-empty unrecognized destination; copy the starter mechanically; write a seed manifest of source relative paths and hashes; never overwrite on repeat; initialize Git with `git init -b main` only after successful copy.

- [ ] **Step 4: Run temporary-destination seed tests**

Run: `python3 -m unittest tests.test_agent_kit_seed -v`

Expected: all tests pass without touching the real sibling.

- [ ] **Step 5: Request filesystem approval and seed the real sibling**

Before execution, inspect `../launchpad-agent-kit` read-only if possible. Request escalation specifically to create that directory. Run the tested helper only after approval. If a non-empty directory exists, stop; do not merge or overwrite it.

- [ ] **Step 6: Add agent-kit environment files using `apply_patch` in the sibling**

`AGENTS.md` states that this is agent configuration, only the developer merges, A0 completes the starter, and reviewers are read-only. `.mise.toml` pins Python 3.14, Node 26, and uv latest for local validation. `Makefile` targets:

- `validate`: JSON parse, `bash -n`, plugin tree existence;
- `test`: `uv run --with pytest pytest -q scripts/test_risk.py`.

- [ ] **Step 7: Validate and commit the agent-kit repository**

Run:

```bash
make validate
make test
git status --short
git add .
git commit -m "chore: seed launchpad agent kit"
```

Expected: validation and 16 risk-classifier tests pass; no remotes and no secrets exist.

- [ ] **Step 8: Re-run meta preflight and commit meta integration tests**

Run `scripts/preflight.sh --phase step-minus-one`, then:

```bash
git add scripts/bootstrap-local.sh tests/test_agent_kit_seed.py
git commit -m "feat: seed separate launchpad agent kit"
```

### Task 7: Install approved tools, document the workflow, and verify Step −1

**Files:**
- Create after resolution: `mise.lock`
- Create: `docs/runbooks/local-development.md`
- Create: `docs/runbooks/step-minus-one-handoff.md`
- Modify: `README.md`
- Modify: `setup/human-setup-status.md` only for owner-confirmed checkbox state
- Test: all `tests/test_*.py`

**Interfaces:**
- Consumes: completed Tasks 1–6 and explicit approval for host-level installation/network access.
- Produces: strict workstation validation where possible, documented owner actions, and the final Step −1 evidence record.

- [ ] **Step 1: Request approval for host-level tool installation**

Show the exact command `scripts/bootstrap-local.sh --install`, the tools it will resolve, and that it uses Homebrew only for mise. Do not run it without approval.

- [ ] **Step 2: Run approved installation and record resolved versions**

Run: `scripts/bootstrap-local.sh --install`

Expected: mise installs/resolves Go 1.27.x, Node 26.x, Python 3.14.x, Rust stable, and uv; `mise.lock` is created. If network or platform support blocks a tool, preserve the evidence and leave the strict preflight item failed rather than substituting an unapproved version.

- [ ] **Step 3: Write the local development runbook**

Document dry-run bootstrap, install bootstrap, manual alternatives, `mise exec`, two-repository side-by-side layout, Docker daemon requirement, safe `gh auth login` guidance, all Make targets, preflight status/exit semantics, status-checklist usage, and milestone deadlines. Link current official mise documentation used to verify config and installation behavior.

- [ ] **Step 4: Add a concise environment section to the root README**

Keep the existing specification index intact. Add links to the approved design, implementation plan, local runbook, human status copy, and commands `make bootstrap`, `make validate`, `make preflight`, and `make preflight-a0`.

- [ ] **Step 5: Write the Step −1 handoff**

Record dated observed facts only: commits, exact commands and exit codes, resolved tool versions, skipped checks, owner actions, sibling path, no configured remotes, and the rule that A0-01/A0-02 verify/refine the imported/seeded assets rather than recreating them. Do not mark an owner checklist item complete without owner confirmation.

- [ ] **Step 6: Run the full local verification suite**

Run:

```bash
make test
make validate
make test-agent-kit
make preflight
make preflight-a0
scripts/preflight.sh --phase step-minus-one --strict
git diff --check
git status --short
git -C ../launchpad-agent-kit diff --check
git -C ../launchpad-agent-kit status --short
```

Expected:

- unit tests and validators pass;
- risk tests pass;
- non-strict Step −1 preflight exits `0` after local setup;
- A0 preflight exits `2` until owner GitHub actions are complete;
- strict preflight exits `0` only if Docker daemon and every pinned tool are ready, otherwise reports exact remaining local work;
- both repositories have only the intentional final documentation/lockfile changes before commit.

- [ ] **Step 7: Scan tracked files for secret/noise patterns**

Use `git ls-files` plus filename checks and gitleaks if installed. Confirm no `.DS_Store`, `.env*`, `*.pem`, `*.key`, private-key headers, or token-like test data are tracked. Test fixtures must use unmistakably synthetic redacted strings.

- [ ] **Step 8: Commit final documentation and lockfile**

```bash
git add README.md mise.lock docs/runbooks/local-development.md docs/runbooks/step-minus-one-handoff.md setup/human-setup-status.md
git commit -m "docs: complete step minus one environment setup"
```

- [ ] **Step 9: Perform verification-before-completion**

Invoke `superpowers:verification-before-completion`, rerun the commands it requires, and report actual outcomes. Step −1 may be called complete only when verification criteria 1–10 in the design are evidenced; otherwise report it as locally complete with exact owner/tool blockers.

---

## Self-Review Results

- **Spec coverage:** All design sections map to Tasks 1–7: import, instructions, toolchain, validation, preflight, checklist, bootstrap, sibling repository, documentation, safety, and final verification.
- **Step scan:** Each checklist step performs one authored change, one mechanical operation, one verification, or one commit. External mutations have explicit approval gates.
- **Type consistency:** `Finding`, `AllowRule`, `Status`, `CheckResult`, and `Context` have single definitions and stable names across tests and implementations.
- **Review focus:** Interrupted import, sibling overwrite, hostile/fake command output, placeholder classification, and false-ready A0 states each have an owning test.
- **Proportion:** The plan specifies decisions, interfaces, tests, and commands without embedding implementation bodies beyond fixed configuration.
