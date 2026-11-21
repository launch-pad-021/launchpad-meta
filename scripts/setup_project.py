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
STATUS_RENAMES = {"Todo": "Backlog", "In Progress": "In progress"}
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


def parse_object(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise SetupError("malformed GitHub response") from exc
    if not isinstance(value, dict):
        raise SetupError("malformed GitHub response")
    return value


def project_fields(org: str, number: int) -> list[dict]:
    raw = run_gh(("project", "field-list", str(number), "--owner", org, "--limit", "1000",
                  "--format", "json"))
    fields = parse_object(raw).get("fields")
    if not isinstance(fields, list) or not all(isinstance(field, dict) for field in fields):
        raise SetupError("malformed GitHub response")
    return fields


def field_by_name(fields: list[dict], name: str) -> dict | None:
    return next((field for field in fields if field.get("name") == name), None)


def option_names(field: dict | None) -> tuple[str, ...]:
    options = (field or {}).get("options", [])
    if not isinstance(options, list) or not all(
        isinstance(item, dict) and isinstance(item.get("name"), str) for item in options
    ):
        raise SetupError("malformed GitHub response")
    return tuple(item["name"] for item in options)


def reconciled_options(field: dict, expected: Sequence[str], colors: Sequence[str],
                       renames: dict[str, str], field_name: str) -> list[dict]:
    existing = field.get("options")
    if not isinstance(existing, list):
        raise SetupError("malformed GitHub response")
    by_target: dict[str, dict] = {}
    for option in existing:
        if not isinstance(option, dict) or not isinstance(option.get("name"), str):
            raise SetupError("malformed GitHub response")
        target = renames.get(option["name"], option["name"])
        if target not in expected:
            raise SetupError(f"existing {field_name} field has unsafe extra options")
        if target in by_target:
            raise SetupError(f"existing {field_name} field has ambiguous options")
        if not isinstance(option.get("id"), str) or not option["id"]:
            raise SetupError("malformed GitHub response")
        by_target[target] = option
    return [
        {**({"id": by_target[name]["id"]} if name in by_target else {}),
         "name": name, "color": color, "description": name}
        for name, color in zip(expected, colors, strict=True)
    ]


def update_select_field(field_id: str, options: list[dict]) -> None:
    payload = json.dumps({
        "query": "mutation($input:UpdateProjectV2FieldInput!){updateProjectV2Field(input:$input){projectV2Field{... on ProjectV2SingleSelectField{id}}}}",
        "variables": {"input": {"fieldId": field_id, "singleSelectOptions": options}},
    })
    run_gh(("api", "graphql", "--input", "-"), input_text=payload)


def verify_org(org: str) -> None:
    observed = run_gh(("api", f"orgs/{org}", "--jq", ".login")).strip()
    membership = run_gh(("api", f"user/memberships/orgs/{org}", "--jq", ".state")).strip()
    if observed != org or membership != "active":
        raise SetupError(f"authenticated user is not an active member of organization {org}")


def reconcile(org: str, apply: bool) -> None:
    expected_org = os.environ.get("LP_ORG")
    if not expected_org or not expected_org.strip():
        raise SetupError("LP_ORG must be set to the trusted organization")
    if expected_org != org:
        raise SetupError(f"--org {org} does not match LP_ORG")
    verify_org(org)

    response = parse_object(run_gh(("project", "list", "--owner", org, "--limit", "1000",
                                    "--format", "json")))
    projects = response.get("projects")
    if not isinstance(projects, list) or not all(isinstance(item, dict) for item in projects):
        raise SetupError("malformed GitHub response")
    matches = [item for item in projects if item.get("title") == "Launchpad"]
    if len(matches) > 1:
        raise SetupError("expected exactly one Launchpad Project; found multiple")
    project = matches[0] if matches else None
    if project is None:
        print("APPLY" if apply else "DRY RUN", f"organization={org}")
        print("create Launchpad Project")
        print(f"ensure {len(LABELS)} labels in each control repository")
        if not apply:
            return
        project = parse_object(run_gh(("project", "create", "--owner", org, "--title", "Launchpad",
                                       "--format", "json")))
    number = project.get("number")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise SetupError("malformed GitHub response")
    fields = project_fields(org, number)
    status = field_by_name(fields, "Status")
    risk = field_by_name(fields, "Risk")
    missing_builtins = [name for name in ("Milestone", "Repository") if field_by_name(fields, name) is None]
    if status is None or missing_builtins:
        raise SetupError("Launchpad Project is missing required built-in fields")

    status_names = option_names(status)
    risk_names = option_names(risk)
    status_target_names = tuple(STATUS_RENAMES.get(name, name) for name in status_names)
    status_update = status_target_names != STATUSES or status_names != STATUSES
    risk_expected = ("low", "medium", "high")
    risk_update = risk is not None and risk_names != risk_expected
    status_options = (
        reconciled_options(status, STATUSES, STATUS_COLORS, STATUS_RENAMES, "Status")
        if status_update else None
    )
    risk_options = (
        reconciled_options(risk, risk_expected, ("GREEN", "YELLOW", "RED"), {}, "Risk")
        if risk_update else None
    )
    print("APPLY" if apply else "DRY RUN", f"organization={org} project={number}")
    print(f"ensure {len(LABELS)} labels in each control repository")
    if status_update:
        print("update Status field options")
    if risk is None or risk_update:
        print("create Risk field" if risk is None else "repair Risk field options")

    if not apply:
        return
    for repo in CONTROL_REPOS:
        for name, color, description in LABELS:
            run_gh(("label", "create", name, "--repo", f"{org}/{repo}", "--color", color,
                    "--description", description, "--force"))
    if status_options is not None:
        update_select_field(status["id"], status_options)
    if risk is None:
        run_gh(("project", "field-create", str(number), "--owner", org, "--name", "Risk",
                "--data-type", "SINGLE_SELECT", "--single-select-options", "low,medium,high"))
    elif risk_options is not None:
        update_select_field(risk["id"], risk_options)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True, help="GitHub organization to reconcile")
    parser.add_argument("--apply", action="store_true", help="perform mutations; default is dry-run")
    args = parser.parse_args()
    try:
        reconcile(args.org, args.apply)
    except SetupError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
