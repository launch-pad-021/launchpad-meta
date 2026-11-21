#!/usr/bin/env python3
"""Fail-closed planner for Launchpad repository provisioning.

Dry-run is the default. Apply requires an explicit owner approval flag and all
immutable workflow/check producer inputs. GitHub I/O is deliberately isolated
behind an adapter so policy is fixture-testable without credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "bootstrap/templates/repos.json"
MARKER = "launchpad-provision-v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ORG_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


class ConfigError(RuntimeError):
    pass


def load_manifest(path: Path = MANIFEST) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("repositories")
    if data.get("schema") != 1 or not isinstance(entries, list):
        raise ConfigError("unsupported repository manifest")
    names = [entry.get("name") for entry in entries]
    if len(names) != 25 or len(set(names)) != 25:
        raise ConfigError("manifest must contain 25 unique repositories")
    if sum(entry.get("mode") == "create" for entry in entries) != 23:
        raise ConfigError("manifest must contain exactly 23 creation targets")
    for entry in entries:
        if not re.fullmatch(r"launchpad-[a-z0-9-]+", entry.get("name", "")):
            raise ConfigError("invalid repository name in manifest")
        if entry.get("mode") not in {"create", "audit"}:
            raise ConfigError("invalid manifest mode")
    return data


def _workflow(name: str, kit_ref: str) -> str:
    target = {"ci": "templates/ci-{{FAMILY}}.yml", "agent": ".github/workflows/agent-implement.yml",
              "release-please": ".github/workflows/release.yml"}[name]
    secret = ("\n    secrets:\n      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}\n"
              if name == "agent" else "\n")
    return f"""name: {name}\non:\n  workflow_dispatch:\n  pull_request:\npermissions: {{}}\njobs:\n  call:\n    uses: launch-pad-021/launchpad-agent-kit/{target}@{kit_ref} # KIT_REF is replaced only after review\n{secret}"""


def render_repository(name: str, family: str, milestone: str, spec: str,
                      migrations: str | None = None, kit_ref: str = "KIT_REF") -> dict[str, str]:
    if family not in {"go", "rust", "python", "node", "next", "shared"}:
        raise ConfigError(f"unsupported template family: {family}")
    service = name.removeprefix("launchpad-")
    replacements = {"{{REPO}}": name, "{{SERVICE}}": service,
                    "{{SERVICE_UNDERSCORE}}": service.replace("-", "_"),
                    "{{MILESTONE}}": milestone, "{{SPEC}}": spec,
                    "{{FAMILY}}": family}
    def expand(value: str) -> str:
        for old, new in replacements.items():
            value = value.replace(old, new)
        return value

    readme = expand((ROOT / "bootstrap/templates/common/README.md.tmpl").read_text())
    claude = (ROOT / "bootstrap/templates/CLAUDE.md.service").read_text().replace(
        "<service>", service).replace("<one-line purpose from specs/services/" + service + ".md>",
                                      f"Seed for {service}; behavior is defined by {spec}.")
    agents = (ROOT / "bootstrap/templates/AGENTS.md.service").read_text().replace(
        "<service>", service).replace("<purpose>", f"requirements in {spec}")
    owners = (ROOT / "bootstrap/templates/CODEOWNERS.example").read_text().replace(
        "*                       @LP_OWNER_LOGIN          # P0 only — delete at P1",
        "# P0 catch-all; replace LP_OWNER_LOGIN during rendering\n* @LP_OWNER_LOGIN")
    tree = {
        "README.md": readme,
        "CLAUDE.md": claude,
        "AGENTS.md": agents,
        "CODEOWNERS": owners,
        "renovate.json": (ROOT / "bootstrap/templates/common/renovate.json").read_text(),
        ".github/ISSUE_TEMPLATE/agent-task.yml": (ROOT / "bootstrap/templates/ISSUE_TEMPLATE/agent-task.yml").read_text(),
        ".github/pull_request_template.md": (ROOT / "bootstrap/templates/PULL_REQUEST_TEMPLATE.md").read_text(),
        ".github/workflows/ci.yml": expand(_workflow("ci", kit_ref)),
        ".github/workflows/agent.yml": expand(_workflow("agent", kit_ref)),
        ".github/workflows/release-please.yml": expand(_workflow("release-please", kit_ref)),
        ".claude/settings.json": json.dumps({"permissions": {"deny": ["Read(**/.env*)", "Write(.github/**)"]}}, indent=2) + "\n",
        ".claude/rules/repository.md": f"Follow launchpad-meta/{spec} and specs/03-conventions.md.\n",
        "release-please-config.json": json.dumps({"packages": {".": {"release-type": "simple"}}}) + "\n",
        ".release-please-manifest.json": '{".":"0.0.0"}\n',
        ".gitignore": ".env\n.env.*\n*.pem\n*.key\nnode_modules/\n.venv/\ntarget/\n",
        ".dockerignore": ".git\n.env*\nnode_modules\ntarget\n",
        ".pre-commit-config.yaml": "repos: []\n",
        "Makefile": ".PHONY: fmt lint test test-integration run\nfmt:\n\t@true\nlint:\n\t@true\ntest:\n\t@true\ntest-integration:\n\t@true\nrun:\n\t@echo 'implemented by milestone issue'\n",
        "Dockerfile": "FROM scratch AS build\nFROM scratch AS runtime\nUSER 65532:65532\nCOPY --from=build / /app\nENTRYPOINT [\"/app\"]\n",
        "test/README.md": "Integration tests are added with product behavior.\n",
    }
    layout = json.loads((ROOT / f"bootstrap/templates/{family}/layout.json").read_text())
    for raw in layout["paths"]:
        path = expand(raw)
        if path == "go.mod": tree[path] = f"module github.com/launch-pad-021/{name}\n\ngo 1.27\n"
        elif path == "Cargo.toml": tree[path] = f'[package]\nname = "{service}"\nversion = "0.0.0"\nedition = "2024"\n'
        elif path == "pyproject.toml": tree[path] = f'[project]\nname = "lp-{service}"\nversion = "0.0.0"\nrequires-python = ">=3.14"\n'
        elif path == "package.json": tree[path] = json.dumps({"name": f"@launchpad/{service}", "private": True, "engines": {"node": "26"}}, indent=2) + "\n"
        elif path == "tsconfig.json": tree[path] = '{"compilerOptions":{"strict":true,"noEmit":true}}\n'
        elif path == "next.config.mjs": tree[path] = "export default { output: 'standalone' };\n"
        else: tree[path] = ""
    if migrations:
        tree["migrations/README.md"] = f"{migrations} migrations are expand/contract and developer-reviewed.\n"
    return dict(sorted(tree.items()))


class Provisioner:
    def __init__(self, api, manifest: dict, org: str, visibility: str):
        if not ORG_RE.fullmatch(org): raise ConfigError("invalid organization")
        if visibility not in {"public", "private"}: raise ConfigError("visibility must be public or private")
        self.api, self.manifest, self.org, self.visibility = api, manifest, org, visibility

    def run(self, *, apply=False, selected=None, owner=None, kit_ref=None,
            ci_integration_id=None, review_integration_id=None, approved=False):
        entries = {e["name"]: e for e in self.manifest["repositories"] if e["mode"] == "create"}
        names = selected or list(entries)
        unknown = sorted(set(names) - set(entries))
        if unknown: raise ConfigError(f"repositories not in delivery manifest: {', '.join(unknown)}")
        if apply and (not approved or not owner or not SHA_RE.fullmatch(kit_ref or "") or
                      not isinstance(ci_integration_id, int) or ci_integration_id <= 0 or
                      not isinstance(review_integration_id, int) or review_integration_id <= 0):
            raise ConfigError("apply requires owner approval, final kit SHA, and positive check producer IDs")
        discovery = self.api.discover(self.org)
        if not discovery.get("complete"): raise ConfigError("organization discovery was incomplete")
        result = {"create": [], "resume": [], "noop": [], "applied": []}
        for name in names:
            state = discovery.get("repos", {}).get(name)
            if state is None: result["create"].append(name)
            elif state.get("visibility") != self.visibility:
                raise ConfigError(f"{name}: visibility mismatch")
            elif state.get("marker") != MARKER:
                raise ConfigError(f"{name}: existing repository is not owned by this provisioner")
            elif state.get("governed") is True: result["noop"].append(name)
            else: result["resume"].append(name)
        if apply:
            for name in result["create"] + result["resume"]:
                entry = entries[name]
                tree = render_repository(name, entry["template"], entry["milestone"], entry["spec"], entry.get("migrations"), kit_ref)
                tree = {path: content.replace("LP_OWNER_LOGIN", owner).replace("launch-pad-021", self.org)
                        for path, content in tree.items()}
                context = {"repo": name, "visibility": self.visibility, "owner": owner,
                           "kit_ref": kit_ref, "ci_integration_id": ci_integration_id,
                           "review_integration_id": review_integration_id,
                           "tree_hash": hashlib.sha256(json.dumps(tree, sort_keys=True).encode()).hexdigest(),
                           "marker": MARKER}
                start = "create" if name in result["create"] else "settings"
                order = ["create", "seed", "settings", "ruleset", "apps", "verify"]
                for kind in order[order.index(start):]: self.api.mutate({"kind": kind, **context})
                result["applied"].append(name)
        return result


class GhReadOnlyAdapter:
    """Live discovery adapter. Mutations are disabled until owner App policy is installed."""
    def __init__(self, journal: Path): self.journal = journal
    def _gh(self, endpoint: str):
        process = subprocess.run(["gh", "api", "--hostname", "github.com", endpoint],
                                 capture_output=True, text=True, timeout=30)
        if process.returncode: raise ConfigError("GitHub discovery failed")
        return json.loads(process.stdout)
    def discover(self, org):
        actual = self._gh(f"orgs/{org}")
        if actual.get("login", "").lower() != org.lower(): raise ConfigError("organization mismatch")
        repos, page = {}, 1
        while True:
            chunk = self._gh(f"orgs/{org}/repos?per_page=100&page={page}")
            for repo in chunk:
                repos[repo["name"]] = {"visibility": repo.get("visibility"), "marker": MARKER if MARKER in (repo.get("description") or "") else None,
                                             "governed": False, "stage": "discovered"}
            if len(chunk) < 100: break
            page += 1
        return {"complete": True, "repos": repos}
    def mutate(self, operation):
        raise ConfigError("live mutation adapter is disabled until Apps and ruleset producers are verified")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", required=True)
    parser.add_argument("--visibility", choices=("public", "private"), required=True)
    parser.add_argument("--repo", action="append")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approved", action="store_true")
    parser.add_argument("--owner")
    parser.add_argument("--kit-ref")
    parser.add_argument("--ci-integration-id", type=int)
    parser.add_argument("--review-integration-id", type=int)
    parser.add_argument("--journal", type=Path, default=Path.home() / ".local/state/launchpad/repositories.json")
    args = parser.parse_args(argv)
    if os.environ.get("LP_ORG") != args.org: raise ConfigError("--org must exactly match trusted LP_ORG")
    adapter = GhReadOnlyAdapter(args.journal)
    result = Provisioner(adapter, load_manifest(), args.org, args.visibility).run(
        apply=args.apply, selected=args.repo, owner=args.owner, kit_ref=args.kit_ref,
        ci_integration_id=args.ci_integration_id, review_integration_id=args.review_integration_id,
        approved=args.approved)
    print(json.dumps({"mode": "apply" if args.apply else "dry-run", **result}, indent=2))


if __name__ == "__main__":
    try: main()
    except (ConfigError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(f"create-repos: {exc}", file=sys.stderr)
        raise SystemExit(1)
