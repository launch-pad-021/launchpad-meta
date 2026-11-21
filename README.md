# Launchpad — Build Specification Pack

**Version:** 1.0 · **Date:** 21 November 2026 · **Owner:** Tejas
**What this is:** the complete, agent-ready specification for building **Launchpad**, a self-hosted PaaS (mini Vercel/Railway) with built-in analytics, using a multi-agent Claude Code development system.

Everything an agent needs to plan, implement, review, deploy and operate Launchpad is in this pack. Version-sensitive facts were checked against primary sources on 21 Nov 2026 (see `specs/15-verification-log.md`).

---

## How to use this pack

1. **Developer (once):** complete `specs/16-human-setup.md` — accounts, GitHub org, bot Apps, server, DNS, secrets. Agents cannot do these steps.
2. **Developer:** create the `launchpad-meta` repo and copy this whole pack into it. Copy `bootstrap/launchpad-meta/CLAUDE.md` to its root.
3. **Start the build:** follow `bootstrap/KICKOFF.md`. Milestone **A0** builds the agent kit; then the planner works through **M0–M12** in `specs/11-delivery-plan.md`.

## Reading order by role

| Role | Must read | Read when relevant |
|---|---|---|
| Every agent | `README.md`, `specs/03-conventions.md`, the issue, the service spec for its repo | `specs/01-architecture.md` |
| Planner | `specs/11-delivery-plan.md`, `specs/00-product.md`, `specs/01-architecture.md` | everything else |
| Implementer | `specs/services/<service>.md`, `specs/03-conventions.md`, `contracts/` | `specs/05-data.md`, `specs/06-public-api.md`, `specs/10-testing.md` |
| Reviewers | the PR, the service spec, `specs/03-conventions.md`, `specs/08-security.md` | `specs/01-architecture.md` |
| Release / incident | `specs/07-infrastructure.md`, `specs/13-runbooks.md`, `specs/09-observability.md` | — |
| Developer | `specs/12-agentic-system.md` §2, `specs/16-human-setup.md` | — |

## Contents

| Path | Purpose |
|---|---|
| `specs/00-product.md` | Vision, users, scope, features, non-goals, glossary |
| `specs/01-architecture.md` | Services, communication rules, deploy saga, Insights integration |
| `specs/02-tech-stack.md` | Pinned versions (verified), why each was chosen, upgrade policy |
| `specs/03-conventions.md` | Cross-language rules: IDs, errors, events, config, logging, naming, repos |
| `specs/04-contracts.md` | Guide to `contracts/` — gRPC services and the event catalog |
| `specs/05-data.md` | Postgres schemas per service, ClickHouse schemas, retention |
| `specs/06-public-api.md` | Gateway REST + SSE API used by the dashboard and CLI |
| `specs/07-infrastructure.md` | Server, compose, networks, Traefik, TLS, BuildKit, registry, GitOps deploy, backups |
| `specs/08-security.md` | Threat model, controls per service, secrets inventory |
| `specs/09-observability.md` | Metrics, alerts, SLOs, tracing, logs, Platform page |
| `specs/10-testing.md` | Test strategy per language, fixtures, E2E, contract and chaos tests |
| `specs/11-delivery-plan.md` | Milestones A0, M0–M12, H1 with every issue, dependencies and parallel tracks |
| `specs/12-agentic-system.md` | How the agents work: autonomy, gates, pipeline, guardrails, metrics |
| `specs/13-runbooks.md` | Deploy, rollback, restore, rotate secrets, incidents |
| `specs/14-decisions.md` | Architecture Decision Records (ADR log) |
| `specs/15-verification-log.md` | What was verified, sources, and what changed because of it |
| `specs/16-human-setup.md` | Developer's one-time setup checklist |
| `specs/services/*.md` | One spec per service/repo (15 files) |
| `contracts/proto/` | gRPC definitions (protobuf) — source for `launchpad-contracts` |
| `contracts/events/` | JSON Schemas for every event + `catalog.md` |
| `bootstrap/` | Kickoff guide, `launchpad-meta` CLAUDE.md, repo templates, agent-kit starter |

## Normative language
**MUST / MUST NOT** = required; violating it fails review. **SHOULD** = default; deviations need a reason in the PR. **MAY** = optional.
When two documents disagree, precedence is: `contracts/` > service spec > `03-conventions.md` > other specs. Agents MUST report any contradiction they find as an issue labelled `spec-bug` instead of guessing.
