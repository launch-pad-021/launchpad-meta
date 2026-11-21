import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "scripts/bootstrap-local.sh"


class AgentKitSeedTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.destination = self.temp / "launchpad-agent-kit"

    def seed(self, destination=None, env=None):
        return subprocess.run(
            [BOOTSTRAP, "--seed-agent-kit", str(destination or self.destination)],
            cwd=ROOT,
            env={**os.environ, **(env or {})},
            capture_output=True,
            text=True,
        )

    def test_missing_destination_is_seeded_as_independent_main_repository(self):
        result = self.seed()
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in (
            ".git", ".launchpad-seed-manifest.sha256", ".claude-plugin/marketplace.json",
            "scripts/risk.py", "scripts/test_risk.py", "AGENTS.md", ".mise.toml", "Makefile",
        ):
            self.assertTrue((self.destination / path).exists(), path)
        branch = subprocess.run(
            ["git", "-C", self.destination, "branch", "--show-current"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        self.assertEqual(branch, "main")
        meta_common = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"], cwd=ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        kit_common = subprocess.run(
            ["git", "-C", self.destination, "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        self.assertNotEqual(Path(meta_common).resolve(), (self.destination / kit_common).resolve())

    def test_unrecognized_nonempty_destination_is_unchanged(self):
        self.destination.mkdir()
        sentinel = self.destination / "keep.txt"
        sentinel.write_text("owner data")
        result = self.seed()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_text(), "owner data")
        self.assertEqual({p.name for p in self.destination.iterdir()}, {"keep.txt"})

    def test_repeat_seed_does_not_overwrite_modifications(self):
        self.assertEqual(self.seed().returncode, 0)
        readme = self.destination / "README.md"
        readme.write_text("local modification\n")
        result = self.seed()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(readme.read_text(), "local modification\n")

    def test_destination_cannot_be_meta_root_or_descendant(self):
        for destination in (ROOT, ROOT / "nested-agent-kit"):
            with self.subTest(destination=destination):
                result = self.seed(destination)
                self.assertNotEqual(result.returncode, 0)

    def test_added_environment_files_keep_placeholders_and_secrets_out(self):
        self.assertEqual(self.seed().returncode, 0)
        for name in ("AGENTS.md", ".mise.toml", ".editorconfig", ".gitattributes", ".gitignore", "Makefile"):
            text = (self.destination / name).read_text()
            self.assertNotIn("LP_ORG", text)
            self.assertNotIn("PRIVATE KEY", text)
            self.assertNotRegex(text, r"gh[opusr]_[A-Za-z0-9]")

    def test_make_validate_and_test_use_the_seeded_tree(self):
        self.assertEqual(self.seed().returncode, 0)
        fake_bin = self.temp / "bin"
        fake_bin.mkdir()
        uv = fake_bin / "uv"
        uv.write_text("#!/bin/sh\ntest -f scripts/test_risk.py || exit 3\necho '18 passed in 0.10s'\n")
        uv.chmod(0o755)
        env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"}
        for target in ("validate", "test"):
            result = subprocess.run(
                ["make", target], cwd=self.destination, env=env,
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
