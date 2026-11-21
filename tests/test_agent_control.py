import json
import tempfile
import unittest
from pathlib import Path

from scripts.agent_control import (
    DryRunAdapter,
    PolicyError,
    execute_cycle,
    plan_cycle,
    validate_plan_manifest,
)


FIXTURES = Path(__file__).parent / "fixtures" / "agent_control"


class AgentControlTests(unittest.TestCase):
    def test_cycle_fixtures(self):
        cases = json.loads((FIXTURES / "cycles.json").read_text())
        for case in cases:
            with self.subTest(case=case["name"]):
                result = plan_cycle(case)
                self.assertEqual(case["expected"], [x["issue_id"] for x in result["dispatches"]])

    def test_unknown_dependency_fails_closed(self):
        snapshot = {
            "enabled": True,
            "daily_budget_micros": 10_000_000,
            "per_run_budget_micros": 1_000_000,
            "spent_micros": 0,
            "active": [],
            "items": [{"id": "a", "status": "Ready", "position": 1, "labels": ["agent:task"], "dependencies": ["missing"], "fields_complete": True, "attempts": 0}],
        }
        result = plan_cycle(snapshot)
        self.assertEqual([], result["dispatches"])
        self.assertIn("dependency-unknown", result["skips"]["a"])

    def test_duplicate_and_partial_failure_get_one_handoff(self):
        snapshot = {
            "enabled": True, "daily_budget_micros": 10_000_000,
            "per_run_budget_micros": 1_000_000, "spent_micros": 0,
            "active": [], "items": [], "errors": ["project-page-2"],
            "event_id": "same", "handoff_keys": ["same:partial-api"],
        }
        result = plan_cycle(snapshot)
        self.assertEqual([], result["handoffs"])
        self.assertEqual([], result["dispatches"])

    def test_stale_project_state_fails_closed_once(self):
        snapshot = {
            "enabled": True, "daily_budget_micros": 10_000_000,
            "per_run_budget_micros": 1_000_000, "spent_micros": 0,
            "active": [], "items": [], "stale": True, "event_id": "stale",
        }
        result = plan_cycle(snapshot)
        self.assertEqual("stale-project-state", result["stop_reason"])
        self.assertEqual(["stale:stale-project-state"], [x["key"] for x in result["handoffs"]])

    def test_retry_limit_and_high_risk_acknowledgement(self):
        base = {"status": "Ready", "labels": ["agent:task"], "dependencies": [], "fields_complete": True, "position": 1}
        snapshot = {"enabled": True, "daily_budget_micros": 20_000_000, "per_run_budget_micros": 1_000_000, "spent_micros": 0, "active": [], "items": [
            dict(base, id="limit", attempts=3),
            dict(base, id="high", attempts=0, risk="high", developer_ack=False, position=2),
        ]}
        result = plan_cycle(snapshot)
        self.assertEqual([], result["dispatches"])
        self.assertEqual("retry-limit", result["skips"]["limit"])
        self.assertEqual("high-risk-unacknowledged", result["skips"]["high"])

    def test_dry_run_adapter_cannot_mutate(self):
        adapter = DryRunAdapter()
        snapshot = {"enabled": True, "daily_budget_micros": 10_000_000, "per_run_budget_micros": 1_000_000, "spent_micros": 0, "active": [], "items": [
            {"id": "a", "status": "Ready", "position": 1, "labels": ["agent:task"], "dependencies": [], "fields_complete": True, "attempts": 0}
        ]}
        result = execute_cycle(snapshot, adapter, dry_run=True)
        self.assertEqual(["a"], [x["issue_id"] for x in result["dispatches"]])
        self.assertEqual([], adapter.calls)
        with self.assertRaises(PolicyError):
            adapter.reserve({"issue_id": "a"})

    def test_kill_switch_rechecked_at_safe_boundaries(self):
        class Flips:
            def __init__(self): self.reads = 0; self.calls = []
            def enabled(self): self.reads += 1; return self.reads < 2
            def reserve(self, intent): self.calls.append(("reserve", intent))
            def dispatch(self, intent): self.calls.append(("dispatch", intent))
        adapter = Flips()
        snapshot = {"enabled": True, "daily_budget_micros": 10_000_000, "per_run_budget_micros": 1_000_000, "spent_micros": 0, "active": [], "items": [
            {"id": "a", "status": "Ready", "position": 1, "labels": ["agent:task"], "dependencies": [], "fields_complete": True, "attempts": 0}
        ]}
        result = execute_cycle(snapshot, adapter, dry_run=False)
        self.assertEqual("kill-switch", result["stop_reason"])
        self.assertEqual(["reserve"], [name for name, _ in adapter.calls])

    def test_plan_manifest_requires_dag_and_one_repo(self):
        manifest = {"version": 1, "milestone": "M0", "tasks": [
            {"id": "one", "repo": "launchpad-a", "depends_on": []},
            {"id": "two", "repo": "launchpad-b", "depends_on": ["one"]},
        ]}
        self.assertEqual(["one", "two"], validate_plan_manifest(manifest))
        manifest["tasks"][0]["depends_on"] = ["two"]
        with self.assertRaises(PolicyError):
            validate_plan_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
