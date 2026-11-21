#!/usr/bin/env python3
"""Deterministic, fail-closed policy for Launchpad control-plane workflows.

The module intentionally contains no GitHub client.  Network adapters must supply
fresh, typed snapshots and are kept out of credential-free dry runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from typing import Any


MAX_IMPLEMENTERS = 3
MAX_IMPLEMENTATION_ATTEMPTS = 3


class PolicyError(ValueError):
    pass


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PolicyError(f"invalid-{name}")
    return value


def _handoff(result: dict[str, Any], snapshot: dict[str, Any], reason: str) -> None:
    event_id = str(snapshot.get("event_id", "cycle"))
    key = f"{event_id}:{reason}"
    if key not in set(snapshot.get("handoff_keys", [])):
        result["handoffs"].append({"key": key, "reason": reason})


def _lease_id(issue_id: str, ordinal: int) -> str:
    material = f"agent-result-v1:implement:{issue_id}:{ordinal}".encode()
    return hashlib.sha256(material).hexdigest()[:24]


def plan_cycle(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic dispatch intents without performing side effects."""
    result: dict[str, Any] = {
        "version": 1, "dispatches": [], "skips": {}, "handoffs": [],
        "stop_reason": None,
    }
    if snapshot.get("enabled") is not True:
        result["stop_reason"] = "kill-switch"
        return result

    try:
        daily = _integer(snapshot.get("daily_budget_micros"), "daily-budget", minimum=1)
        per_run = _integer(snapshot.get("per_run_budget_micros"), "per-run-budget", minimum=1)
        spent = _integer(snapshot.get("spent_micros"), "spent")
    except PolicyError as error:
        result["stop_reason"] = str(error)
        _handoff(result, snapshot, str(error))
        return result
    if per_run > daily:
        result["stop_reason"] = "per-run-exceeds-daily"
        _handoff(result, snapshot, result["stop_reason"])
        return result
    if snapshot.get("errors"):
        result["stop_reason"] = "partial-api"
        _handoff(result, snapshot, "partial-api")
        return result
    if snapshot.get("stale") is True:
        result["stop_reason"] = "stale-project-state"
        _handoff(result, snapshot, result["stop_reason"])
        return result

    items = snapshot.get("items")
    active = snapshot.get("active")
    if not isinstance(items, list) or not isinstance(active, list):
        result["stop_reason"] = "malformed-snapshot"
        _handoff(result, snapshot, result["stop_reason"])
        return result
    if any(not isinstance(item, dict) or not item.get("id") for item in items):
        result["stop_reason"] = "malformed-item"
        _handoff(result, snapshot, result["stop_reason"])
        return result
    item_by_id = {str(item["id"]): item for item in items}
    if len(item_by_id) != len(items):
        result["stop_reason"] = "duplicate-item"
        _handoff(result, snapshot, result["stop_reason"])
        return result
    if any(isinstance(item.get("position"), bool) or not isinstance(item.get("position"), int) for item in items):
        result["stop_reason"] = "invalid-position"
        _handoff(result, snapshot, result["stop_reason"])
        return result

    unowned = {
        item_id for item_id, item in item_by_id.items()
        if item.get("status") == "In progress" and item_id not in set(map(str, active))
    }
    occupied = len(set(map(str, active)) | unowned)
    slots = max(0, MAX_IMPLEMENTERS - occupied)
    reservations = snapshot.get("reservations", [])
    if not isinstance(reservations, list) or any(not isinstance(x, dict) for x in reservations):
        result["stop_reason"] = "malformed-reservations"
        _handoff(result, snapshot, result["stop_reason"])
        return result
    try:
        outstanding = sum(
            _integer(x.get("reserved_micros", 0), "reservation")
            for x in reservations if x.get("status") not in {"completed", "released"}
        )
    except PolicyError as error:
        result["stop_reason"] = str(error)
        _handoff(result, snapshot, str(error))
        return result
    available = daily - spent - outstanding

    ordered = sorted(item_by_id.items(), key=lambda pair: (pair[1].get("position", 2**63), pair[0]))
    for issue_id, item in ordered:
        if item.get("status") != "Ready":
            continue
        labels = item.get("labels")
        if not isinstance(labels, list) or "agent:task" not in labels:
            result["skips"][issue_id] = "not-agent-task"
            continue
        if {"agent:hold", "agent:blocked"}.intersection(labels):
            result["skips"][issue_id] = "held-or-blocked"
            continue
        if item.get("fields_complete") is not True:
            result["skips"][issue_id] = "definition-of-ready"
            continue
        attempts = item.get("attempts")
        if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 0:
            result["skips"][issue_id] = "invalid-attempts"
            continue
        if attempts >= MAX_IMPLEMENTATION_ATTEMPTS:
            result["skips"][issue_id] = "retry-limit"
            continue
        if item.get("risk", "low") == "high" and item.get("developer_ack") is not True:
            result["skips"][issue_id] = "high-risk-unacknowledged"
            continue
        dependencies = item.get("dependencies")
        if not isinstance(dependencies, list):
            result["skips"][issue_id] = "dependency-malformed"
            continue
        unknown = [str(dep) for dep in dependencies if str(dep) not in item_by_id]
        if unknown:
            result["skips"][issue_id] = "dependency-unknown"
            continue
        if any(item_by_id[str(dep)].get("status") != "Done" for dep in dependencies):
            result["skips"][issue_id] = "dependency-incomplete"
            continue
        if slots <= 0:
            result["skips"][issue_id] = "concurrency-limit"
            continue
        if available < per_run:
            result["skips"][issue_id] = "budget-exhausted"
            continue
        ordinal = attempts + 1
        result["dispatches"].append({
            "version": 1,
            "issue_id": issue_id,
            "stage": "implement",
            "ordinal": ordinal,
            "reserved_micros": per_run,
            "dispatch_id": _lease_id(issue_id, ordinal),
            "repo": item.get("repo"),
            "issue_number": item.get("issue_number"),
            "project_item_id": item.get("project_item_id"),
        })
        slots -= 1
        available -= per_run
    if any(reason == "budget-exhausted" for reason in result["skips"].values()):
        _handoff(result, snapshot, "budget-exhausted")
    return result


class DryRunAdapter:
    """Sentinel adapter: any mutation is a policy failure."""
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def enabled(self) -> bool:
        return True

    def reserve(self, intent: dict[str, Any]) -> None:
        raise PolicyError("dry-run-mutation-denied")

    def dispatch(self, intent: dict[str, Any]) -> None:
        raise PolicyError("dry-run-mutation-denied")


class GitHubAdapter:
    """Narrow, idempotent GitHub mutation boundary used only after policy passes."""

    marker = "<!-- launchpad-control-v1:"

    def __init__(self, *, org: str, project_id: str, status_field_id: str,
                 in_progress_option_id: str, control_issue: int,
                 token: str | None = None, runner=subprocess.run) -> None:
        required = (org, project_id, status_field_id, in_progress_option_id)
        if not all(isinstance(value, str) and value for value in required):
            raise PolicyError("missing-live-config")
        if not isinstance(control_issue, int) or control_issue < 1:
            raise PolicyError("invalid-control-issue")
        self.org = org
        self.project_id = project_id
        self.status_field_id = status_field_id
        self.in_progress_option_id = in_progress_option_id
        self.control_issue = control_issue
        self.token = os.environ.get("GH_TOKEN") if token is None else token
        if not self.token:
            raise PolicyError("missing-github-token")
        self.runner = runner
        self._records: set[str] | None = None
        self.attempt_counts: dict[str, int] = {}

    def _api(self, endpoint: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
        command = ["gh", "api", "--hostname", "github.com", "--method", method, endpoint]
        data = None
        if payload is not None:
            command += ["--input", "-"]
            data = json.dumps(payload, separators=(",", ":"))
        process = self.runner(command, input=data, capture_output=True, text=True,
                              timeout=30, env={**os.environ, "GH_TOKEN": self.token})
        if process.returncode:
            raise PolicyError("github-api-failed")
        if not process.stdout.strip():
            return None
        try:
            return json.loads(process.stdout)
        except json.JSONDecodeError as error:
            raise PolicyError("github-api-malformed") from error

    def _graphql(self, query: str, variables: dict[str, Any]) -> Any:
        response = self._api("graphql", method="POST", payload={"query": query, "variables": variables})
        if not isinstance(response, dict) or response.get("errors") or not isinstance(response.get("data"), dict):
            raise PolicyError("github-graphql-failed")
        return response["data"]

    def enabled(self) -> bool:
        response = self._api(f"orgs/{self.org}/actions/variables/AGENTS_ENABLED")
        return isinstance(response, dict) and response.get("value") == "true"

    def _load_records(self) -> set[str]:
        if self._records is None:
            self._records = set()
            page = 1
            while True:
                comments = self._api(
                    f"repos/{self.org}/launchpad-meta/issues/{self.control_issue}/comments?per_page=100&page={page}"
                )
                if not isinstance(comments, list):
                    raise PolicyError("control-ledger-malformed")
                for comment in comments:
                    body = comment.get("body", "") if isinstance(comment, dict) else ""
                    match = re.search(r"<!-- launchpad-control-v1:([0-9a-f]{24}):(reserved|sending|sent) -->", body)
                    if match:
                        self._records.add(f"{match.group(1)}:{match.group(2)}")
                        issue = re.search(r"issue `([^`]+)`", body)
                        if issue and match.group(2) == "reserved":
                            self.attempt_counts[issue.group(1)] = self.attempt_counts.get(issue.group(1), 0) + 1
                if len(comments) < 100:
                    break
                page += 1
        return self._records

    def _record(self, intent: dict[str, Any], phase: str) -> bool:
        key = f"{intent['dispatch_id']}:{phase}"
        records = self._load_records()
        if key in records:
            return False
        body = (f"{self.marker}{key} -->\n"
                f"Agent lease `{intent['dispatch_id']}` {phase}; issue `{intent['issue_id']}`, "
                f"attempt {intent['ordinal']}.")
        self._api(f"repos/{self.org}/launchpad-meta/issues/{self.control_issue}/comments",
                  method="POST", payload={"body": body})
        records.add(key)
        return True

    def reserve(self, intent: dict[str, Any]) -> None:
        for field in ("repo", "issue_number", "project_item_id"):
            if not intent.get(field):
                raise PolicyError("dispatch-target-missing")
        if self.enabled() is not True:
            raise PolicyError("kill-switch")
        if not self._record(intent, "reserved"):
            return
        if self.enabled() is not True:
            raise PolicyError("kill-switch")
        mutation = """mutation($project:ID!,$item:ID!,$field:ID!,$option:String!){
          updateProjectV2ItemFieldValue(input:{projectId:$project,itemId:$item,fieldId:$field,
            value:{singleSelectOptionId:$option}}){projectV2Item{id}}}"""
        self._graphql(mutation, {"project": self.project_id, "item": intent["project_item_id"],
                                  "field": self.status_field_id, "option": self.in_progress_option_id})

    def dispatch(self, intent: dict[str, Any]) -> None:
        sent_key = f"{intent['dispatch_id']}:sent"
        sending_key = f"{intent['dispatch_id']}:sending"
        if {sent_key, sending_key}.intersection(self._load_records()):
            return
        self._record(intent, "sending")
        if self.enabled() is not True:
            raise PolicyError("kill-switch")
        payload = {"event_type": "lp-implement", "client_payload": {
            "version": 1, "issue": intent["issue_number"], "dispatch_id": intent["dispatch_id"]}}
        self._api(f"repos/{self.org}/{intent['repo']}/dispatches", method="POST", payload=payload)
        self._record(intent, "sent")


def execute_cycle(snapshot: dict[str, Any], adapter: Any, *, dry_run: bool) -> dict[str, Any]:
    result = plan_cycle(snapshot)
    if dry_run or not result["dispatches"]:
        return result
    for intent in result["dispatches"]:
        if adapter.enabled() is not True:
            result["stop_reason"] = "kill-switch"
            break
        adapter.reserve(intent)
        if adapter.enabled() is not True:
            result["stop_reason"] = "kill-switch"
            break
        adapter.dispatch(intent)
    return result


def validate_plan_manifest(manifest: dict[str, Any]) -> list[str]:
    if manifest.get("version") != 1 or not isinstance(manifest.get("milestone"), str):
        raise PolicyError("invalid-plan-header")
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise PolicyError("invalid-plan-tasks")
    by_id: dict[str, dict[str, Any]] = {}
    for task in tasks:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str):
            raise PolicyError("invalid-task")
        if task["id"] in by_id or not isinstance(task.get("repo"), str) or "," in task["repo"]:
            raise PolicyError("invalid-task-identity")
        if not isinstance(task.get("depends_on"), list):
            raise PolicyError("invalid-dependencies")
        by_id[task["id"]] = task
    visiting: set[str] = set()
    visited: set[str] = set()
    ordered: list[str] = []
    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise PolicyError("dependency-cycle")
        if task_id in visited:
            return
        task = by_id.get(task_id)
        if task is None:
            raise PolicyError("dependency-unknown")
        visiting.add(task_id)
        for dependency in task["depends_on"]:
            if not isinstance(dependency, str):
                raise PolicyError("invalid-dependency")
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)
        ordered.append(task_id)
    for task_id in by_id:
        visit(task_id)
    return ordered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=argparse.FileType("r"), default=sys.stdin)
    parser.add_argument("--dry-run", action="store_true", default=False)
    args = parser.parse_args()
    try:
        snapshot = json.load(args.snapshot)
        result = execute_cycle(snapshot, DryRunAdapter(), dry_run=args.dry_run)
    except (PolicyError, json.JSONDecodeError) as error:
        print(json.dumps({"version": 1, "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
