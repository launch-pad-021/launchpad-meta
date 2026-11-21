# 04 — Contracts

The `contracts/` directory in this pack is the **initial content of the `launchpad-contracts` repo**.

## 1. Layout
```
contracts/
├── proto/launchpad/
│   ├── common/v1/common.proto
│   ├── identity/v1/identity.proto
│   ├── projects/v1/projects.proto
│   ├── scm/v1/scm.proto
│   ├── deployer/v1/deployer.proto
│   ├── builder/v1/builder.proto
│   ├── runtime/v1/runtime.proto
│   ├── router/v1/router.proto
│   ├── logs/v1/logs.proto
│   ├── notifier/v1/notifier.proto
│   └── analytics/v1/analytics.proto
├── events/
│   ├── catalog.md                    every event: topic, producer, consumers, purpose
│   ├── envelope.schema.json
│   └── <type>.schema.json            one JSON Schema (draft 2020-12) per event type
├── buf.yaml  buf.gen.yaml           (created in M1)
```

## 2. Rules
- `buf lint` with the `STANDARD` rule set; `buf breaking --against` the latest release tag (`FILE` category).
- Package `launchpad.<service>.v1`; Go package `github.com/<org>/launchpad-contracts/gen/go/launchpad/<service>/v1;<service>v1`.
- Only additive changes in a `v1` package. Removing/renaming a field, RPC or enum value → new `v2` package (high risk, G2).
- Enum zero values are `*_UNSPECIFIED`.
- Every RPC and message has a comment; comments are the API documentation.
- Event schemas: `additionalProperties: true` on `data` for forward compatibility; required fields listed explicitly; a breaking change creates `<name>.v2`.

## 3. Generated clients (published on each tag by CI)
| Language | Output | Published as |
|---|---|---|
| Go | `gen/go/...` (protoc-gen-go, protoc-gen-go-grpc) | Go module (git tag) |
| TypeScript | `gen/ts/...` (protoc-gen-es) | `@<org>/launchpad-contracts` on GitHub Packages |
| Python | `gen/python/...` (grpcio-tools) | wheel `launchpad-contracts` on GitHub Packages |
| Rust | `gen/rust/...` (prost + tonic via buf remote plugins) | crate via git dependency on the tag |
| Event types | Go structs, TS types (json-schema-to-typescript), Python pydantic models, Rust serde structs | same packages |

## 4. Versioning
SemVer tags `vX.Y.Z` via release-please. Additive change → minor. Consumers pin exact versions; Renovate bumps them.

## 5. Ownership
CODEOWNERS: developer owns `proto/**` and `events/**` for breaking changes; additive changes are medium risk and need `architecture-reviewer` approval (see `12-agentic-system.md` §11).
