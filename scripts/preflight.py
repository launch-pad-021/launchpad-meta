"""Check local workstation and owner readiness for a Launchpad milestone."""

import argparse
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    OWNER_ACTION = "OWNER ACTION"


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


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
    command_runner: Runner
    issue: str | None = None
    container_drill: bool = False


PHASES = ("step-minus-one", "a0", "m0", "m1")
# A phase without an issue evaluates readiness across the whole phase.
M1_LANGUAGES = {
    "M1-01": {"go", "node", "python", "rust"},
    "M1-02": {"go", "node", "python", "rust"},
    "M1-03": {"go"},
    "M1-04": {"rust"},
    "M1-05": {"node"},
    "M1-06": {"go", "node", "rust"},
}
# Infrastructure issue prerequisites from specs/11-delivery-plan.md.
M0_DEPENDENCIES = {
    "M0-01": set(), "M0-02": {"M0-01"}, "M0-03": {"M0-01"},
    "M0-04": {"M0-01", "M0-02"}, "M0-05": {"M0-01", "M0-02"},
    "M0-06": {"M0-01", "M0-02"}, "M0-07": {"M0-01", "M0-02"},
}
OWNER_GATES = {
    "ACCOUNT-01": "M0-02", "ACCOUNT-02": "M0-01", "ACCOUNT-03": "M0-02",
    "ACCOUNT-04": "M0-02", "ACCOUNT-05": "A0", "ACCOUNT-06": "A0",
    "GITHUB-01": "A0", "GITHUB-02": "A0", "GITHUB-APPS-01": "A0",
    "GITHUB-SECRETS-01": "A0", "GITHUB-VARS-01": "A0", "GITHUB-REPOS-01": "A0",
    "GITHUB-PROJECT-01": "A0", "GITHUB-REPOS-02": "M0",
    "SERVER-01": "M0-01", "SERVER-02": "M0-02", "SERVER-03": "M0-05",
    "DNS-01": "M0-03", "DNS-02": "M0-02", "FINAL-01": "M0", "FINAL-02": "M0",
}

RESTRICTED_BASENAMES = {
    ".DS_Store", ".env", "id_dsa", "id_ecdsa", "id_ed25519", "id_rsa", "id_xmss",
}
RESTRICTED_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def restricted_tracked_path(name: str) -> bool:
    parts = Path(name).parts
    basename = parts[-1] if parts else ""
    return (
        any(part in RESTRICTED_PARTS for part in parts)
        or basename in RESTRICTED_BASENAMES
        or basename.startswith(".env.")
        or basename.endswith((".pem", ".key", ".pyc", ".pyo"))
    )


def probe(runner: Runner, *args: str) -> str | None:
    """Keep raw command output internal. None denotes unavailable or unsuccessful."""
    try:
        result = runner(args)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def git_path(root: Path, runner: Runner, option: str) -> Path | None:
    output = probe(runner, "git", "-C", str(root), "rev-parse", "--path-format=absolute", option)
    if not output or not output.rstrip("\n"):
        return None
    return Path(output.rstrip("\n")).resolve()


def resolve_sibling(root: Path, env: Mapping[str, str], runner: Runner) -> Path:
    override = env.get("LP_AGENT_KIT_PATH")
    if override:
        return Path(os.path.realpath(root / override))
    common = git_path(root, runner, "--git-common-dir")
    canonical = common.parent if common else root
    return canonical.parent / "launchpad-agent-kit"


def local(ctx: Context, name: str, ready: bool, detail: str, required: bool = True) -> CheckResult:
    status = Status.PASS if ready else Status.FAIL if required else Status.SKIP
    return CheckResult(name, status, ctx.phase, detail, required)


def owner(ctx: Context, name: str, ready: bool, required: bool, detail: str) -> CheckResult:
    return CheckResult(name, Status.PASS if ready else Status.OWNER_ACTION, ctx.phase, detail, required)


def owner_required(ctx: Context, gate: str) -> bool:
    if gate == "A0":
        return ctx.phase != "step-minus-one"
    if ctx.phase not in ("m0", "m1"):
        return False
    if ctx.phase == "m0" and ctx.issue and gate.startswith("M0-"):
        return gate == ctx.issue or gate in M0_DEPENDENCIES[ctx.issue]
    return True


def checklist_checks(ctx: Context) -> list[CheckResult]:
    path = ctx.root / "setup/human-setup-status.md"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (UnicodeError, OSError):
        return [local(ctx, "owner-checklist", False, "cannot read setup/human-setup-status.md")]
    state = {}
    for line in lines:
        if not re.match(r"^\s*[-*+]\s*\[", line):
            continue
        match = re.fullmatch(r"- \[([ x])\] ([A-Z]+(?:-[A-Z]+)*-[0-9]{2}):.*", line)
        if not match or match[2] not in OWNER_GATES or match[2] in state:
            return [local(ctx, "owner-checklist", False, "invalid or duplicate checklist entry")]
        state[match[2]] = match[1] == "x"
    if state.keys() != OWNER_GATES.keys():
        return [local(ctx, "owner-checklist", False, "required checklist entries missing")]
    checks = [local(ctx, "owner-checklist", True, "all required IDs present")]
    for ident, gate in OWNER_GATES.items():
        detail = "marked complete" if state[ident] else f"pending in setup/human-setup-status.md (due {gate})"
        checks.append(owner(ctx, ident, state[ident], owner_required(ctx, gate), detail))
    return checks


def is_agent_kit(root: Path, sibling: Path, runner: Runner) -> bool:
    meta_common = git_path(root, runner, "--git-common-dir")
    kit_common = git_path(sibling, runner, "--git-common-dir")
    return (
        git_path(sibling, runner, "--show-toplevel") == sibling
        and meta_common is not None and kit_common is not None and kit_common != meta_common
        and all((sibling / path).is_file() for path in (
            ".claude-plugin/marketplace.json", "scripts/risk.py", "scripts/test_risk.py",
        ))
    )


def repository_checks(ctx: Context) -> list[CheckResult]:
    runner = ctx.command_runner
    root = ctx.root.resolve()
    sibling = Path(os.path.realpath(ctx.sibling))
    sibling_ok = is_agent_kit(root, sibling, runner)
    layout_ok = (
        git_path(root, runner, "--show-toplevel") == root
        and all((root / name).is_file() for name in (
            "README.md", "AGENTS.md", "CLAUDE.md", "Makefile", ".mise.toml",
            "specs/16-human-setup.md", "contracts/events/envelope.schema.json", "bootstrap/KICKOFF.md",
        ))
        and not (root / "launchpad-spec-pack").exists()
    )
    branch = probe(runner, "git", "-C", str(root), "symbolic-ref", "--quiet", "--short", "HEAD")
    checks = [
        local(ctx, "meta-layout", layout_ok, "root layout present" if layout_ok else "check the meta root layout"),
        local(ctx, "sibling", sibling_ok, "independent agent kit present" if sibling_ok
              else "independent seeded agent kit required"),
        local(ctx, "branch", bool(branch), "on main" if branch == "main\n" else
              "on a working branch" if branch else "detached HEAD or branch unavailable", required=False),
    ]
    for label, repo, valid in (("meta", root, layout_ok), ("kit", sibling, sibling_ok)):
        names = probe(runner, "git", "-C", str(repo), "ls-files", "-z") if valid else None
        clean = names is not None and not any(
            restricted_tracked_path(name) for name in names.split("\0") if name
        )
        checks.append(local(ctx, f"{label}-tracked-files", clean, "index clean" if clean else
                            "tracked restricted path" if names is not None else "index unavailable"))
        remote = probe(runner, "git", "-C", str(repo), "remote") if valid else None
        configured = bool(remote and remote.strip())
        checks.append(owner(ctx, f"{label}-remote", configured, ctx.phase != "step-minus-one",
                            "remote configured" if configured else "configure repository remote"))
    return checks


VERSION = r"([0-9]{1,4}(?:\.[0-9]{1,4}){1,3})"
# Capture only the numeric release from a version line. Never render command output.
TOOLS = {
    "git": (("git", "--version"), r"git version "),
    "bash": (("bash", "--version"), r"GNU bash, version "),
    "make": (("make", "--version"), r"GNU Make "),
    "jq": (("jq", "--version"), r"jq-"),
    "claude": (("claude", "--version"), ""),
    "python": (("python3", "--version"), "Python "),
    "go": (("go", "version"), "go version go"),
    "node": (("node", "--version"), "v"),
    "rust": (("rustc", "--version"), "rustc "),
    "uv": (("uv", "--version"), "uv "),
    "buf": (("buf", "--version"), ""),
    "gh": (("gh", "--version"), "gh version "),
    "docker-client": (("docker", "--version"), "Docker version "),
}
TARGETS = {"go": "1.27.x", "node": "26.x", "python": "3.14.x", "rust": "stable with Edition 2024"}


def version_of(ctx: Context, name: str) -> tuple[int, ...]:
    command, prefix = TOOLS[name]
    output = probe(ctx.command_runner, *command)
    if not output:
        return ()
    vendor = r"(?:-apple)?" if name == "jq" else ""
    match = re.search(r"^" + prefix + VERSION + vendor + r"(?=[\s(,]|$)", output, re.MULTILINE)
    return tuple(map(int, match[1].split("."))) if match else ()


def tool_checks(ctx: Context) -> list[CheckResult]:
    versions = {name: version_of(ctx, name) for name in TOOLS}
    desired = {
        "go": versions["go"][:2] == (1, 27),
        "node": versions["node"][:1] == (26,),
        "python": versions["python"][:2] == (3, 14),
        "rust": versions["rust"] >= (1, 85),
    }
    languages = M1_LANGUAGES.get(ctx.issue, TARGETS)
    daemon_required = ctx.strict or ctx.phase in ("m0", "m1") or ctx.container_drill
    checks = []
    for name, version in versions.items():
        required = True
        detail = ".".join(map(str, version)) if version else "missing or unrecognized version"
        if name in TARGETS:
            required = ctx.strict or (ctx.phase == "m1" and name in languages)
            detail += f" (requires {TARGETS[name]})"
        elif name == "buf":
            required = ctx.strict or ctx.phase == "m1"
        elif name == "docker-client":
            required = daemon_required
        elif name == "gh":
            required = ctx.phase != "step-minus-one"
        checks.append(local(ctx, name, desired.get(name, bool(version)), detail, required))

    capable = versions["python"] >= (3, 11)
    checks.append(local(ctx, "python-runtime", capable, "Python 3.11+ available" if capable
                        else "active Python 3.11+ required"))
    authenticated = bool(versions["gh"]) and probe(ctx.command_runner, "gh", "auth", "status",
                                                   "--hostname", "github.com") is not None
    checks.append(owner(ctx, "gh-auth", authenticated, ctx.phase != "step-minus-one",
                        "authenticated" if authenticated else "authentication required"))
    daemon = bool(versions["docker-client"]) and probe(ctx.command_runner, "docker", "info",
                                                      "--format", "{{.ServerVersion}}") is not None
    checks.append(local(ctx, "docker-daemon", daemon, "daemon available" if daemon else "daemon unavailable",
                        daemon_required))
    # These are local hints only. The owner verifies organization-side configuration.
    for key in ("LP_ORG", "LP_OWNER_LOGIN", "LP_BASE_DOMAIN"):
        present = bool(ctx.env.get(key))
        checks.append(local(ctx, f"env-{key}", present, "present locally" if present else "unset locally", False))
    return checks


def risk_tests(sibling: Path, runner: Runner) -> tuple[bool, str]:
    args = ("uv", "run", "--no-project", "--no-python-downloads", "--python", "python3",
            "--with", "pytest", "pytest", "-q", "--color=no",
            str(sibling / "scripts/test_risk.py"))
    output = probe(runner, args[0], args[1], "--offline", *args[2:])
    if output is None:
        output = probe(runner, *args)
    if output is None:
        return False, "sibling risk tests failed or uv unavailable"
    summary = re.search(r"^([1-9][0-9]{0,5}) passed(?:, [0-9]+ warnings?)? in ", output, re.MULTILINE)
    if not summary:
        return False, "pytest did not report a complete passing suite"
    return True, f"{summary[1]} sibling risk tests passed"


def run_checks(context: Context) -> list[CheckResult]:
    ctx = context
    if ctx.phase not in PHASES or (ctx.issue and (
        ctx.issue not in M0_DEPENDENCIES.keys() | M1_LANGUAGES.keys()
        or ctx.issue[:2].lower() != ctx.phase
    )) or (ctx.container_drill and ctx.phase != "a0"):
        return [local(ctx, "phase-selection", False, "invalid phase, issue or container drill selection")]
    checks = repository_checks(ctx) + tool_checks(ctx) + checklist_checks(ctx)
    ready = {row.check_id for row in checks if row.status == Status.PASS}
    milestone = ctx.phase if ctx.phase == "step-minus-one" else ctx.phase.upper()
    valid = probe(ctx.command_runner, str(ctx.root / "scripts/validate-spec-pack.sh"),
                  "--milestone", milestone) is not None
    checks.append(local(ctx, "spec-validation", valid, "spec pack validated" if valid
                        else "run make validate for spec diagnostics"))
    eligible = {"sibling", "uv", "python-runtime"} <= ready
    if eligible:
        risk_ok, detail = risk_tests(ctx.sibling, ctx.command_runner)
    else:
        risk_ok, detail = False, "requires the sibling, uv and Python 3.11+"
    checks.append(local(ctx, "risk-tests", risk_ok, detail))
    return sorted(checks, key=lambda row: row.check_id)


def exit_code(results: Sequence[CheckResult]) -> int:
    if any(row.blocking and row.status in (Status.FAIL, Status.SKIP) for row in results):
        return 1
    return 2 if any(row.blocking and row.status == Status.OWNER_ACTION for row in results) else 0


def run_command(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          errors="replace", timeout=120, check=False)


def main() -> int:
    class ExitOneArgumentParser(argparse.ArgumentParser):
        def error(self, message: str) -> None:
            self.print_usage(__import__("sys").stderr)
            self.exit(1, f"{self.prog}: error: {message}\n")

    parser = ExitOneArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=PHASES, default="step-minus-one")
    parser.add_argument("--strict", action="store_true", help="require the full toolchain and Docker daemon")
    parser.add_argument("--issue", type=str.upper, choices=(*M0_DEPENDENCIES, *M1_LANGUAGES),
                        help="check the prerequisites of this M0 or M1 issue")
    parser.add_argument("--container-drill", action="store_true", help="require Docker for an A0 container drill")
    parser.add_argument("--json", action="store_true", help="emit a JSON array")
    parser.add_argument("--test-agent-kit", action="store_true", help="run only the sibling risk tests")
    args = parser.parse_args()
    if args.issue and args.issue[:2].lower() != args.phase:
        parser.error("--issue must belong to the requested --phase")
    if args.container_drill and args.phase != "a0":
        parser.error("--container-drill requires --phase a0")
    root = Path(__file__).resolve().parents[1]
    sibling = resolve_sibling(root, os.environ, run_command)
    if args.test_agent_kit:
        if not is_agent_kit(root, sibling, run_command):
            print("Independent seeded agent kit required")
            return 1
        ok, detail = risk_tests(sibling, run_command)
        print(detail)
        return int(not ok)
    ctx = Context(root, sibling, args.phase, args.strict, os.environ, run_command, args.issue, args.container_drill)
    checks = run_checks(ctx)
    if args.json:
        print(json.dumps([asdict(row) for row in checks], indent=2))
    else:
        print(f"Preflight for {ctx.phase}" + (" (strict)" if ctx.strict else ""))
        print(f"{'STATUS':<12}  {'CHECK':<22}  {'REQUIRED':<8}  DETAIL")
        for row in checks:
            print(f"{row.status:<12}  {row.check_id:<22}  {'yes' if row.blocking else 'no':<8}  {row.detail}")
    return exit_code(checks)


if __name__ == "__main__":
    raise SystemExit(main())
