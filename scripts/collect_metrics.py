#!/usr/bin/env python3
"""Collect bounded, redacted workflow-run facts from the Launchpad installation."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys


def api(endpoint):
    process = subprocess.run(["gh", "api", "--hostname", "github.com", endpoint],
                             capture_output=True, text=True, timeout=30)
    if process.returncode:
        raise RuntimeError("github-read-failed")
    return json.loads(process.stdout)


def main():
    org = os.environ.get("LP_ORG", "")
    if not org or not os.environ.get("GH_TOKEN"):
        print("missing metrics configuration", file=sys.stderr)
        return 2
    repos = api(f"orgs/{org}/repos?per_page=100")
    if not isinstance(repos, list):
        return 2
    records = []
    for repo in repos:
        name = repo.get("name") if isinstance(repo, dict) else None
        if not isinstance(name, str) or not name.startswith("launchpad-"):
            continue
        runs = api(f"repos/{org}/{name}/actions/runs?per_page=100")
        for run in runs.get("workflow_runs", []) if isinstance(runs, dict) else []:
            created, updated = run.get("created_at"), run.get("updated_at")
            if not isinstance(created, str) or not isinstance(updated, str):
                continue
            try:
                start = dt.datetime.fromisoformat(created.replace("Z", "+00:00"))
                end = dt.datetime.fromisoformat(updated.replace("Z", "+00:00"))
            except ValueError:
                continue
            records.append({"version": 1, "date": start.date().isoformat(), "repo": name,
                "issue": "", "result": run.get("conclusion") or run.get("status"),
                "duration_seconds": max(0, int((end - start).total_seconds())),
                "cost_micros": None, "reason": run.get("event", "")})
    print(json.dumps(records, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
