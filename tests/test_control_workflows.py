import re
import unittest
from pathlib import Path


WORKFLOWS = Path(__file__).parents[1] / ".github" / "workflows"
NAMES = ("conductor.yml", "planner.yml", "metrics.yml", "weekly-audits.yml")


class ControlWorkflowTests(unittest.TestCase):
    def test_workflows_have_fail_closed_permissions_and_timeouts(self):
        for name in NAMES:
            with self.subTest(name=name):
                text = (WORKFLOWS / name).read_text()
                self.assertIn("permissions: {}", text)
                self.assertIn("timeout-minutes:", text)
                self.assertIn("AGENTS_ENABLED", text)
                self.assertNotIn("secrets: inherit", text)
                self.assertNotIn("pull_request_target", text)

    def test_external_actions_are_sha_pinned(self):
        action = re.compile(r"uses:\s+([^\s]+)")
        sha = re.compile(r"^[^@]+@[0-9a-f]{40}$")
        for name in NAMES:
            for use in action.findall((WORKFLOWS / name).read_text()):
                self.assertRegex(use, sha, f"floating action in {name}: {use}")

    def test_mutating_workflows_default_to_dry_run(self):
        for name in ("conductor.yml", "planner.yml", "weekly-audits.yml"):
            text = (WORKFLOWS / name).read_text()
            self.assertRegex(text, r"dry_run:[\s\S]*?default: true")


if __name__ == "__main__":
    unittest.main()
