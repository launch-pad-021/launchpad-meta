import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from scripts.preflight import Context, Status, exit_code, resolve_sibling, run_checks


ROOT = Path(__file__).resolve().parents[1]
VERSIONS = {
    ("git", "--version"): "git version 2.49.0",
    ("bash", "--version"): "GNU bash, version 5.2.37(1)-release",
    ("make", "--version"): "GNU Make 3.81",
    ("jq", "--version"): "jq-1.7.1",
    ("claude", "--version"): "2.1.5 (Claude Code)",
    ("python3", "--version"): "Python 3.14.0",
    ("go", "version"): "go version go1.27.1 darwin/arm64",
    ("node", "--version"): "v26.1.0",
    ("rustc", "--version"): "rustc 1.85.1 (4eb161250 2025-03-15)",
    ("uv", "--version"): "uv 0.8.2",
    ("buf", "--version"): "1.47.2",
    ("gh", "--version"): "gh version 2.65.0 (2025-01-06)",
    ("docker", "--version"): "Docker version 28.0.0, build 1234abc",
}


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True,
    ).stdout.strip()


class PreflightTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve() / "meta"
        self.sibling = self.root.with_name("launchpad-agent-kit")
        for repo in (self.root, self.sibling):
            repo.mkdir()
            git(repo, "init", "-b", "main")
            git(repo, "remote", "add", "origin", "https://example.invalid/repo.git")
        for path in ("README.md", "AGENTS.md", "CLAUDE.md", "Makefile", ".mise.toml",
                     "scripts/validate-spec-pack.sh", "bootstrap/KICKOFF.md",
                     "contracts/events/envelope.schema.json", "specs/16-human-setup.md"):
            file = self.root / path
            file.parent.mkdir(exist_ok=True, parents=True)
            file.touch()
        for path in ("scripts/risk.py", "scripts/test_risk.py", ".claude-plugin/marketplace.json"):
            file = self.sibling / path
            file.parent.mkdir(exist_ok=True, parents=True)
            file.touch()
        self.checklist = self.root / "setup/human-setup-status.md"
        self.checklist.parent.mkdir()
        shutil.copyfile(ROOT / "setup/human-setup-status.md", self.checklist)
        self.versions = VERSIONS.copy()
        self.failed = set()
        self.risk_summary = "16 passed in 0.12s"
        self.context = Context(self.root, self.sibling, "step-minus-one", False, {}, self.command)

    def command(self, args):
        args = tuple(map(str, args))
        if args[0] in self.failed or args[:2] in self.failed:
            return subprocess.CompletedProcess(args, 1, "private-stdout", "private-stderr")
        if args in self.versions:
            return subprocess.CompletedProcess(args, 0, self.versions[args], "private-stderr")
        if args[:2] == ("git", "-C"):
            return subprocess.run(args, capture_output=True, text=True)
        if args[:2] == ("uv", "run"):
            return subprocess.CompletedProcess(args, 0, self.risk_summary, "private-stderr")
        if (args[:2] in {("gh", "auth"), ("docker", "info")} or
                args[0] == str(self.root / "scripts/validate-spec-pack.sh")):
            return subprocess.CompletedProcess(args, 0, "private-stdout", "private-stderr")
        self.fail(f"unexpected command {args}")

    def results(self, **kwargs):
        return run_checks(replace(self.context, **kwargs))

    def check_all(self):
        data = self.checklist.read_text()
        self.checklist.write_text(data.replace("- [ ]", "- [x]"))

    def test_step_minus_one_ready_with_owner_actions_and_stable_order(self):
        rows = self.results()
        self.assertEqual(exit_code(rows), 0, rows)
        self.assertTrue(any(row.status == Status.OWNER_ACTION for row in rows))
        ids = [r.check_id for r in rows]
        self.assertEqual(ids, sorted(set(ids)))

    def test_local_failure_wins_over_owner_action(self):
        self.failed.add("jq")
        rows = self.results(phase="a0")
        self.assertEqual(exit_code(rows), 1)
        self.assertTrue(any(row.status == Status.OWNER_ACTION and row.blocking for row in rows))

    def test_a0_github_checkmark_cannot_be_inferred_from_environment(self):
        self.check_all()
        self.checklist.write_text(self.checklist.read_text().replace("[x] GITHUB-01:", "[ ] GITHUB-01:"))
        self.versions["go", "version"] = "go version go1.25.2 linux/arm64"
        rows = self.results(phase="a0", env={"LP_ORG": "private-org"})
        self.assertEqual(exit_code(rows), 2)
        self.assertEqual([r.check_id for r in rows if r.blocking and r.status != Status.PASS],
                         ["GITHUB-01"])
        self.assertNotIn("private-org", str(rows))
        self.check_all()
        self.assertEqual(exit_code(self.results(phase="a0")), 0)

    def test_apple_jq_build_is_accepted_without_exposing_vendor_text(self):
        self.versions["jq", "--version"] = "jq-1.7.1-apple"
        rows = self.results()
        self.assertEqual(exit_code(rows), 0)
        self.assertNotIn("-apple", str(rows))

    def test_auth_and_daemon_output_is_redacted(self):
        self.failed.update({("gh", "auth"), ("docker", "info")})
        rows = self.results(phase="a0")
        indexed = {r.check_id: r for r in rows}
        self.assertEqual(indexed["gh-auth"].status, Status.OWNER_ACTION)
        self.assertEqual(indexed["docker-client"].status, Status.PASS)
        self.assertNotEqual(indexed["docker-daemon"].status, Status.PASS)
        self.assertNotIn("private-", str(rows))
        self.assertEqual(exit_code(rows), 2)
        self.assertEqual(exit_code(self.results(phase="a0", container_drill=True)), 1)
        self.assertEqual(exit_code(self.results(phase="m0")), 1)

    def test_strict_requires_pinned_versions_uv_buf_and_daemon(self):
        self.failed.update({"go", "node", "rustc", "buf", ("docker", "info")})
        self.versions["python3", "--version"] = "Python 3.11.12"
        self.assertEqual(exit_code(self.results()), 0)
        self.failed.add("uv")
        rows = self.results(strict=True)
        blockers = {r.check_id for r in rows if r.blocking and r.status != Status.PASS}
        self.assertTrue({"go", "node", "rust", "python", "uv", "buf", "docker-daemon"} <= blockers)
        self.assertEqual(exit_code(rows), 1)
        self.assertEqual(exit_code(self.results()), 1)

    def test_prerelease_or_wrong_version_cannot_pass_strict(self):
        for command, output in [
            (("rustc", "--version"), "rustc 1.85.0-nightly (abc)"),
            (("rustc", "--version"), "rustc 1.84.0 (abc)"),
            (("go", "version"), "go version go1.27rc1 linux/amd64"),
            (("node", "--version"), "v26.0.0-rc.1"),
            (("python3", "--version"), "Python 3.14.0b1"),
        ]:
            with self.subTest(command=command, output=output):
                self.versions = {**VERSIONS, command: output}
                self.assertEqual(exit_code(self.results(strict=True)), 1)

    def test_m1_gates_selected_languages(self):
        self.check_all()
        self.failed.add("rustc")
        self.assertEqual(exit_code(self.results(phase="m1", issue="M1-03")), 0)
        self.assertEqual(exit_code(self.results(phase="m1", issue="M1-04")), 1)
        self.assertEqual(exit_code(self.results(phase="m1")), 1)
        self.failed.add("buf")
        self.assertEqual(exit_code(self.results(phase="m1", issue="M1-03")), 1)

    def test_m0_gates_cloud_setup_by_issue(self):
        self.check_all()
        self.checklist.write_text(self.checklist.read_text().replace("[x] ACCOUNT-03:", "[ ] ACCOUNT-03:"))
        self.assertEqual(exit_code(self.results(phase="m0", issue="M0-01")), 0)
        self.assertEqual(exit_code(self.results(phase="m0", issue="M0-06")), 2)
        self.assertEqual(exit_code(self.results(phase="m1")), 2)

    def test_m0_server_secret_inventory_requires_maxmind_account(self):
        self.check_all()
        self.checklist.write_text(self.checklist.read_text().replace("[x] ACCOUNT-04:", "[ ] ACCOUNT-04:"))
        self.assertEqual(exit_code(self.results(phase="m0", issue="M0-02")), 2)

    def test_m0_server_secret_inventory_requires_r2_and_cloudflare_credentials(self):
        for ident in ("ACCOUNT-01", "ACCOUNT-03", "DNS-02"):
            with self.subTest(ident=ident):
                self.check_all()
                self.checklist.write_text(
                    self.checklist.read_text().replace(f"[x] {ident}:", f"[ ] {ident}:")
                )
                self.assertEqual(exit_code(self.results(phase="m0", issue="M0-02")), 2)

    def test_bad_issue_or_flag_combination_fails_closed(self):
        for args in (["--phase", "m1", "--issue", "M1-77"], ["--phase", "m1", "--issue", "M0-01"],
                     ["--phase", "m1", "--container-drill"]):
            run = subprocess.run([ROOT / "scripts/preflight.sh", *args], capture_output=True)
            self.assertEqual(run.returncode, 1)
            self.assertIn(b"usage", run.stderr)

    def test_invalid_status_copy_is_local_failure(self):
        original = self.checklist.read_text()
        for value in (original + "\n- [x] GITHUB-01: duplicate\n", original.replace("GITHUB-01:", "BAD-01:"),
                      original.replace("[ ] GITHUB-01:", "[?] GITHUB-01:"), original + "\n* [X] bogus\n"):
            self.checklist.write_text(value)
            self.assertEqual(exit_code(self.results()), 1)
        self.checklist.unlink()
        self.assertEqual(exit_code(self.results()), 1)

    def test_git_index_hygiene_in_both_repositories(self):
        for repo in (self.root, self.sibling):
            directory = repo / "nested"
            directory.mkdir()
            for name in (".env", ".env.local", "tls.pem", "signing.key", ".DS_Store"):
                file = directory / name
                file.touch()
                self.assertEqual(exit_code(self.results()), 0)
                git(repo, "add", "-f", "--", str(file))
                self.assertEqual(exit_code(self.results()), 1)
                git(repo, "rm", "--cached", str(file))

    def test_git_index_hygiene_rejects_openssh_keys_and_generated_noise(self):
        for repo in (self.root, self.sibling):
            for name in ("id_ed25519", "id_rsa", "__pycache__/tracked.pyc", ".pytest_cache/state"):
                with self.subTest(repo=repo.name, name=name):
                    file = repo / name
                    file.parent.mkdir(exist_ok=True, parents=True)
                    file.touch()
                    git(repo, "add", "-f", "--", str(file))
                    self.assertEqual(exit_code(self.results()), 1)
                    git(repo, "rm", "--cached", str(file))

    def test_validation_and_sibling_risk_tests_are_blocking(self):
        for command in (str(self.root / "scripts/validate-spec-pack.sh"), ("uv", "run")):
            self.failed = {command}
            self.assertEqual(exit_code(self.results()), 1)

    def test_collect_only_or_skipped_risk_suite_cannot_prove_readiness(self):
        for output in ("16 tests collected in 0.01s", "16 skipped in 0.02s"):
            self.risk_summary = output
            self.assertEqual(exit_code(self.results()), 1)

    def test_unrelated_or_linked_meta_checkout_cannot_supply_agent_kit(self):
        self.assertEqual(exit_code(self.results(sibling=self.root)), 1)
        self.assertEqual(exit_code(self.results(sibling=self.root / "absent")), 1)
        git(self.root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "--allow-empty", "-m", "fixture")
        linked = self.root.with_name("linked")
        git(self.root, "worktree", "add", "-b", "other", str(linked))
        self.assertEqual(resolve_sibling(linked, {}, self.command), self.sibling)
        self.assertEqual(resolve_sibling(linked, {"LP_AGENT_KIT_PATH": str(self.root)}, self.command),
                         self.root)
        self.assertEqual(exit_code(self.results(sibling=linked)), 1)

    def test_make_runs_risk_tests_from_overridden_sibling(self):
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        uv = bin_dir / "uv"
        uv.write_text("#!/bin/sh\nfor arg; do last=$arg; done\ntest -f \"$last\" || exit 1\necho '16 passed in 0.10s'\n")
        uv.chmod(0o755)
        result = subprocess.run(
            ["make", "test-agent-kit"], cwd=ROOT,
            env={**os.environ, "LP_AGENT_KIT_PATH": str(self.sibling),
                 "PATH": f"{bin_dir}:{os.environ['PATH']}"},
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(str(self.sibling), result.stdout + result.stderr)

    def test_wrapper_json_keeps_override_and_host_probes_private(self):
        private = "synthetic-private-worktree"
        (self.root / private).symlink_to(private)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        for name in ("bash", "dirname", "git"):
            (bin_dir / name).symlink_to(shutil.which(name))
        (bin_dir / "python3").symlink_to(sys.executable)
        result = subprocess.run(
            [ROOT / "scripts/preflight.sh", "--json"], cwd=self.root,
            env={**os.environ, "PATH": str(bin_dir), "LP_AGENT_KIT_PATH": str(self.root / private)},
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(private, result.stdout + result.stderr)
        rows = json.loads(result.stdout)
        self.assertTrue(any(r["check_id"] == "sibling" and r["status"] == "FAIL" for r in rows))
