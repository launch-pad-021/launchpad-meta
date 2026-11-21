import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.validate_spec_pack import AllowRule, find_placeholders, load_allowlist, validate


class ValidateSpecPackTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.write("scripts/placeholder-allowlist.txt", "# path, pattern, reason, expiry\n")

    def write(self, relative_path, content):
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def findings(self, check, path=None):
        return [
            finding for finding in validate(self.root)
            if finding.check == check and (path is None or finding.path == path)
        ]

    def test_missing_required_root_file_is_an_error(self):
        self.assertEqual([finding.level for finding in self.findings("required", "README.md")], ["error"])

    def test_deleting_an_indexed_proto_is_an_error(self):
        path = "contracts/proto/launchpad/builder/v1/builder.proto"
        proto = self.write(path, 'syntax = "proto3";')
        self.assertEqual(self.findings("required", path), [])
        proto.unlink()
        self.assertEqual([finding.level for finding in self.findings("required", path)], ["error"])

    def test_deleting_an_indexed_agent_kit_workflow_is_an_error(self):
        path = "bootstrap/agent-kit/.github/workflows/agent-review.yml"
        workflow = self.write(path, "name: agent-review\n")
        self.assertEqual(self.findings("required", path), [])
        workflow.unlink()
        self.assertEqual([finding.level for finding in self.findings("required", path)], ["error"])

    def test_malformed_json_has_a_relative_path_and_line(self):
        path = "bootstrap/agent-kit/plugins/launchpad/hooks/hooks.json"
        self.write(path, "{\n invalid\n}")
        finding, = self.findings("json", path)
        self.assertEqual(finding.level, "error")
        self.assertIn("line 2", finding.detail)

    def test_nonstandard_json_constant_is_an_error(self):
        path = "bootstrap/agent-kit/schemas/review.schema.json"
        self.write(path, '{"minimum": NaN}')
        finding, = self.findings("json", path)
        self.assertEqual(finding.level, "error")
        self.assertIn("NaN", finding.detail)

    def test_schema_title_must_match_filename(self):
        path = "contracts/events/app.created.v1.schema.json"
        self.write(path, '{"title": "app.updated.v1"}')
        self.write("contracts/events/catalog.md", "| `app.created.v1` | `lp.projects` |\n")
        finding, = self.findings("event-title", path)
        self.assertEqual(finding.level, "error")
        self.assertIn("app.created.v1", finding.detail)

    def test_schema_and_catalog_must_have_one_to_one_membership(self):
        self.write("contracts/events/app.created.v1.schema.json", '{"title": "app.created.v1"}')
        self.write(
            "contracts/events/catalog.md",
            "| `app.updated.v1` | `lp.projects` |\n| `app.updated.v1` | `lp.projects` |\n",
        )
        findings = self.findings("event-catalog")
        self.assertEqual([finding.level for finding in findings], ["error"] * 3)
        self.assertTrue(any("app.created.v1" in finding.detail for finding in findings))
        self.assertTrue(any("app.updated.v1" in finding.detail for finding in findings))
        self.assertTrue(any("duplicate" in finding.detail.lower() for finding in findings))

    def test_envelope_is_parsed_without_requiring_a_catalog_row(self):
        self.write("contracts/events/envelope.schema.json", '{"title": "Launchpad event envelope"}')
        self.write("contracts/events/catalog.md", "| Type | Topic |\n|---|---|\n")
        self.assertEqual(self.findings("event-title"), [])
        self.assertEqual(self.findings("event-catalog"), [])

    def test_intentional_org_placeholder_is_allowed_at_expiry(self):
        path = "bootstrap/templates/project.md"
        self.write(path, "Clone from <org>/project.\n")
        allowlist = self.write(
            "scripts/placeholder-allowlist.txt", f"{path}\t<org>\tOwner setup\tA0\n",
        )
        finding, = find_placeholders(self.root, load_allowlist(allowlist), "A0")
        self.assertEqual((finding.level, finding.path), ("allowed", path))
        self.assertIn("Owner setup", finding.detail)

    def test_unexpected_placeholder_is_reported_with_line_number(self):
        path = "specs/new.md"
        self.write(path, "# Title\nDetails.\nUNEXPECTED_PLACEHOLDER\n")
        finding, = find_placeholders(self.root, [], "step-minus-one")
        self.assertEqual((finding.level, finding.path), ("error", path))
        self.assertIn("line 3", finding.detail)
        self.assertIn("UNEXPECTED_PLACEHOLDER", finding.detail)

    def test_unexpected_placeholder_in_python_starter_is_an_error(self):
        path = "bootstrap/agent-kit/scripts/risk.py"
        self.write(path, "# Risk classifier\nlabel = 'UNEXPECTED_PLACEHOLDER'\n")
        findings = self.findings("placeholder", path)
        self.assertEqual([finding.level for finding in findings], ["error"])
        self.assertIn("line 2", findings[0].detail)

    def test_allowing_a_token_does_not_exempt_the_rest_of_its_line(self):
        path = "bootstrap/templates/project.md"
        self.write(path, "Clone from <org>/project and notify <other-person>.\n")
        rule = AllowRule("bootstrap/templates/*.md", r"<org>", "Owner setup", "A0")
        findings = find_placeholders(self.root, [rule], "step-minus-one")
        self.assertEqual([finding.level for finding in findings], ["allowed", "error"])
        self.assertIn("<other-person>", findings[1].detail)

    def test_expired_rule_is_an_error(self):
        path = "bootstrap/templates/project.md"
        self.write(path, "Clone from <org>/project.\n")
        rule = AllowRule(path, r"<org>", "Owner setup", "A0")
        finding, = find_placeholders(self.root, [rule], "M0")
        self.assertEqual((finding.level, finding.path), ("error", path))
        self.assertIn("expired", finding.detail.lower())
        self.assertIn("A0", finding.detail)

    def test_invalid_allowlist_row_is_an_error(self):
        self.write("scripts/placeholder-allowlist.txt", "# comment\n*.md\t<org>\tMissing expiry\n")
        finding, = self.findings("allowlist", "scripts/placeholder-allowlist.txt")
        self.assertEqual(finding.level, "error")
        self.assertIn("line 2", finding.detail)

    def test_invalid_allowlist_pattern_is_an_error(self):
        self.write("scripts/placeholder-allowlist.txt", "*.md\t(\tBad regex\tA0\n")
        finding, = self.findings("allowlist")
        self.assertEqual(finding.level, "error")
        self.assertIn("regular expression", finding.detail)

    def test_catch_all_allowlist_scopes_and_patterns_are_errors(self):
        examples = (
            ("*", ".*", "scope"),
            ("**/*.md", "<org>", "scope"),
            ("specs/00-product.md", "(?s:.*)", "pattern"),
            ("specs/00-product.md", "<[^>]+>", "pattern"),
        )
        for glob, pattern, reason in examples:
            with self.subTest(glob=glob, pattern=pattern):
                self.write("scripts/placeholder-allowlist.txt", f"{glob}\t{pattern}\tBlanket rule\tM1\n")
                findings = self.findings("allowlist")
                self.assertEqual([finding.level for finding in findings], ["error"])
                self.assertIn(reason, findings[0].detail)

    def test_shell_syntax_failure_is_an_error_even_in_a_template(self):
        path = "bootstrap/agent-kit/hooks/broken.sh"
        self.write(path, "#!/usr/bin/env bash\nif true; then\n")
        finding, = self.findings("shell-syntax", path)
        self.assertEqual(finding.level, "error")

    def test_non_executable_live_entrypoint_is_an_error(self):
        path = "scripts/validate-spec-pack.sh"
        self.write(path, "#!/usr/bin/env bash\n")
        finding, = self.findings("executable", path)
        self.assertEqual(finding.level, "error")

    def test_non_executable_imported_hook_is_an_a0_warning(self):
        path = "bootstrap/agent-kit/plugins/launchpad/hooks/scripts/guard-bash.sh"
        self.write(path, "#!/usr/bin/env bash\n")
        finding, = self.findings("executable", path)
        self.assertEqual(finding.level, "warning")
        self.assertIn("A0", finding.detail)

    def test_missing_buf_config_is_an_explicit_skip(self):
        finding, = self.findings("buf", "buf.yaml")
        self.assertEqual(finding.level, "skip")
        self.assertIn("root buf.yaml", finding.detail)

    def test_absent_buf_binary_is_an_explicit_skip(self):
        self.write("buf.yaml", "version: v2\n")
        with patch.dict(os.environ, {"PATH": str(self.root)}):
            finding, = self.findings("buf", "buf.yaml")
        self.assertEqual(finding.level, "skip")
        self.assertIn("unavailable", finding.detail)

    def test_buf_format_diff_and_lint_failures_are_reported(self):
        self.write("buf.yaml", "version: v2\n")
        buf = self.write(
            "bin/buf",
            "#!/bin/sh\n"
            '[ -f buf.yaml ] || exit 99\n'
            'case "$*" in\n'
            '  "format --diff --exit-code") exit 100;;\n'
            '  lint) exit 1;;\n'
            'esac\n',
        )
        buf.chmod(0o755)
        with patch.dict(os.environ, {"PATH": str(buf.parent)}):
            findings = [finding for finding in validate(self.root) if finding.check.startswith("buf")]
        self.assertEqual([(finding.check, finding.level) for finding in findings], [
            ("buf-format", "error"), ("buf-lint", "error"),
        ])
        self.assertIn("100", findings[0].detail)
        self.assertIn("1", findings[1].detail)
