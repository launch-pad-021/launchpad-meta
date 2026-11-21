#!/usr/bin/env python3
"""Deterministic GitHub publishers for planner, metrics and weekly audits."""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    from agent_control import PolicyError, validate_plan_manifest
    from agent_metrics import FIELDS, normalized_row
    from weekly_audits import fingerprint
except ModuleNotFoundError:  # Imported as scripts.github_publish by unit tests.
    from scripts.agent_control import PolicyError, validate_plan_manifest
    from scripts.agent_metrics import FIELDS, normalized_row
    from scripts.weekly_audits import fingerprint


class Publisher:
    def __init__(self, org: str, token: str | None = None, runner=subprocess.run):
        self.org = org
        self.token = os.environ.get("GH_TOKEN") if token is None else token
        if not self.token:
            raise PolicyError("missing-github-token")
        self.runner = runner

    def api(self, endpoint, method="GET", payload=None, *, allow_not_found=False):
        command = ["gh", "api", "--hostname", "github.com", "--method", method, endpoint]
        data = None
        if payload is not None:
            command += ["--input", "-"]
            data = json.dumps(payload, separators=(",", ":"))
        process = self.runner(command, input=data, capture_output=True, text=True, timeout=30,
                              env={**os.environ, "GH_TOKEN": self.token})
        if process.returncode and allow_not_found and "HTTP 404" in process.stderr:
            return None
        if process.returncode:
            raise PolicyError("github-api-failed")
        if not process.stdout.strip():
            return None
        try:
            return json.loads(process.stdout)
        except json.JSONDecodeError as error:
            raise PolicyError("github-api-malformed") from error

    def enabled(self):
        result = self.api(f"orgs/{self.org}/actions/variables/AGENTS_ENABLED")
        return isinstance(result, dict) and result.get("value") == "true"

    def upsert_pr_file(self, *, branch: str, path: str, content: str, title: str):
        if not self.enabled():
            raise PolicyError("kill-switch")
        repo = f"{self.org}/launchpad-meta"
        main = self.api(f"repos/{repo}/git/ref/heads/main")
        base_sha = main.get("object", {}).get("sha") if isinstance(main, dict) else None
        if not isinstance(base_sha, str):
            raise PolicyError("main-ref-malformed")
        ref = self.api(f"repos/{repo}/git/ref/heads/{branch}", allow_not_found=True)
        if ref is None:
            self.api(f"repos/{repo}/git/refs", "POST", {"ref": f"refs/heads/{branch}", "sha": base_sha})
        existing = self.api(f"repos/{repo}/contents/{path}?ref={branch}", allow_not_found=True)
        payload = {"message": title, "branch": branch,
                   "content": base64.b64encode(content.encode()).decode()}
        if isinstance(existing, dict) and isinstance(existing.get("sha"), str):
            payload["sha"] = existing["sha"]
            current = base64.b64decode(existing.get("content", "")).decode(errors="strict")
            if current == content:
                return {"changed": False, "pr": None}
        self.api(f"repos/{repo}/contents/{path}", "PUT", payload)
        pulls = self.api(f"repos/{repo}/pulls?state=open&head={self.org}:{branch}&base=main")
        if isinstance(pulls, list) and pulls:
            return {"changed": True, "pr": pulls[0].get("html_url")}
        pr = self.api(f"repos/{repo}/pulls", "POST", {"title": title, "head": branch,
                                                       "base": "main", "body": "Deterministic control-plane proposal."})
        return {"changed": True, "pr": pr.get("html_url") if isinstance(pr, dict) else None}

    def publish_findings(self, findings):
        if not self.enabled():
            raise PolicyError("kill-switch")
        repo = f"{self.org}/launchpad-meta"
        existing = self.api(f"repos/{repo}/issues?state=all&labels=agent:audit&per_page=100")
        bodies = [issue.get("body", "") for issue in existing] if isinstance(existing, list) else []
        created = []
        for finding in findings:
            key = fingerprint(finding)
            marker = f"<!-- launchpad-audit-v1:{key} -->"
            if any(marker in body for body in bodies):
                continue
            body = marker + "\n" + finding["summary"] + "\n\nPath: `" + finding["path"] + "`"
            issue = self.api(f"repos/{repo}/issues", "POST", {
                "title": f"audit: {finding['auditor']} {finding['rule']}",
                "body": body, "labels": ["agent:audit"]})
            created.append(issue.get("html_url") if isinstance(issue, dict) else None)
        return created


def metrics_csv(records):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(sorted((normalized_row(record) for record in records),
                            key=lambda row: (row["date"], row["repo"], row["issue"])))
    return output.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("manifest", type=Path)
    metrics = sub.add_parser("metrics")
    metrics.add_argument("results", type=Path)
    audits = sub.add_parser("audits")
    audits.add_argument("findings", type=Path)
    args = parser.parse_args(argv)
    try:
        publisher = Publisher(args.org)
        if args.command == "plan":
            manifest = json.loads(args.manifest.read_text())
            validate_plan_manifest(manifest)
            milestone = manifest["milestone"]
            result = publisher.upsert_pr_file(branch=f"plan/{milestone}", path=f"plans/{milestone}.json",
                content=json.dumps(manifest, indent=2, sort_keys=True) + "\n", title=f"plan: {milestone}")
        elif args.command == "metrics":
            records = json.loads(args.results.read_text())
            result = publisher.upsert_pr_file(branch="agent/metrics", path="metrics/agent-runs.csv",
                content=metrics_csv(records), title="chore: update agent metrics")
        else:
            findings = json.loads(args.findings.read_text())
            result = {"created": publisher.publish_findings(findings)}
    except (OSError, ValueError, json.JSONDecodeError, PolicyError) as error:
        print(json.dumps({"error": str(error)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
