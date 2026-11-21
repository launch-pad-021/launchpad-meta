#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)

run_quiet() {
  local log
  log=$(mktemp "${TMPDIR:-/tmp}/launchpad-bootstrap.XXXXXX")
  if ! "$@" >"$log" 2>&1; then
    rm -f "$log"
    echo "Bootstrap command failed: $1" >&2
    return 1
  fi
  rm -f "$log"
}

seed_agent_kit() {
  if [ "$#" -ne 1 ]; then
    echo "usage: $0 --seed-agent-kit DESTINATION" >&2
    exit 2
  fi
  exec python3 "$root/scripts/seed_agent_kit.py" "$1"
}

mode=detect
case "${1:-}" in
  "") ;;
  --install) mode=install; shift ;;
  --seed-agent-kit) shift; seed_agent_kit "$@" ;;
  *) echo "usage: $0 [--install | --seed-agent-kit DESTINATION]" >&2; exit 2 ;;
esac
[ "$#" -eq 0 ] || { echo "usage: $0 [--install | --seed-agent-kit DESTINATION]" >&2; exit 2; }

os=$(uname -s)
arch=$(uname -m)
if command -v mise >/dev/null 2>&1; then
  mise_state=present
else
  mise_state=missing
fi
printf 'Launchpad local bootstrap: OS=%s architecture=%s mise=%s\n' "$os" "$arch" "$mise_state"

if [ "$mode" = detect ]; then
  echo "No host changes made. To install the pinned toolchain, run: scripts/bootstrap-local.sh --install"
  exec "$root/scripts/preflight.sh" --phase step-minus-one
fi

if ! command -v mise >/dev/null 2>&1; then
  if [ "$os" = Darwin ] && command -v brew >/dev/null 2>&1; then
    run_quiet brew install mise
    hash -r
  else
    echo "Install mise manually from https://mise.jdx.dev/getting-started.html, then rerun --install." >&2
    exit 1
  fi
fi

cd "$root"
run_quiet mise install
run_quiet mise lock
while IFS= read -r tool_path; do
  [ -n "$tool_path" ] && PATH="$tool_path:$PATH"
done < <(mise env --paths)
export PATH
hash -r
exec "$root/scripts/preflight.sh" --phase step-minus-one --strict
