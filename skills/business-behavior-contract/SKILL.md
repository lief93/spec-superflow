---
name: business-behavior-contract
description: Extract and validate source-anchored business behavior contracts from Kotlin or Java frontend code. Use when behavior must be classified, traced to fixed source, and reviewed without generating target UI or implementation code.
---

# Business Behavior Contract

Create a reviewable `behavior-contract.v2` from real Kotlin/Java source. Keep unknown behavior explicit; names and previews are not evidence.

## Workflow

1. Fix the reviewed source set in `.behavior-source-safe.json`. Include only regular Kotlin/Java files and their SHA-256 values; never follow symlinks.
2. Build `behavior-source-inventory.v1` from concrete actions, state, navigation, effects, lifecycle, persistence, data flow, and platform effects.
3. Run `scripts/collect_behavior_rules.py scaffold` and review all six families. Replace every `unresolved` disposition with source-backed `applicable` or justified `not_applicable`.
4. Read the actual source and fill the contract, anchors, ownership, relationships, structured facts, scenarios, and source closure. Do not infer retry, security, cancellation, defaults, or dependency internals that are unavailable in source.
5. Run `scripts/audit_behavior_source.py census` against the fixed snapshot. Bind every discovered obligation, then obtain an independent `behavior-source-review.v1` over the current scope, census, and contract.
6. Run `scripts/validate_behavior_contract_v2.py --phase source`. Resolve every error; a hash-valid artifact is not a substitute for semantic review.
7. If a target implementation is being checked, record each executed scenario as `behavior-scenario-evidence.v1` and run the validator with `--phase target` and `--target`.

Read [references/behavior-contract-v2.md](references/behavior-contract-v2.md) for artifact shapes and commands. Read [references/semantic-transcription.md](references/semantic-transcription.md) when deciding whether source behavior has been preserved rather than merely renamed.

## Boundary

This Skill classifies and validates business behavior. It does not generate pages, UI code, projects, migration plans, capability graphs, execution plans, or business implementations.
