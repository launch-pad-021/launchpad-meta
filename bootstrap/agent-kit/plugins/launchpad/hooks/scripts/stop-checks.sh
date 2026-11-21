#!/usr/bin/env bash
# Stop: run fast checks for the repo's language; if they fail, keep Claude working via {"decision":"block"}.
set -uo pipefail
input=$(cat)
# Avoid infinite loops: if this stop was already triggered by a stop hook, allow stopping.
if [ "$(echo "$input" | jq -r '.stop_hook_active // false')" = "true" ]; then exit 0; fi
out=""; rc=0
run() { local o; o=$("$@" 2>&1) || { rc=1; out+=$'\n'"\$ $*"$'\n'"$(echo "$o" | tail -40)"; }; }
if [ -f go.mod ]; then run gofmt -l . ; [ -z "$(gofmt -l . 2>/dev/null)" ] || { rc=1; out+=$'\nFiles need gofmt.'; }; run go vet ./... ; run go test ./... -count=1 -short
elif [ -f Cargo.toml ]; then run cargo fmt --check; run cargo clippy --quiet -- -D warnings; run cargo test --quiet
elif [ -f pyproject.toml ]; then run uv run ruff check; run uv run ruff format --check; run uv run pytest -q -x -m "not integration"
elif [ -f package.json ]; then run npx --no-install tsc --noEmit; run npx --no-install eslint . ; run npx --no-install vitest run
fi
if [ $rc -ne 0 ]; then
  jq -n --arg r "Fast checks failed. Fix them before finishing (or write a handoff note explaining why they cannot pass):$out" '{decision:"block", reason:$r}'
fi
exit 0
