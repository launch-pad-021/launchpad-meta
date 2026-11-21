---
name: spec-to-issues
description: Turn a Launchpad milestone from specs/11-delivery-plan.md into a milestone plan of PR-sized, testable issues. Use when planning a milestone; not for implementation.
---
# spec-to-issues

Use superpowers `writing-plans` for how to structure tasks (exact files, verification steps, small increments); this skill adds Launchpad's sources, issue format and risk rules.

1. Read the milestone section in `specs/11-delivery-plan.md`, every service spec it references, `specs/03-conventions.md`, `specs/10-testing.md`, and existing issues for the milestone (avoid duplicates).
2. For each row, produce an issue entry:
   - **Title:** Conventional style (`deployer: saga compensation on health failure`).
   - **Repo**, **Depends on** (issue IDs), **Parallel-safe** (yes/no).
   - **Risk:** low/medium/high with the matching rule from `specs/12-agentic-system.md` §11.1.
   - **Acceptance criteria:** numbered, testable, derived from the service spec's Behavior/Tests/Acceptance sections. Quote the spec section you derived each from.
   - **Verification:** which test/check proves each criterion.
   - **Out of scope.**
3. Split any row expected to exceed ~400 changed lines into ordered sub-issues.
4. Cross-repo work follows contracts → producers → consumers.
5. Write `plans/<milestone>.md` and open a PR `plan: <milestone>`. Include an "Open questions" section for any ambiguity; never fill gaps with invented requirements.
