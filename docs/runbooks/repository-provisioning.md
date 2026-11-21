# Repository provisioning

Checked against the A0 specification on 2026-11-21.

`scripts/create-repos.sh` is read-only unless `--apply --approved` is supplied.
The requested organization must exactly match the trusted organization environment
value, and repository names can only come from `bootstrap/templates/repos.json`.

Dry-run example:

```sh
env 'LP_'"ORG=launch-pad-021" scripts/create-repos.sh \
  --org launch-pad-021 --visibility public
```

Apply additionally requires the reviewed 40-character agent-kit commit and the
numeric GitHub Actions/check integration IDs. The live mutation adapter remains
fail-closed until the owner has installed and verified all four Apps, producer
IDs, CODEOWNER, organization plan capabilities, and ruleset policy. This is an
intentional A0-09 gate, not a condition the script guesses around.

The planner distinguishes `create`, owned `resume`, governed `noop`, and
refusal. It refuses an existing repository unless its visibility and
`launchpad-provision-v1` provenance marker match. It also refuses incomplete
organization discovery. Each apply stage is ordered as create, seed, settings,
ruleset, Apps, verify; a future owner-enabled adapter must persist each receipt
to the private journal before advancing and must re-read ambiguous results.

Never store credentials, account identifiers, raw GitHub responses, or the
journal in this repository. Do not retry an ambiguous repository creation or
initial push without discovery and provenance reconciliation.
