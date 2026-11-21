import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.a0_drills import run_drills, write_evidence


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/a0_drills.json"


def resolve_agent_kit() -> Path:
    if override := os.environ.get("LP_AGENT_KIT_PATH"):
        return Path(override).resolve()
    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve().parent.parent / "launchpad-agent-kit"
    return ROOT.parent / "launchpad-agent-kit"


KIT = resolve_agent_kit()


class A0DrillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (KIT / "scripts/merge_gate.py").is_file():
            raise unittest.SkipTest("merged launchpad-agent-kit sibling is required for A0 drills")

    def test_local_drills_pass_and_live_drills_do_not_fake_success(self):
        report = run_drills(ROOT, KIT, FIXTURE, "2026-11-21T11:00:00Z")
        by_id = {item["id"]: item for item in report["drills"]}
        self.assertEqual(
            {"protected-path", "high-risk-merge", "kill-switch", "prompt-injection",
             "budget-exhaustion", "red-ci"},
            {name for name, item in by_id.items() if item["local_status"] == "pass"},
        )
        self.assertTrue(all(item["live_status"] == "blocked" for item in by_id.values()))
        self.assertTrue(all(item["blocker"] for item in by_id.values()))

    def test_five_golden_tasks_have_complete_baseline_fields(self):
        report = run_drills(ROOT, KIT, FIXTURE, "2026-11-21T11:00:00Z")
        self.assertEqual(5, len(report["golden_tasks"]))
        self.assertEqual(10, len(report["acceptance"]))
        for task in report["golden_tasks"]:
            self.assertEqual("pass", task["status"])
            self.assertGreaterEqual(task["duration_ms"], 0)
            self.assertEqual(0.0, task["cost_usd"])
            self.assertEqual(0, task["retries"])
            self.assertEqual(1.0, task["reviewer_agreement"])
            self.assertEqual(0, task["escaped_defects"])

    def test_evidence_writer_is_deterministic_and_labels_limitations(self):
        report = run_drills(ROOT, KIT, FIXTURE, "2026-11-21T11:00:00Z")
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw)
            write_evidence(report, output)
            first = (output / "summary.json").read_bytes()
            write_evidence(report, output)
            self.assertEqual(first, (output / "summary.json").read_bytes())
            readme = (output / "README.md").read_text()
            self.assertIn("Local deterministic evidence", readme)
            self.assertIn("Live evidence still blocked", readme)
            self.assertIn("Production rollback", readme)


if __name__ == "__main__":
    unittest.main()
