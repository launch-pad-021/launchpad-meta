import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.create_repos import (FINAL_KIT_REF, ConfigError, GhAdapter, Journal,
                                  Provisioner, load_manifest,
                                  render_repository, ruleset_payload)


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
                self.assertIn(FINAL_KIT_REF, tree[".github/workflows/ci.yml"])
                self.assertNotIn("KIT_REF", tree[".github/workflows/ci.yml"])
                self.assertIn("/.github/workflows/ci-", tree[".github/workflows/ci.yml"])
                agent = tree[".github/workflows/agent.yml"]
                for field in ("issue_number:", "lease_id:", "attempt:", "max_budget_usd:", "kit_ref:"):
                    self.assertIn(field, agent)

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
                      {"visibility": "private", "marker": "launchpad-provision-v1"},
                      {"visibility": "public", "marker": "launchpad-provision-v1", "stage": "discovered"}):
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

    def test_ruleset_payload_pins_both_check_producers(self):
        payload = ruleset_payload(123, 456)
        checks = payload["rules"][-1]["parameters"]["required_status_checks"]
        self.assertEqual([item["context"] for item in checks], [
            "CI / build", "CI / lint", "CI / types", "CI / tests",
            "CI / security", "CI / contracts", "agent-review / merge-gate",
        ])
        self.assertTrue(all(item["integration_id"] == 123 for item in checks[:6]))
        self.assertEqual(checks[-1]["integration_id"], 456)
        self.assertEqual(payload["bypass_actors"], [])

    def test_journal_is_atomic_and_refuses_identity_drift(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "state.json"
            journal = Journal(path)
            journal.record("launchpad-router", {"repo_id": 7, "visibility": "public",
                                                  "stage": "created", "marker": "launchpad-provision-v1"})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(Journal(path).repo("launchpad-router")["repo_id"], 7)
            with self.assertRaises(ConfigError):
                journal.assert_identity("launchpad-router", 8, "public")

    def test_create_lost_response_is_reconciled_without_repeating_post(self):
        with tempfile.TemporaryDirectory() as raw:
            calls = []
            repo = {"id": 77, "name": "launchpad-router", "full_name": "launch-pad-021/launchpad-router",
                    "visibility": "public", "description": "launchpad-provision-v1; managed"}

            def runner(argv, **kwargs):
                calls.append((list(argv), kwargs.get("input")))
                endpoint = argv[-1]
                if endpoint == "orgs/launch-pad-021/repos":
                    return subprocess.CompletedProcess(argv, 1, "", "synthetic lost response")
                if endpoint == "repos/launch-pad-021/launchpad-router":
                    return subprocess.CompletedProcess(argv, 0, json.dumps(repo), "")
                return subprocess.CompletedProcess(argv, 9, "", "unexpected")

            adapter = GhAdapter(Path(raw) / "journal.json", apply=True, runner=runner)
            adapter.org = "launch-pad-021"
            adapter.prepared = True  # policy preflight is tested separately from lost-response recovery
            adapter.mutate({"kind": "create", "repo": "launchpad-router", "visibility": "public",
                            "kit_ref": FINAL_KIT_REF, "tree_hash": "a" * 64, "tree": {},
                            "marker": "launchpad-provision-v1", "owner": "synthetic-owner",
                            "ci_integration_id": 123, "review_integration_id": 456,
                            "app_roles": ["dev", "review"]})
            posts = [call for call in calls if "--method" in call[0] and "POST" in call[0]]
            self.assertEqual(len(posts), 1)
            payload = json.loads(posts[0][1])
            self.assertFalse(payload["auto_init"])
            self.assertFalse(payload["allow_merge_commit"])
            self.assertEqual(Journal(Path(raw) / "journal.json").repo("launchpad-router")["stage"], "created")

    def test_apply_preflight_requires_exact_selected_app_policy(self):
        with tempfile.TemporaryDirectory() as raw:
            installations = [
                {"id": 1, "app_slug": "launchpad-dev", "repository_selection": "selected",
                 "suspended_at": None, "permissions": {"contents": "write", "issues": "write",
                 "pull_requests": "write", "metadata": "read"}},
                {"id": 2, "app_slug": "launchpad-review", "repository_selection": "selected",
                 "suspended_at": None, "permissions": {"contents": "read", "pull_requests": "write",
                 "statuses": "write", "metadata": "read"}},
            ]

            def runner(argv, **kwargs):
                return subprocess.CompletedProcess(argv, 0, json.dumps({"total_count": 2,
                                                                          "installations": installations}), "")

            adapter = GhAdapter(Path(raw) / "journal.json", apply=True,
                                installations={"dev": 1, "review": 2}, runner=runner)
            adapter.org = "launch-pad-021"
            adapter.prepare_apply({"dev", "review"})
            self.assertTrue(adapter.prepared)
            installations[1]["permissions"]["administration"] = "write"
            second = GhAdapter(Path(raw) / "second.json", apply=True,
                               installations={"dev": 1, "review": 2}, runner=runner)
            second.org = "launch-pad-021"
            with self.assertRaises(ConfigError):
                second.prepare_apply({"dev", "review"})
