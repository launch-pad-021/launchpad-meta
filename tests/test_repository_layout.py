import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryLayoutTest(unittest.TestCase):
    def test_required_spec_pack_paths_are_at_repository_root(self):
        for path in (
            "README.md",
            "specs/00-product.md",
            "specs/12-agentic-system.md",
            "contracts/events/envelope.schema.json",
            "contracts/proto/launchpad/common/v1/common.proto",
            "bootstrap/KICKOFF.md",
            "bootstrap/agent-kit/README.md",
        ):
            self.assertTrue((ROOT / path).is_file(), path)

    def test_nested_spec_pack_no_longer_exists(self):
        self.assertFalse((ROOT / "launchpad-spec-pack").exists())

    def test_root_claude_instructions_match_bootstrap_bytes(self):
        root_instructions = ROOT / "CLAUDE.md"
        self.assertTrue(root_instructions.is_file(), root_instructions)
        bootstrap_instructions = ROOT / "bootstrap/launchpad-meta/CLAUDE.md"
        self.assertEqual(root_instructions.read_bytes(), bootstrap_instructions.read_bytes())

    def test_agent_instructions_cover_repository_workflow_and_safety(self):
        path = ROOT / "AGENTS.md"
        self.assertTrue(path.is_file(), path)
        instructions = path.read_text(encoding="utf-8")
        for rule in (
            "launchpad-meta",
            "`contracts/` > service spec > `specs/03-conventions.md` > other specs",
            "make validate",
            "make preflight",
            ".github/",
            ".claude/",
            "CODEOWNERS",
            "CLAUDE.md",
            "AGENTS.md",
            "agent-config",
            "Never commit secrets",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, instructions)

    def test_mise_declares_supported_tool_versions(self):
        path = ROOT / ".mise.toml"
        self.assertTrue(path.is_file(), path)
        with path.open("rb") as config:
            self.assertEqual(
                tomllib.load(config)["tools"],
                {"go": "1.27", "node": "26", "python": "3.14", "rust": "stable", "uv": "latest"},
            )

    def test_gitignore_covers_local_files_and_keeps_dotenv_examples_ignored(self):
        path = ROOT / ".gitignore"
        self.assertTrue(path.is_file(), path)
        rules = path.read_text(encoding="utf-8").splitlines()
        for pattern in (".DS_Store", ".env", ".env.*", "*.pem", "*.key", ".venv/", "mise.local.toml"):
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, rules)
        self.assertNotIn("!.env.example", rules)

    def test_makefile_declares_public_targets(self):
        path = ROOT / "Makefile"
        self.assertTrue(path.is_file(), path)
        recipes = path.read_text(encoding="utf-8")
        for target in (
            "bootstrap",
            "bootstrap-install",
            "preflight",
            "preflight-a0",
            "validate",
            "test",
            "test-agent-kit",
        ):
            with self.subTest(target=target):
                self.assertRegex(recipes, rf"(?m)^{target}:")
