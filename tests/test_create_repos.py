import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.create_repos import ConfigError, Provisioner, load_manifest, render_repository


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "bootstrap/templates/repos.json"


class FakeGitHub:
    def __init__(self, repos=None, complete=True):
        self.repos = dict(repos or {})
        self.complete = complete
        self.writes = []

    def discover(self, org):
        return {"complete": self.complete, "repos": self.repos}

    def mutate(self, operation):
        self.writes.append(operation)


class RepositoryTemplateTest(unittest.TestCase):
    def test_manifest_is_exact_and_unique(self):
        data = load_manifest(MANIFEST)
        names = [entry["name"] for entry in data["repositories"]]
        self.assertEqual(len(names), 25)
        self.assertEqual(len(set(names)), 25)
        self.assertEqual(sum(entry["mode"] == "create" for entry in data["repositories"]), 23)
        self.assertEqual({e["name"] for e in data["repositories"] if e["mode"] == "audit"},
                         {"launchpad-meta", "launchpad-agent-kit"})

    def test_all_five_families_render_governed_non_root_trees(self):
        for family in ("go", "rust", "python", "node", "next"):
            with self.subTest(family=family):
                tree = render_repository("launchpad-example", family, "M0", "specs/00-product.md")
                required = {"CLAUDE.md", "AGENTS.md", "CODEOWNERS", "renovate.json",
                            "Dockerfile", "Makefile", ".github/workflows/ci.yml",
                            ".github/workflows/agent.yml", ".github/workflows/release-please.yml"}
                self.assertTrue(required <= set(tree))
                self.assertIn("USER ", tree["Dockerfile"])
                self.assertNotIn("@main", "\n".join(tree.values()))
                self.assertIn("KIT_REF", tree[".github/workflows/ci.yml"])

    def test_render_is_deterministic_and_has_no_real_owner(self):
        first = render_repository("launchpad-router", "go", "M5-02", "specs/services/router.md")
        second = render_repository("launchpad-router", "go", "M5-02", "specs/services/router.md")
        self.assertEqual(first, second)
        self.assertNotIn("Tejas021", "\n".join(first.values()))
        self.assertIn("@LP_OWNER_LOGIN", first["CODEOWNERS"])


class ProvisioningPolicyTest(unittest.TestCase):
    def setUp(self):
        self.manifest = load_manifest(MANIFEST)

    def test_default_plan_is_read_only(self):
        api = FakeGitHub()
        result = Provisioner(api, self.manifest, "launch-pad-021", "public").run(apply=False)
        self.assertEqual(api.writes, [])
        self.assertEqual(len(result["create"]), 23)

    def test_unknown_repo_and_incomplete_discovery_fail_before_writes(self):
        for selected, api in ((["launchpad-unknown"], FakeGitHub()),
                              (None, FakeGitHub(complete=False))):
            with self.subTest(selected=selected):
                with self.assertRaises(ConfigError):
                    Provisioner(api, self.manifest, "launch-pad-021", "public").run(
                        apply=True, selected=selected, owner="synthetic-owner",
                        kit_ref="a" * 40, ci_integration_id=123, review_integration_id=456,
                        approved=True)
                self.assertEqual(api.writes, [])

    def test_apply_rejects_unresolved_live_gates_before_writes(self):
        api = FakeGitHub()
        with self.assertRaises(ConfigError):
            Provisioner(api, self.manifest, "launch-pad-021", "public").run(
                apply=True, owner="synthetic-owner", kit_ref="KIT_REF",
                ci_integration_id=0, review_integration_id=0, approved=False)
        self.assertEqual(api.writes, [])

    def test_owned_partial_state_resumes_and_governed_state_is_noop(self):
        api = FakeGitHub({
            "launchpad-router": {"visibility": "public", "marker": "launchpad-provision-v1",
                                 "stage": "seeded", "governed": False},
            "launchpad-gateway": {"visibility": "public", "marker": "launchpad-provision-v1",
                                  "stage": "governed", "governed": True},
        })
        result = Provisioner(api, self.manifest, "launch-pad-021", "public").run(
            apply=False, selected=["launchpad-router", "launchpad-gateway"])
        self.assertEqual(result["resume"], ["launchpad-router"])
        self.assertEqual(result["noop"], ["launchpad-gateway"])

    def test_unrelated_or_wrong_visibility_existing_repo_refuses(self):
        for state in ({"visibility": "public"},
                      {"visibility": "private", "marker": "launchpad-provision-v1"}):
            api = FakeGitHub({"launchpad-router": state})
            with self.assertRaises(ConfigError):
                Provisioner(api, self.manifest, "launch-pad-021", "public").run(
                    apply=False, selected=["launchpad-router"])
            self.assertEqual(api.writes, [])

    def test_apply_emits_ordered_journalable_operations(self):
        api = FakeGitHub()
        result = Provisioner(api, self.manifest, "launch-pad-021", "public").run(
            apply=True, selected=["launchpad-router"], owner="synthetic-owner",
            kit_ref="a" * 40, ci_integration_id=123, review_integration_id=456,
            approved=True)
        self.assertEqual([op["kind"] for op in api.writes],
                         ["create", "seed", "settings", "ruleset", "apps", "verify"])
        self.assertEqual(result["applied"], ["launchpad-router"])

    def test_cli_fake_gh_dry_run_performs_only_discovery(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            log = root / "calls.jsonl"
            fake = root / "gh"
            fake.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
Path(os.environ['FAKE_GH_LOG']).open('a').write(json.dumps(sys.argv[1:]) + '\\n')
endpoint = sys.argv[-1]
if endpoint == 'orgs/launch-pad-021': print(json.dumps({'login':'launch-pad-021'}))
elif endpoint.startswith('orgs/launch-pad-021/repos?'): print('[]')
else: raise SystemExit(9)
""")
            fake.chmod(0o755)
            env = {**os.environ, "LP_ORG": "launch-pad-021", "FAKE_GH_LOG": str(log),
                   "PATH": f"{root}:{Path(sys.executable).parent}:/usr/bin:/bin"}
            result = subprocess.run([ROOT / "scripts/create-repos.sh", "--org", "launch-pad-021",
                                     "--visibility", "public"], env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('"mode": "dry-run"', result.stdout)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertTrue(calls)
            self.assertFalse(any("--method" in call or "-X" in call for call in calls))
