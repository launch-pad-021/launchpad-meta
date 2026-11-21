# launchpad-agent-kit (starter)

Claude Code plugin + reusable workflows for building Launchpad with agents. This is the **starter** shipped in the spec pack; milestone **A0** completes it (`launchpad-meta/specs/11-delivery-plan.md`).

## Layout
```
.claude-plugin/marketplace.json        # this repo is a plugin marketplace with one plugin: "launchpad"
plugins/launchpad/
  .claude-plugin/plugin.json           # only the manifest lives here
  agents/        planner, implementer, code-reviewer, correctness-verifier, ci-fixer   (+12 more in A0-06)
  skills/        spec-to-issues, implement-issue, launchpad-review-gate   (Launchpad glue only; engineering skills come from adopted plugins)
  hooks/hooks.json + hooks/scripts/    session-start, guard-bash, guard-paths, stop-checks
schemas/review.schema.json             # reviewer JSON output (enforced with --json-schema)
scripts/risk.py + test_risk.py         # deterministic risk classifier (16 tests)
.github/workflows/agent-implement.yml  # reusable: implement one issue
.github/workflows/agent-review.yml     # reusable: risk + parallel reviewers → commit statuses
```

## Adopted plugins (not copied here)
superpowers, pr-review-toolkit, code-review, security-guidance, feature-dev, frontend-design, commit-commands, skill-creator, LSP plugins (all `@claude-plugins-official`); Trail of Bits `static-analysis`, `variant-analysis`, `differential-review`, `fix-review`, `insecure-defaults`, `sharp-edges`, `agentic-actions-auditor`; `anthropics/skills` `webapp-testing`. See `launchpad-meta/specs/12-agentic-system.md` §8.

## Use
- Locally: `claude --plugin-dir ./plugins/launchpad`
- In CI (claude-code-action@v1): `plugin_marketplaces` lists the official, Trail of Bits and this marketplace (newline-separated); `plugins` lists `launchpad@launchpad-agent-kit` plus the adopted plugins; skills are invoked as `/launchpad:<skill>` or `/superpowers:<skill>`.

## Verify during A0
- Exact plugin and marketplace names for the adopted set (`/plugin` → browse), and pin them.
- Marketplace/plugin JSON fields against https://code.claude.com/docs/en/plugin-marketplaces and plugins-reference.
- Subagent frontmatter (`tools`, `model`) against https://code.claude.com/docs/en/sub-agents.
- The claude-code-action structured-output output name used in `agent-review.yml`.
- `scripts/test_risk.py`: `python3 -m pytest -q scripts/`.

Changes to this repo are `agent-config`: only the developer merges.
