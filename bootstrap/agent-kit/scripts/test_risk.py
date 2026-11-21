from risk import classify

def lvl(*a, **k):
    return classify(*a, **k)["level"]

def test_docs_only_low():
    assert lvl("launchpad-deployer", ["README.md"]) == "low"

def test_identity_any_code_high():
    assert lvl("launchpad-identity", ["internal/session/store.go"]) == "high"

def test_identity_tests_only_low():
    assert lvl("launchpad-identity", ["internal/session/store_test.go"]) == "low"

def test_projects_crypto_high_other_low():
    assert lvl("launchpad-projects", ["internal/crypto/aead.go"]) == "high"
    assert lvl("launchpad-projects", ["internal/apps/validate.go"]) == "low"

def test_scm_webhooks_high():
    assert lvl("launchpad-scm", ["src/webhooks/verify.ts"]) == "high"

def test_router_runtime_builder_high():
    for r in ["launchpad-router", "launchpad-runtime-agent", "launchpad-builder"]:
        assert lvl(r, ["internal/x/y.go"]) == "high"

def test_gateway_auth_high():
    assert lvl("launchpad-gateway", ["internal/auth/mw.go"]) == "high"
    assert lvl("launchpad-gateway", ["internal/routes/apps.go"]) == "low"

def test_ingest_and_analytics_paths():
    assert lvl("launchpad-ingest", ["src/handler.rs"]) == "high"
    assert lvl("launchpad-analytics", ["src/lp_analytics/ask/validate.py"]) == "high"
    assert lvl("launchpad-analytics", ["src/lp_analytics/queries/overview.py"]) == "low"

def test_agent_config_paths_never_low():
    r = classify("launchpad-deployer", [".github/workflows/ci.yml"])
    assert r["level"] == "high" and r["agent_config"]
    r = classify("launchpad-deployer", ["CODEOWNERS"])
    assert r["agent_config"]

def test_agent_config_repos():
    assert classify("launchpad-agent-kit", ["plugins/launchpad/agents/x.md"])["agent_config"]
    assert classify("launchpad-meta", ["specs/x.md"])["agent_config"]

def test_infra_versions_only_low_else_high():
    assert lvl("launchpad-infra", ["versions.env"]) == "low"
    assert lvl("launchpad-infra", ["versions.env"], labels=["has-migration"]) == "medium"
    assert lvl("launchpad-infra", ["versions.env"], labels=["inherit:high"]) == "high"
    assert lvl("launchpad-infra", ["compose.yml"]) == "high"

def test_contracts():
    assert lvl("launchpad-contracts", ["proto/launchpad/x/v1/x.proto"]) == "medium"
    assert lvl("launchpad-contracts", ["proto/launchpad/x/v1/x.proto"], buf_breaking=True) == "high"

DIFF_DROP = """+++ b/migrations/0005_drop.sql
+ALTER TABLE apps DROP COLUMN foo;
"""
DIFF_ADD = """+++ b/migrations/0004_add.sql
+ALTER TABLE apps ADD COLUMN foo text;
"""
DIFF_TYPE = """+++ b/migrations/0006.sql
+ALTER TABLE apps ALTER COLUMN port TYPE smallint;
"""

def test_migrations():
    assert lvl("launchpad-deployer", ["migrations/0005_drop.sql"], DIFF_DROP) == "high"
    assert lvl("launchpad-deployer", ["migrations/0004_add.sql"], DIFF_ADD) == "medium"
    assert lvl("launchpad-deployer", ["migrations/0006.sql"], DIFF_TYPE) == "high"

def test_dependency_manifest_medium():
    assert lvl("launchpad-deployer", ["go.mod"]) == "medium"

def test_large_change_medium():
    diff = "+++ b/internal/x.go\n" + "\n".join("+line" for _ in range(401))
    assert lvl("launchpad-deployer", ["internal/x.go"], diff) == "medium"

def test_labels_raise_never_lower():
    assert lvl("launchpad-deployer", ["internal/x.go"], labels=["risk:high"]) == "high"
    assert lvl("launchpad-identity", ["internal/x.go"], labels=["risk:low"]) == "high"
