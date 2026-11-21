#!/usr/bin/env python3
"""Fetch authoritative Project state and execute one bounded conductor cycle."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

from agent_control import GitHubAdapter, PolicyError, execute_cycle


PROJECT_QUERY = """query($id:ID!,$after:String){node(id:$id){... on ProjectV2{items(first:100,after:$after){nodes{
  id fieldValues(first:20){nodes{... on ProjectV2ItemFieldSingleSelectValue{name field{... on ProjectV2FieldCommon{name}}}}}
  content{... on Issue{id number body state repository{name} labels(first:100){nodes{name}}}}
} pageInfo{hasNextPage endCursor}}}}}"""


def section(body: str, heading: str) -> str:
    match = re.search(rf"(?ims)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)", body)
    return match.group(1).strip() if match else ""


def project_snapshot(adapter: GitHubAdapter, *, daily: int, per_run: int, owner_login: str) -> dict:
    if adapter.enabled() is not True:
        return {"enabled": False}
    nodes, cursor = [], None
    while True:
        data = adapter._graphql(PROJECT_QUERY, {"id": adapter.project_id, "after": cursor})
        project = data.get("node")
        connection = project.get("items") if isinstance(project, dict) else None
        page = connection.get("nodes") if isinstance(connection, dict) else None
        page_info = connection.get("pageInfo") if isinstance(connection, dict) else None
        if not isinstance(page, list) or not isinstance(page_info, dict):
            raise PolicyError("project-items-malformed")
        nodes.extend(page)
        if page_info.get("hasNextPage") is not True:
            break
        cursor = page_info.get("endCursor")
        if not isinstance(cursor, str) or not cursor:
            raise PolicyError("project-pagination-malformed")
    items = []
    by_ref = {}
    for position, node in enumerate(nodes):
        content = node.get("content") if isinstance(node, dict) else None
        if not isinstance(content, dict) or content.get("state") != "OPEN":
            continue
        repository = content.get("repository") or {}
        repo = repository.get("name")
        number = content.get("number")
        if not isinstance(repo, str) or not isinstance(number, int):
            raise PolicyError("project-issue-malformed")
        fields = {}
        for value in node.get("fieldValues", {}).get("nodes", []):
            field = value.get("field") if isinstance(value, dict) else None
            if isinstance(field, dict) and isinstance(field.get("name"), str):
                fields[field["name"]] = value.get("name")
        labels = [label.get("name") for label in content.get("labels", {}).get("nodes", [])
                  if isinstance(label, dict) and isinstance(label.get("name"), str)]
        body = content.get("body") or ""
        issue_id = str(content.get("id"))
        item = {"id": issue_id, "project_item_id": node.get("id"), "repo": repo,
                "issue_number": number, "position": position, "status": fields.get("Status"),
                "risk": fields.get("Risk", "low"), "labels": labels,
                "fields_complete": all(section(body, name) for name in
                    ("Plan ID", "Repo", "Context", "Acceptance criteria", "Out of scope",
                     "Depends on", "Risk", "Risk reason", "Verification", "Agent notes"))
                    and section(body, "Repo") == repo,
                "developer_ack": False,
                "attempts": 0, "dependencies": [], "_body": body}
        items.append(item)
        by_ref[f"{repo}#{number}"] = issue_id
    for item in items:
        if item["risk"] != "high":
            continue
        comments = adapter._api(
            f"repos/{adapter.org}/{item['repo']}/issues/{item['issue_number']}/comments?per_page=100")
        if not isinstance(comments, list):
            raise PolicyError("approval-comments-malformed")
        item["developer_ack"] = any(
            isinstance(comment, dict)
            and (comment.get("user") or {}).get("login") == owner_login
            and str(comment.get("body", "")).strip() == "/agent approve"
            for comment in comments
        )
    for item in items:
        raw = section(item.pop("_body"), "Depends on")
        if raw.lower() not in {"", "none", "n/a"}:
            refs = re.findall(r"(?:launch-pad-[a-z0-9-]+)?#\d+", raw)
            refs += [f"{repo}#{number}" for repo, number in re.findall(
                r"github\.com/[^/]+/(launchpad-[a-z0-9-]+)/issues/(\d+)", raw)]
            normalized = [ref if not ref.startswith("#") else f"{item['repo']}{ref}" for ref in refs]
            item["dependencies"] = [by_ref.get(ref, f"unknown:{ref}") for ref in normalized]
    records = adapter._load_records()
    for item in items:
        item["attempts"] = adapter.attempt_counts.get(item["id"], 0)
    return {"enabled": True, "event_id": os.environ.get("GITHUB_RUN_ID", "manual"),
            "daily_budget_micros": daily, "per_run_budget_micros": per_run,
            "spent_micros": 0, "active": [], "reservations": [], "items": items}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--org", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--status-field-id", required=True)
    parser.add_argument("--in-progress-option-id", required=True)
    parser.add_argument("--control-issue", required=True, type=int)
    parser.add_argument("--owner-login", required=True)
    parser.add_argument("--daily-budget-micros", required=True, type=int)
    parser.add_argument("--per-run-budget-micros", required=True, type=int)
    args = parser.parse_args(argv)
    try:
        adapter = GitHubAdapter(org=args.org, project_id=args.project_id,
            status_field_id=args.status_field_id, in_progress_option_id=args.in_progress_option_id,
            control_issue=args.control_issue)
        snapshot = project_snapshot(adapter, daily=args.daily_budget_micros,
                                    per_run=args.per_run_budget_micros,
                                    owner_login=args.owner_login)
        result = execute_cycle(snapshot, adapter, dry_run=args.dry_run)
    except PolicyError as error:
        print(json.dumps({"version": 1, "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
