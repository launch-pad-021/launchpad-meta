import json
import unittest
from types import SimpleNamespace

from scripts.agent_metrics import normalized_row
from scripts.weekly_audits import fingerprint
from scripts.github_publish import Publisher


class ControlToolTests(unittest.TestCase):
    def test_metrics_escape_spreadsheet_formulas(self):
        row = normalized_row({"version": 1, "date": "2026-11-21", "repo": "=cmd", "issue": 1})
        self.assertEqual("'=cmd", row["repo"])
        self.assertEqual("", row["result"])

    def test_audit_fingerprint_is_stable(self):
        finding = {"auditor": "security-auditor", "repo": "launchpad-a", "rule": "R1", "path": "a", "summary": "finding"}
        self.assertEqual(fingerprint(finding), fingerprint(dict(finding)))
        with self.assertRaises(ValueError):
            fingerprint({**finding, "auditor": "lookalike"})

    def test_publisher_deduplicates_audit_issues_and_checks_live_switch(self):
        calls = []
        finding = {"auditor": "security-auditor", "repo": "launchpad-a", "rule": "R1",
                   "path": "a", "summary": "finding"}
        marker = fingerprint(finding)
        def runner(command, **kwargs):
            calls.append((command, kwargs.get("input")))
            endpoint = command[-1] if command[-1] != "-" else command[-3]
            if endpoint.endswith("AGENTS_ENABLED"):
                output = '{"value":"true"}'
            elif "issues?state=all" in endpoint:
                output = '[{"body":"<!-- launchpad-audit-v1:' + marker + ' -->"}]'
            else:
                output = '{}'
            return SimpleNamespace(returncode=0, stdout=output, stderr="")
        publisher = Publisher("example-org", token="synthetic", runner=runner)
        self.assertEqual([], publisher.publish_findings([finding]))
        self.assertFalse(any(json.loads(raw or "{}").get("title") for _, raw in calls))


if __name__ == "__main__":
    unittest.main()
