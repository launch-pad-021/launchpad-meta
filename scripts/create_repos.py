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
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "bootstrap/templates/repos.json"
MARKER = "launchpad-provision-v1"
FINAL_KIT_REF = "68d7c12e5543e15e0ec9d44421f7fec6dd4dfee2"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ORG_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


class ConfigError(RuntimeError):
    pass


class Journal:
    """Owner-local, atomic provisioning receipt; it never contains credentials."""
    def __init__(self, path: Path):
        self.path = path
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ConfigError("provisioning journal is unreadable") from exc
        else:
            self.data = {"schema": 1, "repositories": {}}
        if self.data.get("schema") != 1 or not isinstance(self.data.get("repositories"), dict):
            raise ConfigError("unsupported provisioning journal")

    def repo(self, name):
        return self.data["repositories"].get(name)

    def assert_identity(self, name, repo_id, visibility):
        current = self.repo(name)
        if current and (current.get("repo_id") != repo_id or current.get("visibility") != visibility):
            raise ConfigError(f"{name}: journal identity drift")

    def record(self, name, values):
        current = dict(self.repo(name) or {})
        current.update(values)
        self.data["repositories"][name] = current
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, raw = tempfile.mkstemp(prefix=".repositories-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.data, handle, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(raw, 0o600)
            os.replace(raw, self.path)
        finally:
            if os.path.exists(raw):
                os.unlink(raw)


def ruleset_payload(ci_integration_id: int, review_integration_id: int) -> dict:
    checks = [{"context": f"CI / {name}", "integration_id": ci_integration_id}
              for name in ("build", "lint", "types", "tests", "security", "contracts")]
    checks.append({"context": "agent-review / merge-gate", "integration_id": review_integration_id})
    return {
        "name": "Launchpad main governance", "target": "branch", "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
        "rules": [
            {"type": "deletion"}, {"type": "non_fast_forward"},
            {"type": "required_linear_history"},
            {"type": "pull_request", "parameters": {
                "allowed_merge_methods": ["squash"], "dismiss_stale_reviews_on_push": True,
                "require_code_owner_review": True, "require_last_push_approval": False,
                "required_approving_review_count": 1, "required_review_thread_resolution": True}},
            {"type": "required_status_checks", "parameters": {
                "do_not_enforce_on_create": False, "strict_required_status_checks_policy": True,
                "required_status_checks": checks}},
        ],
    }


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


def _workflow(name: str, kit_ref: str, family: str) -> str:
    target = {"ci": ".github/workflows/ci-{{FAMILY}}.yml", "agent": ".github/workflows/agent-implement.yml",
              "release-please": ".github/workflows/release.yml"}[name]
    uses = f"launch-pad-021/launchpad-agent-kit/{target}@{kit_ref}"
    if name == "ci":
        if family == "shared":
            jobs = "\n".join(
                f"  {check}:\n    name: CI / {check}\n    runs-on: ubuntu-24.04\n    steps:\n"
                f"      - uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803 # v6\n"
                f"      - run: make {'test' if check in {'tests', 'contracts'} else 'lint'}"
                for check in ("build", "lint", "types", "tests", "security", "contracts"))
            return "name: CI\non:\n  pull_request:\n  push:\n    branches: [main]\npermissions:\n  contents: read\njobs:\n" + jobs + "\n"
        return f"""name: CI
on:
  pull_request:
  push:
    branches: [main]
permissions: {{}}
jobs:
  call:
    uses: {uses} # reviewed immutable agent-kit revision
"""
    if name == "agent":
        return f"""name: Agent
run-name: agent-${{{{ github.event.client_payload.dispatch_id }}}}
on:
  repository_dispatch:
    types: [lp-implement]
permissions: {{}}
jobs:
  call:
    uses: {uses} # reviewed immutable agent-kit revision
    with:
      issue_number: ${{{{ fromJSON(github.event.client_payload.issue) }}}}
      lease_id: ${{{{ github.event.client_payload.dispatch_id }}}}
      attempt: ${{{{ fromJSON(github.event.client_payload.attempt) }}}}
      max_attempts: 3
      model: sonnet
      max_turns: 60
      max_budget_usd: ${{{{ fromJSON(github.event.client_payload.max_budget_usd) }}}}
      kit_ref: {kit_ref}
    secrets:
      ANTHROPIC_API_KEY: ${{{{ secrets.ANTHROPIC_API_KEY }}}}
      LP_DEV_APP_ID: ${{{{ secrets.LP_DEV_APP_ID }}}}
      LP_DEV_APP_KEY: ${{{{ secrets.LP_DEV_APP_KEY }}}}
"""
    return f"""name: Release
on:
  push:
    branches: [main]
  workflow_dispatch:
permissions: {{}}
jobs:
  call:
    uses: {uses} # reviewed immutable agent-kit revision
    with:
      service: {{{{SERVICE}}}}
      kit_ref: {kit_ref}
      max_budget_usd: ${{{{ fromJSON(vars.LP_AGENT_RELEASE_BUDGET_USD) }}}}
    secrets:
      ANTHROPIC_API_KEY: ${{{{ secrets.ANTHROPIC_API_KEY }}}}
      LP_RELEASE_APP_ID: ${{{{ secrets.LP_RELEASE_APP_ID }}}}
      LP_RELEASE_APP_KEY: ${{{{ secrets.LP_RELEASE_APP_KEY }}}}
"""


def render_repository(name: str, family: str, milestone: str, spec: str,
                      migrations: str | None = None, kit_ref: str = FINAL_KIT_REF) -> dict[str, str]:
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
        ".github/workflows/ci.yml": expand(_workflow("ci", kit_ref, family)),
        ".github/workflows/agent.yml": expand(_workflow("agent", kit_ref, family)),
        ".github/workflows/release-please.yml": expand(_workflow("release-please", kit_ref, family)),
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
            elif state.get("stage") == "discovered":
                raise ConfigError(f"{name}: marker exists without an owner-local provisioning receipt")
            elif state.get("governed") is True: result["noop"].append(name)
            else: result["resume"].append(name)
        if apply:
            required_roles = {"dev", "review"}
            for name in names:
                entry = entries[name]
                if name == "launchpad-infra": required_roles.add("release")
                if entry.get("profile") == "service": required_roles.add("scm")
            if hasattr(self.api, "prepare_apply"):
                self.api.prepare_apply(required_roles)
            for name in result["create"] + result["resume"]:
                entry = entries[name]
                tree = render_repository(name, entry["template"], entry["milestone"], entry["spec"], entry.get("migrations"), kit_ref)
                tree = {path: content.replace("LP_OWNER_LOGIN", owner).replace("launch-pad-021", self.org)
                        for path, content in tree.items()}
                context = {"repo": name, "visibility": self.visibility, "owner": owner,
                           "kit_ref": kit_ref, "ci_integration_id": ci_integration_id,
                           "review_integration_id": review_integration_id,
                           "tree_hash": hashlib.sha256(json.dumps(tree, sort_keys=True).encode()).hexdigest(),
                           "marker": MARKER, "tree": tree,
                           "app_roles": (["dev", "review", "release"] if name == "launchpad-infra"
                                         else ["dev", "review", "scm"] if entry.get("profile") == "service"
                                         else ["dev", "review"])}
                observed = discovery.get("repos", {}).get(name) or {}
                next_stage = {"created": "seed", "seeded": "settings", "settings": "ruleset",
                              "ruleset": "apps", "apps": "verify", "verified": "verify"}
                start = "create" if name in result["create"] else next_stage.get(observed.get("stage"), "settings")
                order = ["create", "seed", "settings", "ruleset", "apps", "verify"]
                for kind in order[order.index(start):]: self.api.mutate({"kind": kind, **context})
                result["applied"].append(name)
        return result


class GhAdapter:
    """Owner-session GitHub adapter with readback after every bounded mutation."""
    def __init__(self, journal: Path, *, apply=False, installations=None, runner=subprocess.run):
        self.journal = Journal(journal)
        self.apply = apply
        self.installations = dict(installations or {})
        self.runner = runner
        self.org = None
        self.prepared = False

    def _run(self, argv, *, cwd=None, input_text=None, timeout=45, check=True):
        process = self.runner(argv, cwd=cwd, input=input_text, capture_output=True,
                              text=True, timeout=timeout)
        if check and process.returncode:
            raise ConfigError("external command failed; inspect local owner terminal")
        return process

    def _gh(self, endpoint: str, *, method="GET", payload=None):
        command = ["gh", "api", "--hostname", "github.com"]
        if method != "GET": command += ["--method", method]
        if payload is not None: command += ["--input", "-"]
        command.append(endpoint)
        process = self._run(command, input_text=(json.dumps(payload) if payload is not None else None), check=False)
        if process.returncode:
            raise ConfigError("GitHub API request failed; state must be rediscovered")
        if not process.stdout.strip(): return None
        try: return json.loads(process.stdout)
        except json.JSONDecodeError as exc: raise ConfigError("GitHub returned malformed JSON") from exc

    def _repo(self, name):
        return self._gh(f"repos/{self.org}/{name}")

    def discover(self, org):
        self.org = org
        actual = self._gh(f"orgs/{org}")
        if actual.get("login", "").lower() != org.lower(): raise ConfigError("organization mismatch")
        repos, page = {}, 1
        while True:
            chunk = self._gh(f"orgs/{org}/repos?per_page=100&page={page}")
            for repo in chunk:
                name = repo["name"]
                marker = MARKER if MARKER in (repo.get("description") or "") else None
                receipt = self.journal.repo(name)
                if receipt:
                    self.journal.assert_identity(name, repo.get("id"), repo.get("visibility"))
                governed = bool(receipt and receipt.get("stage") == "verified" and self._governed(repo, receipt))
                repos[name] = {"id": repo.get("id"), "visibility": repo.get("visibility"),
                               "marker": marker, "governed": governed,
                               "stage": receipt.get("stage", "discovered") if receipt else "discovered"}
            if len(chunk) < 100: break
            page += 1
        return {"complete": True, "repos": repos}

    def _governed(self, repo, receipt):
        if (repo.get("default_branch") != "main" or not repo.get("allow_squash_merge") or
                repo.get("allow_merge_commit") or repo.get("allow_rebase_merge") or repo.get("allow_auto_merge")):
            return False
        rules = self._gh(f"repos/{self.org}/{repo['name']}/rulesets?includes_parents=false")
        if sum(item.get("name") == "Launchpad main governance" for item in rules) != 1: return False
        errors = self._gh(f"repos/{self.org}/{repo['name']}/codeowners/errors")
        if errors.get("errors"): return False
        for role in receipt.get("app_roles", []):
            installation = self.installations.get(role)
            if not installation: return False
            member = self._gh(f"user/installations/{installation}/repositories/{repo['id']}")
            if member.get("id") != repo.get("id"): return False
        return True

    def mutate(self, operation):
        if not self.apply: raise ConfigError("mutation requested from read-only adapter")
        if not self.prepared: raise ConfigError("App policy was not verified before mutation")
        kind = operation["kind"]
        getattr(self, f"_{kind}")(operation)

    def prepare_apply(self, required_roles):
        expected = {
            "dev": ("launchpad-dev", {"contents": "write", "issues": "write", "pull_requests": "write", "metadata": "read"}),
            "review": ("launchpad-review", {"contents": "read", "pull_requests": "write", "statuses": "write", "metadata": "read"}),
            "release": ("launchpad-release", {"contents": "write", "pull_requests": "write", "metadata": "read"}),
            "scm": ("launchpad-scm", {"contents": "read", "metadata": "read"}),
        }
        if set(required_roles) - set(self.installations):
            raise ConfigError("all required App installation IDs must be supplied before apply")
        found, page = {}, 1
        while True:
            chunk = self._gh(f"orgs/{self.org}/installations?per_page=100&page={page}")
            items = chunk.get("installations", []) if isinstance(chunk, dict) else chunk
            for item in items:
                found[item.get("id")] = item
            if isinstance(chunk, dict):
                if len(found) >= chunk.get("total_count", len(found)): break
            elif len(chunk) < 100: break
            page += 1
        for role in required_roles:
            item = found.get(self.installations[role])
            slug, permissions = expected[role]
            if (not item or item.get("app_slug") != slug or item.get("repository_selection") != "selected" or
                    item.get("suspended_at") is not None or item.get("permissions") != permissions):
                raise ConfigError(f"{role} App installation policy mismatch")
        self.prepared = True

    def _record(self, op, stage, **extra):
        repo = self._repo(op["repo"])
        if repo.get("full_name") != f"{self.org}/{op['repo']}" or repo.get("visibility") != op["visibility"]:
            raise ConfigError(f"{op['repo']}: readback identity mismatch")
        if MARKER not in (repo.get("description") or ""):
            raise ConfigError(f"{op['repo']}: provisioning marker missing")
        self.journal.assert_identity(op["repo"], repo.get("id"), repo.get("visibility"))
        self.journal.record(op["repo"], {"repo_id": repo.get("id"), "visibility": repo.get("visibility"),
                                         "marker": MARKER, "stage": stage,
                                         "kit_ref": op["kit_ref"], "tree_hash": op["tree_hash"], **extra})

    def _create(self, op):
        payload = {"name": op["repo"], "description": f"{MARKER}; managed by launchpad-meta",
                   "visibility": op["visibility"], "auto_init": False,
                   "has_issues": True, "has_projects": False, "has_wiki": False,
                   "allow_squash_merge": True, "allow_merge_commit": False,
                   "allow_rebase_merge": False, "allow_auto_merge": False,
                   "delete_branch_on_merge": True}
        try:
            self._gh(f"orgs/{self.org}/repos", method="POST", payload=payload)
        except ConfigError:
            repo = self._repo(op["repo"])
            if MARKER not in (repo.get("description") or "") or repo.get("visibility") != op["visibility"]:
                raise
        self._record(op, "created")

    def _seed(self, op):
        with tempfile.TemporaryDirectory(prefix="launchpad-seed-") as raw:
            root = Path(raw)
            for relative, content in op["tree"].items():
                path = Path(relative)
                if path.is_absolute() or ".." in path.parts: raise ConfigError("unsafe rendered path")
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            for command in (["git", "init", "-b", "main"], ["git", "config", "user.name", "Launchpad Provisioner"],
                            ["git", "config", "user.email", "noreply@launchpad.invalid"], ["git", "add", "--all"],
                            ["git", "commit", "-m", "chore: seed governed repository"]):
                self._run(command, cwd=root)
            tree_sha = self._run(["git", "rev-parse", "HEAD^{tree}"], cwd=root).stdout.strip()
            remote = f"https://github.com/{self.org}/{op['repo']}.git"
            pushed = self._run(["git", "push", remote, "HEAD:refs/heads/main"], cwd=root,
                               timeout=120, check=False)
            if pushed.returncode:
                branch = self._gh(f"repos/{self.org}/{op['repo']}/branches/main")
                commit = self._gh(f"repos/{self.org}/{op['repo']}/git/commits/{branch['commit']['sha']}")
                if commit.get("tree", {}).get("sha") != tree_sha: raise ConfigError("seed push outcome is ambiguous")
        self._record(op, "seeded", git_tree=tree_sha)

    def _settings(self, op):
        payload = {"default_branch": "main", "allow_squash_merge": True, "allow_merge_commit": False,
                   "allow_rebase_merge": False, "allow_auto_merge": False, "delete_branch_on_merge": True}
        self._gh(f"repos/{self.org}/{op['repo']}", method="PATCH", payload=payload)
        repo = self._repo(op["repo"])
        expected = {"default_branch": "main", "allow_squash_merge": True, "allow_merge_commit": False,
                    "allow_rebase_merge": False, "allow_auto_merge": False}
        if any(repo.get(key) != value for key, value in expected.items()):
            raise ConfigError("repository settings readback failed")
        self._record(op, "settings")

    def _ruleset(self, op):
        expected = ruleset_payload(op["ci_integration_id"], op["review_integration_id"])
        existing = self._gh(f"repos/{self.org}/{op['repo']}/rulesets?includes_parents=false")
        matches = [item for item in existing if item.get("name") == expected["name"]]
        if len(matches) > 1: raise ConfigError("duplicate Launchpad rulesets")
        if matches:
            detail = self._gh(f"repos/{self.org}/{op['repo']}/rulesets/{matches[0]['id']}")
            for key in ("target", "enforcement", "conditions", "rules"):
                if detail.get(key) != expected.get(key): raise ConfigError("existing ruleset differs from approved policy")
        else:
            self._gh(f"repos/{self.org}/{op['repo']}/rulesets", method="POST", payload=expected)
        self._record(op, "ruleset")

    def _apps(self, op):
        missing = sorted(set(op["app_roles"]) - set(self.installations))
        if missing: raise ConfigError("missing verified App installation IDs: " + ", ".join(missing))
        repo = self._repo(op["repo"])
        for role in op["app_roles"]:
            installation = self.installations[role]
            self._gh(f"user/installations/{installation}/repositories/{repo['id']}", method="PUT")
            member = self._gh(f"user/installations/{installation}/repositories/{repo['id']}")
            if member.get("id") != repo.get("id"):
                raise ConfigError(f"{role} App membership readback failed")
        self._record(op, "apps", app_roles=op["app_roles"])

    def _verify(self, op):
        repo = self._repo(op["repo"])
        if repo.get("default_branch") != "main" or not repo.get("allow_squash_merge"):
            raise ConfigError("repository verification failed")
        if repo.get("allow_merge_commit") or repo.get("allow_rebase_merge") or repo.get("allow_auto_merge"):
            raise ConfigError("unsafe merge settings remain enabled")
        errors = self._gh(f"repos/{self.org}/{op['repo']}/codeowners/errors")
        if errors.get("errors"): raise ConfigError("CODEOWNERS has errors")
        rules = self._gh(f"repos/{self.org}/{op['repo']}/rulesets?includes_parents=false")
        if sum(item.get("name") == "Launchpad main governance" for item in rules) != 1:
            raise ConfigError("governance ruleset verification failed")
        self._record(op, "verified", app_roles=op["app_roles"])


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", required=True)
    parser.add_argument("--visibility", choices=("public", "private"), required=True)
    parser.add_argument("--repo", action="append")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approved", action="store_true")
    parser.add_argument("--owner")
    parser.add_argument("--kit-ref", default=FINAL_KIT_REF)
    parser.add_argument("--ci-integration-id", type=int)
    parser.add_argument("--review-integration-id", type=int)
    parser.add_argument("--app-installation", action="append", default=[], metavar="ROLE=ID")
    parser.add_argument("--journal", type=Path, default=Path.home() / ".local/state/launchpad/repositories.json")
    args = parser.parse_args(argv)
    if os.environ.get("LP_ORG") != args.org: raise ConfigError("--org must exactly match trusted LP_ORG")
    installations = {}
    for raw in args.app_installation:
        role, separator, value = raw.partition("=")
        if not separator or role not in {"dev", "review", "release", "scm"} or not value.isdigit() or int(value) <= 0:
            raise ConfigError("--app-installation must be dev|review|release|scm=positive-id")
        installations[role] = int(value)
    adapter = GhAdapter(args.journal, apply=args.apply, installations=installations)
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
