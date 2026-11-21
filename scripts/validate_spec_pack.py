"""Validate the Launchpad specification pack without changing its files."""

import argparse
import json
import os
import re
import shutil
import subprocess
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Literal


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


MILESTONES = ("step-minus-one", "A0", "M0", "M1")
ALLOWLIST = "scripts/placeholder-allowlist.txt"
CATALOG = "contracts/events/catalog.md"
ENVELOPE = "contracts/events/envelope.schema.json"
EVENT_SUFFIX = ".schema.json"

JSON_FILES = (
    "bootstrap/agent-kit/.claude-plugin/marketplace.json",
    "bootstrap/agent-kit/plugins/launchpad/.claude-plugin/plugin.json",
    "bootstrap/agent-kit/plugins/launchpad/hooks/hooks.json",
    "bootstrap/agent-kit/schemas/review.schema.json",
)
HOOK_SCRIPTS = tuple(
    f"bootstrap/agent-kit/plugins/launchpad/hooks/scripts/{name}.sh"
    for name in ("guard-bash", "guard-paths", "session-start", "stop-checks")
)
LIVE_ENTRYPOINTS = (
    "scripts/bootstrap-local.sh",
    "scripts/preflight.sh",
    "scripts/validate-spec-pack.sh",
)
REQUIRED_FILES = (
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    *(f"specs/{name}.md" for name in (
        "00-product", "01-architecture", "02-tech-stack", "03-conventions", "04-contracts",
        "05-data", "06-public-api", "07-infrastructure", "08-security", "09-observability",
        "10-testing", "11-delivery-plan", "12-agentic-system", "13-runbooks", "14-decisions",
        "15-verification-log", "16-human-setup",
    )),
    *(f"specs/services/{name}.md" for name in (
        "analytics", "builder", "cli", "dashboard", "deployer", "gateway", "identity",
        "ingest", "logs", "notifier", "processor", "projects", "router", "runtime-agent", "scm",
    )),
    CATALOG,
    ENVELOPE,
    "contracts/proto/launchpad/common/v1/common.proto",
    "bootstrap/KICKOFF.md",
    "bootstrap/agent-kit/README.md",
    "bootstrap/launchpad-meta/CLAUDE.md",
    "bootstrap/templates/AGENTS.md.service",
    "bootstrap/templates/CLAUDE.md.service",
    "bootstrap/templates/CODEOWNERS.example",
    "bootstrap/templates/ISSUE_TEMPLATE/agent-task.yml",
    "bootstrap/templates/PULL_REQUEST_TEMPLATE.md",
    *JSON_FILES,
    *HOOK_SCRIPTS,
    "scripts/validate-spec-pack.sh",
    ALLOWLIST,
)

LOCAL_DIRECTORIES = {".git", ".superpowers", ".venv", "__pycache__", "node_modules"}
TEXT_SUFFIXES = {".example", ".json", ".md", ".proto", ".service", ".sh", ".toml", ".txt", ".yaml", ".yml"}
ANGLE_TEXT = r"[A-Za-z0-9_.,+ |/()'-]"
PLACEHOLDER = re.compile(
    r"<!--[ \t]*[^<>]*?-->"
    r"|\bStarter; scripts/[\w./-]+ is built in A0-\d+\."
    r"|\bscripts/[\w./-]+ \(A0-\d+\):"
    rf"|<[A-Za-z0-9](?:{ANGLE_TEXT}|<[A-Za-z0-9]{ANGLE_TEXT}*>)*>"
    r"|\b(?:LP_ORG|vX\.Y\.Z|[A-Z0-9]+(?:_[A-Z0-9]+)*_PLACEHOLDER|(?i:TODO|FIXME|TBD))\b"
)
EVENT_NAME = re.compile(r"[a-z_]+(?:\.[a-z_]+)*\.v[0-9]+")


def load_allowlist(path: Path) -> list[AllowRule]:
    rules = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 4 or any(not field.strip() for field in fields):
            raise ValueError(f"line {number}: expected four nonempty tab-separated fields")
        rule = AllowRule(*fields)
        if rule.expires not in MILESTONES:
            raise ValueError(f"line {number}: expected an expiry in {', '.join(MILESTONES)}")
        try:
            re.compile(rule.pattern)
        except re.error as exc:
            raise ValueError(f"line {number}: invalid regular expression ({exc})") from exc
        rules.append(rule)
    return rules


def pack_files(root: Path) -> Iterator[Path]:
    for directory, subdirectories, names in os.walk(root):
        subdirectories[:] = sorted(set(subdirectories) - LOCAL_DIRECTORIES)
        for name in sorted(names):
            path = Path(directory) / name
            if not path.is_symlink() and path.is_file():
                yield path


def find_placeholders(root: Path, rules: Sequence[AllowRule], milestone: str) -> list[Finding]:
    """Apply path globs and full-token patterns to the authored text surfaces."""
    current = MILESTONES.index(milestone)
    compiled_rules = [
        (rule, re.compile(rule.pattern), MILESTONES.index(rule.expires)) for rule in rules
    ]
    findings = []
    for path in pack_files(root):
        relative = path.relative_to(root).as_posix()
        if (
            relative == ALLOWLIST
            or relative.startswith(("docs/superpowers/", "tests/"))
            or path.suffix not in TEXT_SUFFIXES
            or path.name.startswith(".env.")
        ):
            continue
        candidates = [entry for entry in compiled_rules if fnmatchcase(relative, entry[0].path_glob)]
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeError, OSError):
            findings.append(Finding("error", "placeholder", relative, "cannot read file as UTF-8"))
            continue
        for number, line in enumerate(lines, 1):
            for match in PLACEHOLDER.finditer(line):
                token = match.group()
                detail = f"line {number}: {token}"
                matching = [entry for entry in candidates if entry[1].fullmatch(token)]
                if not matching:
                    findings.append(Finding("error", "placeholder", relative, f"{detail} is unexpected"))
                    continue
                rule, _, expiry = next((entry for entry in matching if current > entry[2]), matching[0])
                if current > expiry:
                    findings.append(Finding(
                        "error", "placeholder", relative, f"{detail} expired at {rule.expires} ({rule.reason})",
                    ))
                else:
                    findings.append(Finding(
                        "allowed", "placeholder", relative, f"{detail} ({rule.reason}, through {rule.expires})",
                    ))
    return findings


def reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")


def check_json(root: Path) -> list[Finding]:
    findings = []
    schema_paths = sorted((root / "contracts/events").glob(f"*{EVENT_SUFFIX}"))
    for path in (*schema_paths, *(root / name for name in JSON_FILES)):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        try:
            data = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_json_constant)
        except json.JSONDecodeError as exc:
            findings.append(Finding("error", "json", relative, f"line {exc.lineno}, column {exc.colno}: {exc.msg}"))
            continue
        except (UnicodeError, OSError):
            findings.append(Finding("error", "json", relative, "cannot read file as UTF-8"))
            continue
        except ValueError as exc:
            findings.append(Finding("error", "json", relative, str(exc)))
            continue
        if not isinstance(data, dict):
            findings.append(Finding("error", "json", relative, "expected a JSON object"))
            continue
        if relative == ENVELOPE:
            expected_title = "Launchpad event envelope"
        elif path in schema_paths:
            expected_title = path.name.removesuffix(EVENT_SUFFIX)
            if not EVENT_NAME.fullmatch(expected_title):
                findings.append(Finding("error", "event-title", relative, "filename must use a versioned event type"))
        else:
            continue
        if data.get("title") != expected_title:
            findings.append(Finding("error", "event-title", relative, f"expected schema title {expected_title!r}"))
    return findings


def check_catalog(root: Path) -> list[Finding]:
    catalog = root / CATALOG
    if not catalog.is_file():
        return []
    try:
        lines = catalog.read_text(encoding="utf-8").splitlines()
    except (UnicodeError, OSError):
        return [Finding("error", "event-catalog", CATALOG, "cannot read file as UTF-8")]

    rows: Counter[str] = Counter()
    findings = []
    for number, line in enumerate(lines, 1):
        if not line.lstrip().startswith("|"):
            continue
        cell = line.split("|")[1].strip()
        if cell == "Type" or re.fullmatch(r":?-{3,}:?", cell):
            continue
        event = cell.removeprefix("`").removesuffix("`")
        if not EVENT_NAME.fullmatch(event):
            findings.append(Finding("error", "event-catalog", CATALOG, f"line {number}: invalid event type"))
            continue
        rows[event] += 1
        if rows[event] == 2:
            findings.append(Finding("error", "event-catalog", CATALOG, f"line {number}: duplicate event {event}"))

    schemas = {
        path.name.removesuffix(EVENT_SUFFIX)
        for path in catalog.parent.glob(f"*{EVENT_SUFFIX}")
        if path.is_file() and path.name != Path(ENVELOPE).name
    }
    for event in sorted(rows.keys() - schemas):
        findings.append(Finding("error", "event-catalog", CATALOG, f"{event} has no event schema"))
    for event in sorted(schemas - rows.keys()):
        findings.append(Finding("error", "event-catalog", CATALOG, f"{event} is missing from the catalog"))
    return findings


def check_shell(root: Path) -> list[Finding]:
    shell_files = [path for path in pack_files(root) if path.suffix == ".sh"]
    if not shell_files:
        return []
    bash = shutil.which("bash")
    if bash is None:
        return [Finding("error", "shell-syntax", ".", "bash is required to check shell syntax")]
    findings = []
    for path in shell_files:
        relative = path.relative_to(root).as_posix()
        try:
            result = subprocess.run(
                [bash, "-n", "--", relative], cwd=root,
                env={**os.environ, "BASH_ENV": "", "LC_ALL": "C"},
                capture_output=True, text=True, errors="replace", check=False,
            )
        except OSError:
            findings.append(Finding("error", "shell-syntax", relative, "could not run bash -n"))
            continue
        if result.returncode:
            location = re.search(r": (line \d+):", result.stderr)
            suffix = f" at {location[1]}" if location else ""
            findings.append(Finding("error", "shell-syntax", relative, f"bash -n failed{suffix}"))
    return findings


def check_executables(root: Path) -> list[Finding]:
    findings = []
    for name in (*LIVE_ENTRYPOINTS, *HOOK_SCRIPTS):
        path = root / name
        if path.is_file() and not path.stat().st_mode & 0o100:
            if name in HOOK_SCRIPTS:
                level = "warning"
                detail = "imported hook template lacks the owner execute bit; set it when installing the hook in A0"
            else:
                level = "error"
                detail = "entrypoint lacks the owner execute bit"
            findings.append(Finding(level, "executable", name, detail))
    return findings


def check_buf(root: Path) -> list[Finding]:
    config = "buf.yaml"
    if not (root / config).is_file():
        return [Finding("skip", "buf", config, "no root buf.yaml; the contracts starter gains Buf configuration in M1")]
    buf = shutil.which("buf")
    if buf is None:
        return [Finding("skip", "buf", config, "root buf.yaml exists, but buf is unavailable on PATH")]
    findings = []
    for arguments in (("format", "--diff", "--exit-code"), ("lint",)):
        check = f"buf-{arguments[0]}"
        command = f"buf {' '.join(arguments)}"
        try:
            result = subprocess.run([buf, *arguments], cwd=root, capture_output=True, check=False)
        except OSError:
            findings.append(Finding("error", check, config, f"could not run {command}"))
            continue
        if result.returncode:
            findings.append(Finding("error", check, config, f"{command} exited {result.returncode}"))
    return findings


def validate(root: Path, milestone: str = "step-minus-one") -> list[Finding]:
    if milestone not in MILESTONES:
        return [Finding("error", "milestone", ".", f"expected one of {', '.join(MILESTONES)}")]
    findings = [
        Finding("error", "required", name, "required file is missing")
        for name in REQUIRED_FILES if not (root / name).is_file()
    ]
    findings.extend(check_json(root))
    findings.extend(check_catalog(root))
    if (root / ALLOWLIST).is_file():
        try:
            rules = load_allowlist(root / ALLOWLIST)
        except (UnicodeError, OSError):
            findings.append(Finding("error", "allowlist", ALLOWLIST, "cannot read file as UTF-8"))
        except ValueError as exc:
            findings.append(Finding("error", "allowlist", ALLOWLIST, str(exc)))
        else:
            findings.extend(find_placeholders(root, rules, milestone))
    findings.extend(check_shell(root))
    findings.extend(check_executables(root))
    findings.extend(check_buf(root))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--milestone", choices=MILESTONES, default="step-minus-one")
    parser.add_argument("--json", action="store_true", help="emit an array of findings as JSON")
    args = parser.parse_args()

    findings = validate(Path(__file__).resolve().parents[1], args.milestone)
    if args.json:
        print(json.dumps([asdict(finding) for finding in findings], indent=2))
    else:
        for level, heading in (
            ("error", "Errors"), ("warning", "Warnings"),
            ("allowed", "Allowed placeholders"), ("skip", "Skips"),
        ):
            group = [finding for finding in findings if finding.level == level]
            print(f"{heading} ({len(group)})")
            for finding in group:
                print(f"  {finding.path}: {finding.detail} [{finding.check}]")
    return int(any(finding.level == "error" for finding in findings))


if __name__ == "__main__":
    raise SystemExit(main())
