#!/usr/bin/env bash
# PreToolUse(Bash): block destructive or out-of-scope commands. Exit 2 = block; stderr is shown to Claude.
set -euo pipefail
cmd=$(jq -r '.tool_input.command // ""')
deny=(
  'git[[:space:]]+push[[:space:]].*(--force|-f([[:space:]]|$)|--force-with-lease)'
  'git[[:space:]]+reset[[:space:]]+--hard'
  'git[[:space:]]+push[[:space:]].*[[:space:]](origin[[:space:]]+)?main([[:space:]]|$)'
  'rm[[:space:]]+-rf?[[:space:]]+(/|~|\$HOME|\.\.)'
  '(^|[;&|[:space:]])(ssh|scp|sftp)[[:space:]]'
  'curl[^|]*\|[[:space:]]*(ba)?sh'
  'wget[^|]*\|[[:space:]]*(ba)?sh'
  '(^|[;&|[:space:]])docker[[:space:]]'
  'gh[[:space:]]+(repo[[:space:]]+(delete|edit)|api[[:space:]].*(-X|--method)[[:space:]]*(DELETE|PUT|PATCH).*/(rulesets|branches/.*/protection|collaborators|hooks)|secret|variable|release[[:space:]]+delete)'
  'chmod[[:space:]]+-R[[:space:]]+777'
)
for re in "${deny[@]}"; do
  if [[ "$cmd" =~ $re ]]; then
    echo "Blocked by launchpad guard-bash: command matches a denied pattern ($re). See specs/12-agentic-system.md §14.5. If this is genuinely required, stop and escalate (label agent:blocked)." >&2
    exit 2
  fi
done
exit 0
