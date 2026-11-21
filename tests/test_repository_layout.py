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
