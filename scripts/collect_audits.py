#!/usr/bin/env python3
"""Collect deterministic repository-governance findings without model write access."""

import json
import os
import subprocess
import sys


def main():
    org = os.environ.get("LP_ORG", "")
    if not org or not os.environ.get("GH_TOKEN"):
        return 2
    process = subprocess.run(["gh", "api", "--hostname", "github.com",
        f"orgs/{org}/repos?per_page=100"], capture_output=True, text=True, timeout=30)
    if process.returncode:
        return 2
    repos = json.loads(process.stdout)
    if not isinstance(repos, list):
        return 2
    findings = []
    for repo in repos:
        if not isinstance(repo, dict) or not str(repo.get("name", "")).startswith("launchpad-"):
            continue
        if repo.get("archived"):
            findings.append({"auditor": "spec-drift-auditor", "repo": repo["name"],
                "rule": "repository-active", "path": ".", "summary": "Declared Launchpad repository is archived."})
        if repo.get("default_branch") != "main":
            findings.append({"auditor": "security-auditor", "repo": repo["name"],
                "rule": "default-branch", "path": ".github", "summary": "Default branch is not main."})
    print(json.dumps(findings, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
