#!/usr/bin/env python3
"""Deterministic PR risk classifier for Launchpad (specs/12-agentic-system.md §11.1).

Usage:
  risk.py --repo launchpad-identity --files changed.txt --diff pr.diff [--labels a,b] [--buf-breaking]
Prints JSON: {"level": "low|medium|high", "agent_config": bool, "reasons": [...]}
The level can only be raised by labels, never lowered.
"""
from __future__ import annotations
import argparse, json, re, sys

LEVELS = {"low": 0, "medium": 1, "high": 2}

AGENT_CONFIG_PATTERNS = [r"^\.github/", r"^\.claude/", r"^CLAUDE\.md$", r"^AGENTS\.md$", r"(^|/)CODEOWNERS$", r"^renovate\.json$"]
AGENT_CONFIG_REPOS = {"launchpad-agent-kit", "launchpad-meta"}

# repo -> list of (path regex, reason); "" regex = whole repo
HIGH_RISK_PATHS = {
    "launchpad-identity": [("", "identity: auth, sessions, tokens, JWT")],
    "launchpad-projects": [(r"^internal/(crypto|secrets|runtimeenv)/", "projects: secret handling / GetRuntimeEnv")],
    "launchpad-scm": [(r"^src/webhooks/", "scm: webhook signature verification")],
    "launchpad-router": [("", "router: Traefik rendering and hostname validation")],
    "launchpad-runtime-agent": [("", "runtime-agent: Docker socket and container security")],
    "launchpad-builder": [("", "builder: BuildKit sandbox and registry")],
    "launchpad-gateway": [(r"^internal/(auth|csrf|ratelimit)/", "gateway: auth/CSRF/rate limiting")],
    "launchpad-ingest": [(r"^src/(handler|validate)", "ingest: untrusted input handling")],
    "launchpad-analytics": [(r"^src/lp_analytics/(ask|chusers)/", "analytics: Ask / ClickHouse user management")],
}
TEST_DOC_PATTERNS = [r"(^|/)test(s)?/", r"_test\.go$", r"\.test\.ts$", r"(^|/)test_[^/]*\.py$", r"\.md$", r"^docs/"]
DEP_MANIFESTS = [r"(^|/)go\.mod$", r"(^|/)Cargo\.toml$", r"(^|/)package\.json$", r"(^|/)pyproject\.toml$"]
DESTRUCTIVE_SQL = re.compile(r"\b(DROP\s+(TABLE|COLUMN|INDEX|TYPE|DATABASE)|RENAME\s+(COLUMN|TO)|ALTER\s+COLUMN\s+\S+\s+(TYPE|SET\s+NOT\s+NULL)|TRUNCATE)\b", re.I)


def _match(patterns, path):
    return any(re.search(p, path) for p in patterns)


def added_lines_by_file(diff: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            p = line[4:].strip()
            current = p[2:] if p.startswith("b/") else p
            out.setdefault(current, [])
        elif current and line.startswith("+") and not line.startswith("+++"):
            out[current].append(line[1:])
    return out


def changed_line_count(diff: str) -> int:
    return sum(1 for l in diff.splitlines() if (l.startswith("+") or l.startswith("-")) and not l.startswith(("+++", "---")))


def classify(repo: str, files: list[str], diff: str = "", labels: list[str] | None = None, buf_breaking: bool = False) -> dict:
    labels = labels or []
    level = "low"
    reasons: list[str] = []
    agent_config = False

    def raise_to(new: str, reason: str):
        nonlocal level
        if LEVELS[new] > LEVELS[level]:
            level = new
        reasons.append(f"{new}: {reason}")

    if repo in AGENT_CONFIG_REPOS:
        agent_config = True
        raise_to("high", f"{repo} is agent configuration")
    for f in files:
        if _match(AGENT_CONFIG_PATTERNS, f):
            agent_config = True
            raise_to("high", f"agent-config path {f}")

    non_test = [f for f in files if not _match(TEST_DOC_PATTERNS, f)]

    for regex, reason in HIGH_RISK_PATHS.get(repo, []):
        hits = non_test if regex == "" else [f for f in non_test if re.search(regex, f)]
        if hits:
            raise_to("high", reason)

    if repo == "launchpad-infra":
        others = [f for f in files if f != "versions.env"]
        if others:
            raise_to("high", "infra change other than versions.env")
        if "inherit:high" in labels:
            raise_to("high", "release contains a high-risk change")
        if "inherit:medium" in labels or "has-migration" in labels:
            raise_to("medium", "release contains a migration or medium-risk change")

    if repo == "launchpad-contracts":
        if buf_breaking:
            raise_to("high", "breaking contract change (buf breaking failed)")
        elif any(f.startswith(("proto/", "events/")) for f in files):
            raise_to("medium", "additive contract change")

    added = added_lines_by_file(diff)
    for f, lines in added.items():
        if "migrations/" in f:
            if any(DESTRUCTIVE_SQL.search(l) for l in lines):
                raise_to("high", f"destructive migration in {f}")
            else:
                raise_to("medium", f"migration {f}")

    if any(_match(DEP_MANIFESTS, f) for f in files):
        raise_to("medium", "dependency manifest changed")

    n = changed_line_count(diff)
    if n > 400:
        raise_to("medium", f"large change ({n} lines)")

    for lab in labels:
        if lab.startswith("risk:") and lab[5:] in LEVELS:
            raise_to(lab[5:], f"label {lab}")

    if not reasons:
        reasons.append("low: no risk rules matched")
    return {"level": level, "agent_config": agent_config, "reasons": reasons}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--files", required=True, help="file with one changed path per line")
    ap.add_argument("--diff", default=None)
    ap.add_argument("--labels", default="")
    ap.add_argument("--buf-breaking", action="store_true")
    a = ap.parse_args(argv)
    files = [l.strip() for l in open(a.files) if l.strip()]
    diff = open(a.diff).read() if a.diff else ""
    labels = [x for x in a.labels.split(",") if x]
    print(json.dumps(classify(a.repo, files, diff, labels, a.buf_breaking)))


if __name__ == "__main__":
    sys.exit(main())
