---
name: launchpad-review-gate
description: Run the assigned adopted review agents on a Launchpad PR and convert their findings into the Launchpad reviewer JSON schema for the merge gate. Use in the agent-review workflow; never writes code.
---
# launchpad-review-gate

1. Determine your reviewer role from the prompt (code, security, design, database, docs, deps, correctness).
2. Run the matching adopted reviewers on the PR diff (`origin/<base>...HEAD`):
   | Role | Use |
   |---|---|
   | code | `pr-review-toolkit` agents (code, tests, silent failures, types) + `code-review` |
   | security | Trail of Bits `differential-review`, `insecure-defaults`, `sharp-edges`; `security-guidance` review; check `specs/08-security.md` controls for touched areas |
   | agent-config | Trail of Bits `agentic-actions-auditor` on changed workflows |
   | design | `frontend-design` principles + `webapp-testing` screenshots at 375/768/1280 |
   | database | `specs/05-data.md` §6 expand/contract rules; `EXPLAIN` evidence for query changes |
   | correctness | map each acceptance criterion in the linked issue to a test and a passing CI job (superpowers `verification-before-completion` standard) |
3. Add Launchpad checks the adopted tools don't know: conformance to `contracts/` and `specs/03-conventions.md` (errors, envelope, outbox, config, logging), and the service spec's acceptance criteria.
4. Keep only findings with a concrete file/line, trigger and impact. Drop low-confidence findings rather than guessing.
5. Output **only** JSON matching `schemas/review.schema.json` (`specs/12-agentic-system.md` §9.3). Use `needs_human` when the change is high risk or outside what you can judge.
