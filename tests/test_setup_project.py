import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/setup-project.sh"


class SetupProjectTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.log = self.temp / "gh.log"
        self.state = self.temp / "state.json"
        self.bin = self.temp / "bin"
        self.bin.mkdir()
        fake = self.bin / "gh"
        fake.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
Path(os.environ["FAKE_GH_LOG"]).open("a").write(json.dumps(args) + "\\n")
state = json.loads(Path(os.environ["FAKE_GH_STATE"]).read_text())
if args[:2] == ["api", "orgs/launch-pad-021"]:
    print("launch-pad-021")
elif args[:2] == ["api", "user/memberships/orgs/launch-pad-021"]:
    print("active")
elif args[:2] == ["project", "list"]:
    projects = [{"number": 1, "title": "Launchpad", "id": "project-id"}] if state.get("project_exists", True) else []
    print(json.dumps({"projects": projects}))
elif args[:2] == ["project", "create"]:
    print(json.dumps({"number": 1, "title": "Launchpad", "id": "project-id"}))
elif args[:3] == ["project", "field-list", "1"]:
    print(json.dumps({"fields": state["fields"]}))
elif os.environ.get("FAKE_GH_FAIL") == "1" and args[:2] == ["label", "create"]:
    print("synthetic-secret-token", file=sys.stderr)
    raise SystemExit(9)
else:
    print("{}")
""")
        fake.chmod(0o755)

    def write_state(self, configured=True, project_exists=True, risk_options=None):
        statuses = ["Backlog", "Ready", "In progress", "In review", "Merged", "Deployed",
                    "Verified", "Done", "Blocked", "Failed", "On hold"]
        fields = [
            {"id": "status-id", "name": "Status", "type": "ProjectV2SingleSelectField",
             "options": [{"id": str(i), "name": name} for i, name in enumerate(
                 statuses if configured else ["Todo", "In Progress", "Done"] )]},
            {"id": "milestone-id", "name": "Milestone", "type": "ProjectV2Field"},
            {"id": "repository-id", "name": "Repository", "type": "ProjectV2Field"},
        ]
        if configured:
            fields.append({"id": "risk-id", "name": "Risk", "type": "ProjectV2SingleSelectField",
                           "options": [{"name": value} for value in
                                       (risk_options or ("low", "medium", "high"))]})
        self.state.write_text(json.dumps({"fields": fields, "project_exists": project_exists}))

    def invoke(self, *args, expected_org="launch-pad-021", fail=False):
        env = {
            **os.environ,
            "PATH": f"{self.bin}:{Path(sys.executable).parent}:/usr/bin:/bin",
            "FAKE_GH_LOG": str(self.log),
            "FAKE_GH_STATE": str(self.state),
            "LP_ORG": expected_org,
            "GH_TOKEN": "synthetic-secret-token",
        }
        if fail:
            env["FAKE_GH_FAIL"] = "1"
        return subprocess.run([SCRIPT, *args], env=env, capture_output=True, text=True)

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_root_templates_match_reviewed_sources(self):
        pairs = (
            (ROOT / ".github/ISSUE_TEMPLATE/agent-task.yml",
             ROOT / "bootstrap/templates/ISSUE_TEMPLATE/agent-task.yml"),
            (ROOT / ".github/pull_request_template.md",
             ROOT / "bootstrap/templates/PULL_REQUEST_TEMPLATE.md"),
        )
        for live, source in pairs:
            with self.subTest(path=live):
                self.assertEqual(live.read_bytes(), source.read_bytes())

    def test_readme_documents_project_setup_safety_and_scopes(self):
        readme = (ROOT / "README.md").read_text()
        for text in (
            "scripts/setup-project.sh --org launch-pad-021",
            "--apply",
            "dry run",
            "admin:org",
            "project",
        ):
            with self.subTest(text=text):
                self.assertIn(text, readme)

    def test_default_is_read_only_dry_run(self):
        self.write_state(configured=False)
        result = self.invoke("--org", "launch-pad-021")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DRY RUN", result.stdout)
        self.assertNotIn("synthetic-secret-token", result.stdout + result.stderr)
        mutating = [call for call in self.calls() if call[:2] in (
            ["label", "create"], ["project", "create"], ["project", "field-create"]
        ) or call[:2] == ["api", "graphql"]]
        self.assertEqual(mutating, [])

    def test_wrong_environment_organization_fails_before_gh(self):
        self.write_state()
        result = self.invoke("--org", "other-org")
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not match", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_apply_is_idempotent_when_project_fields_are_configured(self):
        self.write_state()
        result = self.invoke("--org", "launch-pad-021", "--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        label_calls = [call for call in calls if call[:2] == ["label", "create"]]
        self.assertEqual(len(label_calls), 16)
        self.assertTrue(all("--force" in call for call in label_calls))
        self.assertFalse(any(call[:2] == ["api", "graphql"] for call in calls))
        self.assertFalse(any(call[:2] == ["project", "field-create"] for call in calls))

    def test_apply_repairs_default_status_and_missing_risk(self):
        self.write_state(configured=False)
        result = self.invoke("--org", "launch-pad-021", "--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertTrue(any(call[:2] == ["api", "graphql"] for call in calls))
        self.assertTrue(any(call[:2] == ["project", "field-create"] and
                            "Risk" in call for call in calls))

    def test_dry_run_reports_missing_project_without_creating_it(self):
        self.write_state(configured=False, project_exists=False)
        result = self.invoke("--org", "launch-pad-021")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("create Launchpad Project", result.stdout)
        self.assertFalse(any(call[:2] == ["project", "create"] for call in self.calls()))

    def test_apply_creates_missing_project_before_configuring_fields(self):
        self.write_state(configured=False, project_exists=False)
        result = self.invoke("--org", "launch-pad-021", "--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        create_index = next(i for i, call in enumerate(calls) if call[:2] == ["project", "create"])
        fields_index = next(i for i, call in enumerate(calls) if call[:3] == ["project", "field-list", "1"])
        self.assertLess(create_index, fields_index)

    def test_unexpected_risk_options_fail_before_any_mutation(self):
        self.write_state(risk_options=("low", "high"))
        result = self.invoke("--org", "launch-pad-021", "--apply")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unexpected options", result.stderr)
        self.assertFalse(any(call[:2] in (["label", "create"], ["api", "graphql"])
                             for call in self.calls()))

    def test_command_failure_redacts_subprocess_output(self):
        self.write_state()
        result = self.invoke("--org", "launch-pad-021", "--apply", fail=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("GitHub setup command failed", result.stderr)
        self.assertNotIn("synthetic-secret-token", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
