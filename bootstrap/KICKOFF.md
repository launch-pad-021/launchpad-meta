# Kickoff — start the multi-agent build

Prerequisite: `specs/16-human-setup.md` sections 1–2 done (accounts, GitHub org, Apps, secrets, variables, `launchpad-meta` + `launchpad-agent-kit` repos seeded). Server setup (section 3) can wait until M0.

## Phase 0 — bring the agent kit to life (A0), working locally
The automated pipeline doesn't exist yet, so A0 is built with you driving Claude Code locally, using the starter kit as its own guardrails.

1. Clone both repos side by side:
   ```bash
   git clone git@github.com:<org>/launchpad-meta && git clone git@github.com:<org>/launchpad-agent-kit
   ```
2. Install the adopted plugins once (user scope), then load the starter kit from disk while you work:
   ```text
   /plugin install superpowers@claude-plugins-official
   /plugin install pr-review-toolkit@claude-plugins-official
   /plugin install code-review@claude-plugins-official
   /plugin install security-guidance@claude-plugins-official
   /plugin install feature-dev@claude-plugins-official
   /plugin install frontend-design@claude-plugins-official
   /plugin install skill-creator@claude-plugins-official
   /plugin marketplace add trailofbits/skills        # then install the plugins listed in specs/12-agentic-system.md §8.1
   ```
   ```bash
   cd launchpad-meta && claude --plugin-dir ../launchpad-agent-kit/plugins/launchpad
   ```
   Review each third-party plugin's files before relying on it (A0-02 records the review and pins versions).
3. Ask the planner for the A0 plan:
   > Use the planner agent to produce the plan for milestone A0 from specs/11-delivery-plan.md. Write plans/A0.md on branch plan/A0 and open a PR.
4. Review and merge `plans/A0.md` (gate G1). Create the A0 issues (`gh issue create` from the plan, or let the agent do it once you approve).
5. Implement A0 issues one at a time in `launchpad-agent-kit` / `launchpad-meta`:
   > Use the implementer agent on issue #<n> in ../launchpad-agent-kit.
   Then in a **fresh session**: "Use the code-reviewer agent on PR #<n>". You merge (A0 is all `agent-config`).
6. A0 is done when `specs/11-delivery-plan.md` A0 "Done when" holds — notably: risk script tests pass, conductor runs, repos created from templates with rulesets, drills pass.

## Phase 1 — switch on the pipeline (autonomy P0)
1. Confirm org variable `AGENTS_ENABLED=true`.
2. Run the `planner` workflow for **M0** → review/merge `plans/M0.md` → the conductor creates issues and starts dispatching.
3. From here on, agents implement and review; **you merge every PR** during P0 (rulesets make this mandatory via CODEOWNERS until you relax them).
4. M0-01 produces `bootstrap/server.sh` in `launchpad-infra`: review it, then run it on the server yourself (agents never touch the server). Complete `specs/16-human-setup.md` §3–4.

## Phase 2 — graduate autonomy (per `specs/12-agentic-system.md` §22)
| When | Change |
|---|---|
| ≥ 20 agent PRs reviewed and you agreed with reviewer verdicts ≥ 90% | P1: enable auto-merge for **low** risk (remove developer CODEOWNERS for non-sensitive paths; keep high-risk paths) |
| 30 days at P1, change failure rate ≤ 10% | P2: auto-merge **medium** risk |
| M5 done + rollback drill passed twice | P3: auto release + deploy + rollback |
| Two incident game days handled correctly (H1-03) | P4: incident automation, CI self-repair, flaky quarantine |

## Daily rhythm (target ≤ 30 min)
- Read the Telegram digest (20:30 IST).
- Merge milestone plans (G1), approve high-risk PRs (G2), answer escalations (G3).
- Everything else runs without you. To stop everything: `AGENTS_ENABLED=false`.

## Prompts you'll reuse (owner comments)
- `/agent plan M<n>` — plan the next milestone.
- `/agent retry` — re-run the current stage on an issue/PR.
- `/agent hold` · `/agent take-over` · `/agent priority <n>`.
