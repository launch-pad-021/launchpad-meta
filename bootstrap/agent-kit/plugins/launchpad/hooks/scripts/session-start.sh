#!/usr/bin/env bash
# SessionStart: print cheap starting context (stdout becomes context).
set -uo pipefail
echo "## Launchpad session context"
echo "Repo: $(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")  Branch: $(git branch --show-current 2>/dev/null)"
echo "Rules: read CLAUDE.md, AGENTS.md and the issue first. Conventions: launchpad-meta/specs/03-conventions.md."
git status --short 2>/dev/null | head -20
if [ -n "${LP_ISSUE_NUMBER:-}" ] && command -v gh >/dev/null; then
  echo "### Issue #$LP_ISSUE_NUMBER"
  gh issue view "$LP_ISSUE_NUMBER" --json title,body -q '.title + "\n" + .body' 2>/dev/null | head -80
  echo "### Latest handoff note"
  gh pr list --head "$(git branch --show-current)" --json number -q '.[0].number' 2>/dev/null | xargs -r -I{} gh pr view {} --comments --json comments -q '[.comments[] | select(.body | startswith("### Handoff"))] | last | .body' 2>/dev/null | head -40
fi
exit 0
