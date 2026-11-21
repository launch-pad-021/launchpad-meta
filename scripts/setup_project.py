"""Idempotently reconcile Launchpad's GitHub labels and Project fields."""

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence


STATUSES = (
    "Backlog", "Ready", "In progress", "In review", "Merged", "Deployed",
    "Verified", "Done", "Blocked", "Failed", "On hold",
)
STATUS_COLORS = (
    "GRAY", "BLUE", "YELLOW", "PURPLE", "GREEN", "BLUE",
    "GREEN", "GREEN", "RED", "RED", "ORANGE",
)
LABELS = (
    ("agent:task", "1D76DB", "PR-sized task approved through a milestone plan"),
    ("agent:hold", "FBCA04", "Stop agent work until the owner removes this label"),
    ("agent:blocked", "D93F0B", "Agent work requires an owner decision"),
    ("agent-config", "B60205", "Agent configuration; developer merge required"),
    ("spec-bug", "5319E7", "Contradiction or defect in the normative specification"),
    ("risk:low", "0E8A16", "Deterministic low-risk classification"),
    ("risk:medium", "FBCA04", "Deterministic medium-risk classification"),
    ("risk:high", "D93F0B", "High risk; developer approval required"),
)
CONTROL_REPOS = ("launchpad-meta", "launchpad-agent-kit")


class SetupError(RuntimeError):
    pass


def run_gh(args: Sequence[str], *, input_text: str | None = None) -> str:
    try:
        result = subprocess.run(
            ("gh", *args), input=input_text, stdin=subprocess.DEVNULL if input_text is None else None,
            capture_output=True, text=True, timeout=30, check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SetupError("GitHub setup command failed; inspect gh authentication and permissions") from exc
    return result.stdout


def project_fields(org: str, number: int) -> list[dict]:
    raw = run_gh(("project", "field-list", str(number), "--owner", org, "--format", "json"))
    return json.loads(raw)["fields"]


def field_by_name(fields: list[dict], name: str) -> dict | None:
    return next((field for field in fields if field.get("name") == name), None)


def verify_org(org: str) -> None:
    observed = run_gh(("api", f"orgs/{org}", "--jq", ".login")).strip()
    membership = run_gh(("api", f"user/memberships/orgs/{org}", "--jq", ".state")).strip()
    if observed != org or membership != "active":
        raise SetupError(f"authenticated user is not an active member of organization {org}")


def reconcile(org: str, apply: bool) -> None:
    expected_org = os.environ.get("LP_ORG")
    if expected_org and expected_org != org:
        raise SetupError(f"--org {org} does not match LP_ORG")
    verify_org(org)

    projects = json.loads(run_gh(("project", "list", "--owner", org, "--format", "json")))["projects"]
    project = next((item for item in projects if item.get("title") == "Launchpad"), None)
    if project is None:
        print("APPLY" if apply else "DRY RUN", f"organization={org}")
        print("create Launchpad Project")
        print(f"ensure {len(LABELS)} labels in each control repository")
        if not apply:
            return
        project = json.loads(run_gh(("project", "create", "--owner", org, "--title", "Launchpad",
                                     "--format", "json")))
    number = int(project["number"])
    fields = project_fields(org, number)
    status = field_by_name(fields, "Status")
    risk = field_by_name(fields, "Risk")
    missing_builtins = [name for name in ("Milestone", "Repository") if field_by_name(fields, name) is None]
    if status is None or missing_builtins:
        raise SetupError("Launchpad Project is missing required built-in fields")

    status_names = tuple(option["name"] for option in status.get("options", ()))
    risk_names = tuple(option["name"] for option in (risk or {}).get("options", ()))
    if risk is not None and risk_names != ("low", "medium", "high"):
        raise SetupError("existing Risk field has unexpected options; refusing destructive replacement")
    print("APPLY" if apply else "DRY RUN", f"organization={org} project={number}")
    print(f"ensure {len(LABELS)} labels in each control repository")
    if status_names != STATUSES:
        print("update Status field options")
    if risk_names != ("low", "medium", "high"):
        print("create Risk field" if risk is None else "repair Risk field options")

    if not apply:
        return
    for repo in CONTROL_REPOS:
        for name, color, description in LABELS:
            run_gh(("label", "create", name, "--repo", f"{org}/{repo}", "--color", color,
                    "--description", description, "--force"))
    if status_names != STATUSES:
        options = [
            {"name": name, "color": color, "description": name}
            for name, color in zip(STATUSES, STATUS_COLORS, strict=True)
        ]
        payload = json.dumps({
            "query": "mutation($input:UpdateProjectV2FieldInput!){updateProjectV2Field(input:$input){projectV2Field{... on ProjectV2SingleSelectField{id}}}}",
            "variables": {"input": {"fieldId": status["id"], "singleSelectOptions": options}},
        })
        run_gh(("api", "graphql", "--input", "-"), input_text=payload)
    if risk is None:
        run_gh(("project", "field-create", str(number), "--owner", org, "--name", "Risk",
                "--data-type", "SINGLE_SELECT", "--single-select-options", "low,medium,high"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True, help="GitHub organization to reconcile")
    parser.add_argument("--apply", action="store_true", help="perform mutations; default is dry-run")
    args = parser.parse_args()
    try:
        reconcile(args.org, args.apply)
    except (SetupError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
