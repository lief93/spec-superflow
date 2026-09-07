# Frontend behavior contract v2

Use `behavior-contract.v2` to make the existing `behavior_contract` gate prove observable
business parity. The migration inventory remains a broad candidate file and capability inventory;
it does not replace this page- or flow-level contract.

## Implementation authority

Read [semantic-transcription.md](semantic-transcription.md) when implementing business logic.
The contract describes the source's actual semantics, including defects; it does not authorize
cleaning up suspicious behavior or generating a replacement implementation from summaries alone.
Read the bound complete source definitions and dependencies while writing target methods. Reuse
the existing actions, states, data flows, async/lifecycle facts, scenarios and
`traceability.target_implementation` mappings; no new business DSL or contract version is needed.
Unknown source behavior remains unresolved even if a plausible target implementation compiles.

## Artifacts

Create these files outside the read-only Android source tree:

- `behavior-source-inventory.v1.json`: every source behavior fact in the selected page or flow.
- `behavior-contract.v2.json`: platform-neutral behavior and target traceability.
- `behavior-scenario-results.v1.json`: target runtime results for every contract scenario.
- `behavior-contract-validation.v2.json`: deterministic validator output.

The schemas are under `assets/behavior-source-inventory-v1.schema.json` and
`assets/behavior-contract-v2.schema.json`.

## Categorized collection

The required `collection` extension uses `assets/behavior-collection-v1.schema.json`.
The maintained rules live in `assets/behavior-collection-rules.json`: six families,
each with applicability questions, inspection locations, structured fields and verification
responsibilities. This adapts the categorized collection, progressive loading, scaffold and
verification mechanism discussed in https://mp.weixin.qq.com/s/ESWOKhUzBSJWutPqLSMdiA
to Android frontend ownership and behavior. It does not import Go conventions or presume
source-app retry, security, cancellation or persistence policies.

Through the normal migration workflow, the agent invokes this internal maintainer helper:

```bash
python3 "$SKILL_ROOT/scripts/collect_behavior_rules.py" catalog
python3 "$SKILL_ROOT/scripts/collect_behavior_rules.py" scaffold \
  --inventory "$BEHAVIOR_INVENTORY" --output "$NEW_COLLECTION"
python3 "$SKILL_ROOT/scripts/collect_behavior_rules.py" selected --collection "$COLLECTION"
```

The scaffold contains all inventory IDs and all six categories as `unresolved`, with
`status: pending`. Selection returns the full applicability index but loads detailed rules
only for `applicable` families. These are internal tools, not an additional user workflow.
Embed the reviewed object as `contract.collection`; preserve every existing v2 section.
Every category needs a source-anchored rationale and either applicable record IDs,
evidenced `not_applicable`, or an explicit `unresolved` disposition. Missing/unknown decisions,
pending scaffolds and unavailable source details fail both normal validation phases.

Entities use `page`, `definition`, `instance`, or `dependency`. A page has no owner;
other entities have one `owner_id`, and instances reference a reusable `definition_id`.
State and shared data definitions occur once, with a source `symbol` on each
definition/dependency; repeated primary-path/symbol definitions fail. When an entity
has anchors from multiple files, `definition_anchor_id` must identify its definition
source anchor; supplemental references do not change that identity. A single source
path supplies the default. Distinct definitions in different source files may share a name.
Relationships reference entity endpoints
with nonempty `bindings` of kind `input`, `event`, or `dependency`, each carrying `from`,
`to`, and an exact source `expression`. Facts reference their owner, inventory IDs,
anchors and existing action/state/navigation/scenario `contract_ids`. Source-inventory
coverage still comes from the original contract sections, never from collection alone.
Independently, every inventory item must have a structured collection fact of its required
`record_kind`. A category that is already a fact kind (such as `action` or `state`) supplies
that default; broad inventory categories (`effect`, `data_flow`, `persistence`,
`platform_effect`) require an explicit `record_kind` chosen during source inventory.
Entity, relationship or scenario associations cannot substitute for a missing data,
async, branch or lifecycle fact. The validator reports `collection.source_fact_coverage`
separately from the original contract mapping coverage. Marking a family not applicable
cannot remove an already inventoried behavior from this check.

Facts use the kinds and fields listed in the rule catalog. `source_expressions` must occur
in linked source spans. Branch `cases` hold `condition`, `outcome`, and the exact
`source_clause` containing one Kotlin `when` arm: the exact condition before its sole
`->`, and the outcome after it. Clauses spanning adjacent arms, nested-arrow constructs
or unsupported branch forms remain unresolved rather than receiving an inferred proof.
Async records bind `entry` and `normal` expressions in source order within `scope_anchor_id`.
Their `failure`/`cancellation` records carry `disposition: observed` with `expression`, or
`absent_local` with rationale, plus `scope_anchor_id`. An observed expression must occur
inside an explicit local handler body in that async scope: catch/finally for failure,
finally/invokeOnCancellation/catch(CancellationException) for cancellation. A normal-return
write elsewhere cannot prove either outcome. Unsupported handler forms remain unresolved.
Local absence checks look for relevant
catch/finally/cancellation hooks in that exact scope; they do not prove library behavior.
Use unresolved when the relevant scope cannot be established. Data/check records with
`availability` other than `available` remain blocking.

Each anchor has `id`, `kind: source|test`, a snapshot-relative `path`, inclusive 1-based
`start_line`/`end_line`, `file_sha256` and `span_sha256`. Span hashes cover the exact UTF-8
lines including their original line terminators. Test anchors also name `Class.method`;
the span must contain the complete class body and annotated Kotlin test method in a test
source set. Comments and literals do not establish a test declaration.
Inventory `source_evidence` and scenario `android_evidence` contain these anchor IDs, not
free-form test names. The validator independently validates the safe snapshot before any
anchor reads and rejects excluded files, symlinks, stale hashes and nonexistent symbols.

These checks prove structure and source provenance. A reviewer must still check semantic
truth, complete function scopes, branch exhaustiveness and the page/flow denominator.
Unreferenced source behavior cannot be inferred from a filled form; neither a source pass
nor a test-symbol anchor establishes executed Android/Harmony parity. Keep unavailable
repository implementations and runtime concerns explicit in `unresolved` or excluded scope.

## Collection order

### Independent source closure

Before authoring facts, freeze `behavior-source-scope.v1` separately from the candidate contract:
`id`, `kind: page|flow|application`, fixed `source_revision`, and snapshot-relative `entry_paths`.
Choose the full requested surface, including its component and state/data entry points. Do not
shrink a page to a convenient handler to obtain a pass. The closure/review schemas are in
`assets/behavior-source-closure-v1.schema.json` (scope and review are under `$defs`).

```bash
python3 "$SKILL_ROOT/scripts/audit_behavior_source.py" census \
  --snapshot "$SNAPSHOT" --scope "$BEHAVIOR_SOURCE_SCOPE" \
  --output "$RUN_ROOT/behavior-source-census.json"
```

The census reads only independently validated snapshot production Kotlin/Java paths. It derives
local dependencies from imports (including aliases) and same-package classes, generic functions,
and properties. Entry files are complete. Transitive dependencies retain complete top-level
classes/objects/functions/properties (including accessors), rather than every unrelated definition
in an imported file; every reached class still includes all its members. The census retains complete Kotlin callables and
separate balanced declaration/state/decision/operation regions, and binds all source files,
regions, scope and snapshot hashes. Application scope includes every approved production source
file. Required privacy-blocked source and unsupported syntax remain unresolved without being read.

This is a conservative **source coverage ledger**, not a Kotlin compiler or a semantic extractor.
Import edges are candidate dependencies, not proof of runtime dispatch. The agent and independent
reviewer must trace interface implementations/DI, callback/lambda ownership, scheduled work,
source-available helpers, mappers and persistence, and add missing entry files to the frozen scope.
External APIs/platform behavior must be specified at their observed interface or left unresolved;
an import listing does not establish backend or library correctness. Unknown expressions remain
in the ledger rather than disappearing because no keyword category matched.

Populate `contract.source_closure` with `schema_version: behavior-source-closure.v1`,
`census_sha256`, canonical `inventory_sha256` and `bindings`. The inventory hash makes changes to
the inventory's meaning invalidate the bound source review as well. Every binding has one `obligation_id`, `record_ids` of existing
typed collection facts/entities, and acceptance `scenario_ids`. Bind exact region expressions
and source anchors covering the whole region. A broad function anchor cannot substitute for
its separately enumerated operations or decisions; decision regions need branch/check facts.
The normal validator regenerates the denominator, rejecting missing, duplicate, unknown or stale
bindings even when the inventory and facts were deleted together.

An actual independent reviewer then writes `behavior-source-review.v1`, binding the exact
`scope_sha256`, `census_sha256`, and canonical `contract_sha256`, reviewer identity, verdict,
`unresolved`, examined `dependency_edges`/`external_dependencies`, and independent `expectations`.
Each expectation has stable `id`, source-grounded `summary`, and `obligation_ids`, `record_ids`,
`scenario_ids`; every named proof must exist and be bound to the named obligations, and together
they must cover the current denominator. Summaries describe actual
branch precedence, inputs, outcomes, sequencing and observables, not "reviewed this line".
Use the project's persistent independent reviewer, without asking the user to approve each
engineering step. The developer must not manufacture the review file. Hashes bind a review's
scope; they cannot determine whether its semantic judgment is true. Canonical hashes use UTF-8
JSON with sorted keys, separators `(',', ':')`, `ensure_ascii=False`, plus one newline.

Keep source-model completeness separate from runtime correctness. In particular, asynchronous
submission is not settlement; mapper failure may skip persistence; create/delete operations on
different stores need not be atomic; and independent launched coroutines are not ordered merely
because their calls appear consecutively. Preserve source behavior and explicit defects rather
than silently replacing them with idealized retry, rollback, validation or notification policies.

### Collect the behavior model

1. Freeze one page or connected flow and its Android source revision.
2. Inventory routes, parameters, return results, user/system triggers, state-holder commands,
   state fields, repository or platform effects, persistence, and lifecycle behavior.
3. Trace each trigger from UI through its handler and state/data layer to an observable result.
4. Separate initial, loading, content, empty variants, validation failure, operation failure,
   permission, cancellation, retry, recreation, resume, and one-shot event states when applicable.
5. Reconcile Android tests with production source. Tests are evidence, not the only inventory.
6. Map every inventory item into the contract. Put uncertain facts in `unresolved`; do not guess.
7. Define Given/When/Then scenarios with Android evidence for every action and applicable failure,
   boundary, lifecycle, and recovery path.
8. During implementation, map every action to concrete Harmony symbols and run every scenario on
   the target. Record observable results, not only method-level coverage. Reuse Android test inputs
   and expectations without correcting them to suit the target. If tests and source disagree,
   retain both pieces of evidence and resolve the discrepancy before declaring parity; do not
   silently choose a more desirable behavior. Add source-derived characterization cases where
   existing tests are absent.

The optional `scan_android_behavior_symbols.py` helper detects drift in explicitly configured
Kotlin callbacks, commands, and state fields. Its config and mapping are project-specific. It is a
guard against omissions, not a semantic inventory generator.

## Source contract gate

Run before target implementation:

```bash
python3 "$SKILL_ROOT/scripts/validate_behavior_contract_v2.py" \
  --phase source \
  --contract "$BEHAVIOR_CONTRACT" \
  --inventory "$BEHAVIOR_INVENTORY" --snapshot "$SNAPSHOT" \
  --source-scope "$BEHAVIOR_SOURCE_SCOPE" --source-review "$BEHAVIOR_SOURCE_REVIEW" \
  --output "$RUN_ROOT/behavior-contract-source-validation.json"
```

This phase fails when source facts are unmapped, action/scenario declarations disagree, Android
evidence is absent, target action entries are missing, or `unresolved` is non-empty. Target entries
may still be `missing` or `partial` during this phase.
Source-phase success and failure reports use `artifact_type: behavior_source_validation`;
they cannot satisfy the final `behavior_contract` aggregation gate. Do not relabel a source
pass as target evidence.

## Target parity gate

After implementation, create scenario results with this shape:

```json
{
  "schema_version": "behavior-scenario-results.v1",
  "contract_id": "tasks-page",
  "source_revision": "<fixed Android revision>",
  "target_revision": "<current Harmony source digest or revision>",
  "scenarios": [
    {
      "id": "SCN-TASKS-01",
      "verdict": "pass",
      "evidence": [".migration/evidence/tasks-drawer.json"]
    }
  ]
}
```

Each contract scenario also declares the independently reviewed `target_test`, for example
`TasksUiTest.opensDrawer`. Evidence paths must reference actual `evidence_runner.py` records
inside the owned target, with this source-snapshot identity, the current target-source digest,
the scope ID in `slice_ids`, the scenario ID in `demand_ids`, a passed `run` of `ui_tests` or
`device_test`, no skipped cases, and that exact passing test in the captured Hypium report.
Use the existing runner/HDC procedure; do not hand-write signed evidence. A probe, unit test,
human record, nonexistent path or another passing test cannot satisfy this automated parity gate.

Then run:

```bash
python3 "$SKILL_ROOT/scripts/validate_behavior_contract_v2.py" \
  --phase target \
  --contract "$BEHAVIOR_CONTRACT" \
  --inventory "$BEHAVIOR_INVENTORY" --snapshot "$SNAPSHOT" \
  --source-scope "$BEHAVIOR_SOURCE_SCOPE" --source-review "$BEHAVIOR_SOURCE_REVIEW" \
  --target "$TARGET" \
  --scenario-results "$BEHAVIOR_RESULTS" \
  --output "$RUN_ROOT/behavior-contract-validation.json"
```

The target phase fails unless every action is `implemented` with a concrete target symbol and
every scenario has current, scoped, attested execution evidence for its named test. Its output has artifact type
`behavior_contract_validation` (also on target-phase failure); only a passing target result may
be submitted as final evidence. This is the only artifact type accepted by the capability graph's
`behavior_contract` gate. Unit tests remain evidence for `state_transition_tests` and cannot stand
in for source inventory or runtime scenario parity.

## Interpretation

Report three percentages independently:

- source inventory coverage;
- target action implementation coverage;
- target scenario pass coverage.

One page at 100% does not establish whole-app parity. Visual structure and styling remain governed
by `page-snapshot.v2` and screenshot comparison.

`collection_valid` means the original six-family structure/provenance checks pass.
`source_closure.coverage_complete` means all independent source regions have mappings.
`source_complete` additionally requires the current independent semantic review and complete
source contract. `runtime_complete` additionally requires the actual target execution above.
Only an application-scoped runtime pass with no scope exclusions can set `application_complete`.
`scenario_results.reported_passed` is the untrusted submitted count; `passed`/`percent` count only
verified execution. None of these source-only percentages certifies whole-app runtime behavior.
