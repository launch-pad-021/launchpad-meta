# Agent control-plane runbook

## Status and boundary

The control plane is fail-closed at P0. `scripts/agent_control.py` makes policy
decisions from a typed snapshot; it never reads GitHub or performs a mutation.
Workflow jobs start with `permissions: {}` and grant read access only where a
job needs it. Mutating workflows default to dry-run.

The durable interface is `agent-result-v1`. A dispatch intent contains a
deterministic `dispatch_id`, issue identity, stage, attempt ordinal and reserved
USD micros. A receiver must fetch and claim that lease from the trusted control
store before starting a model. Event payload text does not grant authority.

## Local evidence

```sh
python3 scripts/agent_control.py --dry-run \
  --snapshot tests/fixtures/agent_control/dry-run.json
make test
make validate
```

Dry-run uses `DryRunAdapter`; every mutation method raises
`dry-run-mutation-denied`. The fixture result is only a proposal and cannot
reserve budget, change a Project item, dispatch a workflow or post a comment.

## Reconciliation rules

- Only exact boolean `enabled: true` proceeds. Live jobs must also read the org
  variable before every lease, Project mutation, dispatch and model start.
- Count active leases and unowned `In progress` items together. The maximum is
  three implementers.
- Reserve integer USD micros before dispatch. Missing usage remains charged at
  its reservation until authoritative evidence resolves it.
- A `sending` dispatch with an ambiguous response is never sent again. Reconcile
  it from workflow run and receiver-claim evidence; otherwise block once.
- Handoffs have stable keys. A replay may update a known bot-owned note, but must
  not repeat an ambiguous comment creation.
- Dependency, pagination, GraphQL partial-error, stale-head, malformed-budget
  and authorization uncertainty all deny work.

## Live enablement gates

Live apply is intentionally unavailable until the owner configures and verifies:

1. a control-plane GitHub App installation with organization Projects read/write,
   organization/repository Variables read, and scoped cross-repository Actions,
   Issues and Pull Requests read;
2. a separate narrowly scoped writer for the ledger ref, target dispatch,
   Project updates and confirmed handoffs;
3. finite `LP_AGENT_DAILY_BUDGET_USD`, daily run cap and per-role run caps;
4. a provider API credential whose budget semantics enforce USD caps;
5. an immutable agent-kit release and thin caller contract using
   `{"version":1,"issue":7,"dispatch_id":"opaque-lease-id"}`;
6. a default-branch GitHub Actions dry-run proving that write tokens and mutation
   adapters are absent.

Do not replace these with a personal token or `secrets: inherit`. The current
workflow writes a clear failing summary if a user requests live apply before the
installation is proven.

## Recovery

Set `AGENTS_ENABLED=false`, then inspect the ledger head, Project item, workflow
run and receiver result for the exact dispatch ID. Do not retry an ambiguous
write. Once evidence is reconciled, record a terminal result or recoverable
paused lease, then re-enable. Preserve the evidence link and reason code in the
single handoff note.
