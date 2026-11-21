import unittest

from scripts.agent_metrics import normalized_row
from scripts.weekly_audits import fingerprint


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


if __name__ == "__main__":
    unittest.main()
