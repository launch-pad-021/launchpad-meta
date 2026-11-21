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

Apply additionally requires the reviewed 40-character agent-kit commit, the
numeric GitHub Actions/check integration IDs, and the owner-visible installation
ID for every App role assigned to a target. For example, an owner-approved call
includes `--ci-integration-id`, `--review-integration-id`, and one or more
`--app-installation ROLE=ID` arguments. The checked-in agent-kit revision is the
default; an override still has to be a full commit SHA. Missing producer or App
evidence fails before a repository mutation.

The planner distinguishes `create`, owned `resume`, governed `noop`, and
refusal. It refuses an existing repository unless its visibility and
`launchpad-provision-v1` provenance marker match. It also refuses incomplete
organization discovery. Each apply stage is ordered as create, seed, settings,
ruleset, Apps, verify. The owner-session adapter persists each confirmed stage
to a mode-0600 private journal and reads GitHub back before advancing. A lost
repository-create response is reconciled by marker, identity, and visibility;
an ambiguous initial push is accepted only when the remote tree matches the
locally rendered tree. Existing marker-bearing repositories without a matching
local receipt are refused.

Never store credentials, account identifiers, raw GitHub responses, or the
journal in this repository. Do not retry an ambiguous repository creation or
initial push without discovery and provenance reconciliation.
