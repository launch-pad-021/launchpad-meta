#!/usr/bin/env python3
"""Deterministic, fail-closed policy for Launchpad control-plane workflows.

The module intentionally contains no GitHub client.  Network adapters must supply
fresh, typed snapshots and are kept out of credential-free dry runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
