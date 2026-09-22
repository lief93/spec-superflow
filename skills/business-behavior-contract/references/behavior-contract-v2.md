# behavior-contract.v2

`behavior-contract.v2` records observable business behavior with traceable source proof. It separates four claims that must not be conflated:

1. **Inventory:** candidate behavior discovered in the chosen scope.
2. **Collection:** reviewed ownership, relationships, facts, scenarios, and exact source anchors.
3. **Closure:** every independently discovered source obligation is bound to reviewed records and scenarios.
4. **Execution:** optional target evidence shows a scenario actually ran; it does not repair incomplete source analysis.

## Fixed source snapshot

Create `.behavior-source-safe.json` at the snapshot root:

```json
{
  "schema_version": "behavior-source-snapshot.v1",
  "source_revision": "<immutable source identity>",
  "text_files": ["src/main/kotlin/example/Checkout.kt"],
  "text_file_sha256": {
    "src/main/kotlin/example/Checkout.kt": "<64 lowercase hex>"
  },
  "blocked_files": []
}
```

The tools reject absolute paths, parent traversal, symlinks, missing files, and stale hashes. Only listed source is read.

## Inventory and six-family review

Inventory items use `behavior-source-inventory.v1`. Broad categories such as `effect` or `data_flow` must declare the precise `record_kind` they require.

```bash
python3 scripts/collect_behavior_rules.py catalog
python3 scripts/collect_behavior_rules.py scaffold \
  --inventory inventory.json --output collection.json
```

The scaffold is intentionally `pending`. Review ownership; events/state/navigation; data; async/lifecycle; validation/security; and scenarios/evidence. Each family becomes `applicable` or `not_applicable` with a rationale and source anchors.

## Source census and closure

Choose an explicit page, flow, or application scope:

```json
{
  "schema_version": "behavior-source-scope.v1",
  "id": "checkout",
  "kind": "flow",
  "source_revision": "<same identity>",
  "entry_paths": ["src/main/kotlin/example/Checkout.kt"]
}
```

Generate the independent denominator:

```bash
python3 scripts/audit_behavior_source.py census \
  --snapshot snapshot --scope source-scope.json --output source-census.json
```

Copy the census identity into `source_closure` and bind every obligation to source-backed entity/fact records. Non-declaration obligations also require acceptance scenarios. Unresolved syntax, unavailable local source, stale hashes, missing bindings, and unknown bindings fail closed.

An independent `behavior-source-review.v1` must bind semantic expectations to the same `scope_sha256`, `census_sha256`, and contract digest. Structural coverage proves traceability, not that the authored interpretation is correct.

## Validation

```bash
python3 scripts/validate_behavior_contract_v2.py \
  --phase source \
  --contract behavior-contract.json \
  --inventory inventory.json \
  --snapshot snapshot \
  --source-scope source-scope.json \
  --source-review source-review.json
```

The source phase requires reviewed collection, complete inventory mapping, current source closure, an independent semantic review, acceptance scenarios, and no unresolved facts. Target mappings may remain `missing` during source review.

For target validation, every target mapping must be implemented and every scenario result must reference at least one JSON evidence record under `--target`:

```json
{
  "schema_version": "behavior-scenario-evidence.v1",
  "scenario_id": "SCN-SUBMIT",
  "source_revision": "<source identity>",
  "target_revision": "<target identity>",
  "scope_id": "checkout",
  "execution_status": "executed",
  "verdict": "pass"
}
```

Evidence paths cannot escape the target root. The evidence identities must match the contract, scope, and `behavior-scenario-results.v1` record.

## Limits

- Kotlin source scanning is conservative, not a compiler or type checker.
- Java files remain explicit unresolved dependencies until a semantic adapter is supplied.
- Hashes prove identity, not behavioral correctness.
- A source/test anchor proves provenance, not runtime parity.
- External libraries, platform behavior, and unavailable dependency internals remain unresolved unless separately evidenced.
