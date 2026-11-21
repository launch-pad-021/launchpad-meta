#!/usr/bin/env bash
# PreToolUse(Edit|Write|MultiEdit): agents may not change their own guardrails or secrets.
set -euo pipefail
path=$(jq -r '.tool_input.file_path // .tool_input.path // ""')
rel=${path#"${CLAUDE_PROJECT_DIR:-$PWD}/"}
case "$rel" in
  .github/*|.claude/*|CLAUDE.md|AGENTS.md|CODEOWNERS|*/CODEOWNERS|renovate.json|*.pem|*.key|.env|.env.*|secrets/*)
    echo "Blocked by launchpad guard-paths: '$rel' is a protected path (agent config or secrets). Open an issue labelled agent-config describing the change instead." >&2
    exit 2;;
esac
exit 0
