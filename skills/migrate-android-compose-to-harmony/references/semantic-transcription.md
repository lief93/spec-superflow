# Source-first semantic transcription

Use this policy for normal Android-to-Harmony business implementation. The goal is the same
observable behavior for the same inputs, initial state and relevant environment, not identical
syntax or a redesigned business model. AI reads source directly and uses a lightweight UI/business
dossier as a source index, implementation map and record of actual checks. Neither PSI, a generated
closure nor per-syntax-region census coverage is required for this direct procedure. Existing
structured audit tools remain available separately, with unchanged validation contracts.

Migrate the entire requested page/flow, not only its captured state. Preserve source conditions,
all reachable branches and callback behavior in target code, letting runtime state select what is
shown. Any available closure visibility is capture evidence, not an implementation filter; unparsed visibility
does not require a separate per-branch decision record.

## Execute a complete business chain

For the explicitly requested business-pseudocode deliverable described in `SKILL.md`, use this
same source tracing and reconciliation loop, but transcribe non-runnable business bodies into the
existing dossier instead of wiring every platform implementation. Keep source method identities
and the actual expressions, branches, writes and call order visible. Trace application-owned rules
through repositories/queries as well as UI handlers; abstract only the stated platform mechanism.
Record a chain as existing executable code, pseudocode transcription, or unresolved, and separate
source reconciliation from runtime checks. Do not manufacture test results or target-symbol links
for pseudocode. Source collection remains complete, UI is still implemented and visually checked,
and full executable business acceptance below remains a different delivery claim.

Use this same loop for each requested page or connected flow, regardless of whether its source
uses MVVM, reducers/intents, use cases, or direct callbacks. Follow actual calls and ownership;
the architecture's name does not select a different migration algorithm.

1. **Collect from the UI outward.** Start with every UI/system trigger and displayed state in the
   selected production scope. Follow handlers through state, domain/data logic and the actual
   external effect, then follow the result back to the UI. Include initial loading and host
   callbacks, not only click handlers. Point each chain to its complete source definitions and
   describe it once in the existing dossier/spec. Account for the page's triggers before spending
   the implementation budget on a single chain. Follow the page's actual use of a shared owner;
   a whole navigation graph or DI container is not automatically the migration scope.
   Inspect reached UI components for actions they own internally, including menus, gestures and
   dialogs, as well as callbacks supplied by the parent. Follow each scoped action to its result
   or the agreed host boundary; a link to the containing file is not an inventory of its actions.
2. **Choose the observable checks.** From those definitions, select inputs and outcomes that
   distinguish the source's real branches, defaults, writes and applicable lifetime behavior.
   Existing source tests are the first oracle; add a source characterization case when a material
   behavior is otherwise uncertain. Record unavailable dependencies as concrete gaps in the same
   dossier. Test the page's use of a platform API, not equivalence of the whole platform library.
   Finish the source inventory before using target code as evidence: revisit the production page's
   triggers, state owner, reached data methods and result consumers, including application-owned
   rules inside queries and adapters. Add each reached complete definition to the source scope.
   Run the source coverage check and save its passing baseline. An uncovered source span is work
   to collect, not a reason to narrow the scope. This baseline fixes the chains and acceptance cases
   against which implementation is reconciled.
   The saved baseline protects collected obligations; it does not define away an earlier omission.
   If a scoped source definition contains an unrecorded action or data rule, add it and its checks
   before closing the page. Treat a separate destination as outside scope only at the agreed
   navigation/host boundary, not because its behavior was absent from the first table.
3. **Transcribe one chain through all its layers.** Preserve source class/method/state names and
   module responsibilities where target syntax permits. Reuse corresponding target modules;
   place platform differences at named adapter boundaries. UI callbacks, state changes and the
   repository effect form one implementation slice, rather than a clickable UI with behavior
   deferred to another unspecified task. Map the action to its actual target `file#symbol`.
   At data/platform boundaries carry the source's fields, defaults, identifiers and callback
   arguments through to the consumer. A reduced preview object or successful API call does not
   replace the original write/readback or result-handling semantics.
   Start with one representative source action as a production tracer: wire its real target
   composition, build it, and test the result through the same entry used by the page. Continue
   the remaining chains only after this tracer has a working consumer. This exposes platform and
   composition problems before a page accumulates disconnected controller implementations.
4. **Reconcile code, then verify behavior.** Use the procedure below to follow each source trigger
   through the actual target entry, instantiated dependencies and result consumer. Complete any
   missing bodies or wiring before calling the chain implemented. Then execute the chosen
   source/target cases with the same inputs and relevant initial state. Compare outcomes, writes,
   errors and source-guaranteed order; fix mismatches and retain the failing cases. Related branches
   can share one suite/process. Code inspection establishes implementation coverage; execution
   checks its correctness and platform behavior.
5. **Close the requested scope.** Update the same implementation mappings and scenario results,
   run the applicable build/UI/runtime/visual checks. If structured audit was selected, also run
   its existing target gate without changing its requirements. Continue the
   next incomplete chain within that scope. Completion means the requested chains and their
   applicable scenarios are accounted for, not merely that closure JSON or a scaffold exists.
   Close only after every baseline chain has its real target implementation and passing checks,
   the source-to-target sweep has no outstanding business gap, and required native/visual checks
   are satisfied. For a failed check, repair the owning implementation and rerun; for an omitted
   source rule discovered later, extend the source baseline and tests, then rerun all affected
   chains. Do not delete a chain/test or shrink a source span to turn a failed migration green.

For async work, identify the *source owner* and its actual lifecycle trigger before choosing a
target mechanism. Page disappearance, navigation, ViewModel destruction and process termination
are different events. Compare cancellation, late results or error paths when they belong to this
chain; uncertainty about arbitrary unexercised framework schedules is not a new migration task.
Keep a concrete unverified source behavior visible rather than claiming universal equivalence.
Source facts, target mappings and test results stay in the same dossier/spec and its evidence.
Reuse existing `behavior-contract.v2` entries when already available; do not require conversion
to that schema for direct transcription or create a second checklist/handoff.

## Reconcile coverage and meaning

Keep this in the existing dossier, alongside the UI specification. One row per user/system action
or coherent business chain is sufficient; several rows can share a helper and one test can cover
several rows. Expand a row only when it has different rules or outcomes, not for every syntax node.

| Chain / trigger | Source rule and data effect | Target | Checks and current result |
| --- | --- | --- | --- |
| Save edit | `Editor#save` → `Repository#update`: validation, transformed fields, identity, write before navigation | Target symbols, adapter difference if any | Valid/invalid inputs; persisted fields and navigation result; implemented / verified / blocked / missing details |

Use source references for full definitions instead of copying methods into the table. Capture the
specific fields and conditions that could otherwise disappear at a boundary: for example, an
insert that writes title, author, timestamp and an independently allocated record ID is not
equivalent to storing just a file path. This applies to records, intents, reducer actions, request
payloads and navigation results regardless of the source architecture.

Reconcile in both directions as part of the implementer's normal work:

- **Source to target:** revisit the original page's initial load, controls, conditional states and
  host callbacks. Each reachable scoped trigger should lead through its real target handler,
  state owner and data/platform effect to the result consumer. Compare branch priority, values
  carried across calls and writes, error handling and source-guaranteed effect order. A missing
  handler, discarded field or destination with no implementation remains a concrete gap.
- **Target to source:** trace each target business condition, persistence write and navigation
  argument back to the source definition. Reconcile simplified records, invented defaults,
  success placeholders and platform substitutions against that source, rather than checking only
  that both programs have a similarly named method. Preserve source identities when feasible.

Follow the application composition point as well as method bodies: which concrete implementation
is bound to each reached interface, who invokes the handler, and who consumes its returned state
or effect? Link those symbols in the existing chain row. A test fake can verify a rule but cannot
stand in for a missing production dependency. An effect descriptor is complete only with its
dispatcher; a navigation request needs an existing destination or supplied host integration.
Inspect these connections directly in code before spending time on device setup. Distinguish
**missing implementation**, **implemented but unverified**, and **verified for the stated cases**;
an unavailable emulator affects the second distinction, not whether code exists.

Use this reconciliation to finish missing main chains before spending further time on a single
platform anomaly. If an external service is unavailable, preserve the implemented chain, test its
state/data boundary with a controlled port where useful, and continue the other chains. Record the
real-service check as blocked separately. A missing target feature is an implementation gap, not
an environmental blocker. At an out-of-scope destination, verify the caller's actual arguments and
dispatch through the available boundary; a nonexistent route is not successful navigation, and
full destination migration is not implicitly added to a page-scoped task.

Report the accounted-for chain inventory with implementation and verification results separately.
Use chain counts only against that explicit inventory, not file/test counts or syntax coverage.
They describe scoped coverage, not a percentage guarantee of semantic correctness. Re-run checks
for changed business chains on the current target; retain old results with their original version
instead of carrying an earlier success over an unverified change. Representative native paths
prove platform wiring; source-derived tests can exercise external-condition branches without
requiring every such branch to be reproduced on a device.

## Executable dossier checks

Keep the existing four-column table under `## Business chains` in the page dossier. Use one
unique chain label per row, normal Markdown links to actual code spans, and backticked JUnit
test names in the Checks column. Source links are relative to the safe snapshot; target links
are relative to the Harmony project. For example, `[save](ui/Editor.kt#L40-L65)` identifies the
complete source method. In the Target column use links labeled `entry`, `implementation`,
`binding` and `consumer` to locate the production caller, business body, concrete dependency
composition and result handling. Links may share a span when the roles genuinely coincide.
Before implementation this column may remain `pending`. Reference full definitions instead
of reproducing their code; no per-syntax-node inventory is needed. Keep prose outside backticks
in the Checks column so only actual test names are selected.

Select the production page and its reached source definitions independently of this table using
repeated `--source-file` arguments. A whole-file argument covers its executable text; a shared
file can use `file#Lstart-Lend` for each complete reached definition, leaving unrelated definitions
outside the page scope. Include the actual callees/bindings and data rules traced from the entry,
not only the UI file. The check reconciles this source scope against the table and reports uncovered
code lines without an API support registry, PSI or syntax-node JSON. Imports/comments/brace-only
lines are reading context. All other selected lines need a source link in a chain.

Save the passing source report once as the baseline. Implementation and target checks require it;
chain deletion, changed source rules/anchors, removed test cases or another source snapshot fail
before test execution. A source check cannot overwrite a saved baseline. A genuine scope expansion
uses a new source report, preserves the old one and reruns acceptance against the expanded scope.

Use the same CLI before and after implementation:

```bash
python3 "$SKILL_ROOT/scripts/validate_behavior_contract_v2.py" \
  --dossier "$DOSSIER" --snapshot "$SNAPSHOT" --phase source \
  --source-file "$PAGE_SOURCE" --source-file "$REACHED_DATA_DEFINITION" \
  --output "$SOURCE_BASELINE"

python3 "$SKILL_ROOT/scripts/validate_behavior_contract_v2.py" \
  --dossier "$DOSSIER" --snapshot "$SNAPSHOT" --target "$TARGET" --phase implementation \
  --source-baseline "$SOURCE_BASELINE"

python3 "$SKILL_ROOT/scripts/validate_behavior_contract_v2.py" \
  --dossier "$DOSSIER" --snapshot "$SNAPSHOT" --target "$TARGET" --phase target \
  --source-baseline "$SOURCE_BASELINE" \
  --output "$CHECK_RESULT" -- node --test --test-reporter=junit test/behavior.test.mjs
```

`migrate_compose_page.py` accepts exactly the same `--dossier` arguments and delegates to this
same check; it does not analyze source, generate pages or create a target in this mode. Existing
Contract-based invocations retain their own prerequisites and semantics. Do not run both aliases.

The explicit command after `--` runs once, without a shell, in the target directory. Use the
project's actual tests, emitting JUnit XML to stdout (the Node command above is an example), not
a script printing remembered results. Every declared test must occur by its exact unique `name`
and pass; a nonzero exit, missing/duplicate/skipped case, malformed report or changed referenced
code fails. An optional `--timeout` changes the default 300-second command bound. No commands
are read from the dossier. Source and implementation checks do not execute commands. `--output`
saves the result, command, wall time and captured test output; use a new result path per run.

Tests exercise the real target entry and its business modules, substituting only unavailable
platform mechanisms. Include source-derived assertions for boundary payloads, writes and result
consumption; a build-only command is insufficient. A single case may cover several chains.
For host tests, import the production composition used by the page, not a controller constructed
with replacement application callbacks. Keep storage queries, serializers, routing decisions and
result handling in that composition; replace only the underlying storage/network/system driver.
If native syntax prevents importing that entry on the host, exercise it in the native test runner
instead of duplicating its application logic in a test harness. Isolated controller tests remain
useful additions, but are not the acceptance tests linked for the whole chain.
Keep the source-to-target reconciliation above to validate the selected dependency scope and
meaning of the test assertions. The source span check accounts for the selected code, and the
baseline prevents later denominator shrinkage. Challenge material checks with a changed target
variant as described below: remove a rule, disconnect an effect or drop a payload field and
require the same tests to fail. Passing code references alone cannot prove a body is not a stub.
Include a production-binding negative control: disconnect the actual consumer in a temporary
target copy and rerun the same chain acceptance test. The assertion on the observable outcome
must fail; a syntax/build error or a failing test of a different module is not this evidence.
A source-text assertion that notices the removed call is a wiring check, not an executed
business-outcome control; observe the affected state, stored data or dispatched effect instead.
Restore the production code and rerun before recording success. If the test remains green, move
the test boundary outward to include the real binding rather than adding more dispatch assertions.

`references_valid` and `checks_passed` describe only these bounded checks. This mode never sets
`business_verified` or `runtime_complete`; it does not replace required native/build/visual gates
or turn host tests into whole-page semantic parity. A blocked native run remains separate from
missing code and failed host checks. These are check phases, not new workflow states.

## Implement from source, keep the dossier as an index

Read the complete safe-snapshot callable, its state definitions and reached helpers before writing
the target method. Resolve implementations and callback ownership rather than translating names.
The page's UI/system triggers, displayed state and their actual dependency chains define the
scope. A census or behavior JSON, when available, may help find gaps but is not its authority.
The dossier links source, target and checks. None of these replaces reading source, and
neither a populated JSON nor a scaffold proves that business code has been translated.

Use the reached source definitions as the units of transcription, as with source UI components.
Keep each model, state owner, business method and data operation in its corresponding target owner,
with recognizable names and calls. Work through its original body and callees: translate the
expressions, branches, field updates and effects there rather than reconstructing an algorithm
from the dossier or observed output. Reuse an already translated definition across its callers.
The page and behavioral tests consume these same target modules. A host test substitutes the
platform ports beneath them; it does not maintain a second implementation of the target rules.

The platform boundary is where the platform mechanism begins, not a layer name such as
Repository or DAO. Application-owned queries, transactions, conversions and relationships remain
business code to transcribe; their storage/network driver can change. Preserve which identifiers
and relations subsequent reads use. When a platform requires a different structure, link that
adaptation to the original definition and check the caller-visible result, including its next
consumer. Controlled test ports sit below these rules, just as production platform adapters do.

Reuse existing action IDs and mappings when present; otherwise ordinary source and target
`file#symbol` references in the dossier are sufficient. Tie adapter differences to their chain and
checks. No additional mapping document or per-expression record is needed.
Do not drop reachable code as "garbage" because its purpose is unclear. Prove an exclusion from
the selected scope or leave it unresolved. User-requested improvements are separate changes.

Check only the semantic dimensions used by the scoped source:

| Source behavior | Transcription obligation |
|---|---|
| Ordered branches, early return, defaults and nullable values | Preserve branch priority and exact default/null/empty/error distinctions; do not replace `?:` with truthiness tests. |
| Mutations and external calls | Preserve which write/call happens before normal return or failure, partial state and lack of rollback. No added retries, validation, notifications or deduplication. |
| Data classes, references and collections | Check constructor vs body properties, shallow copy, equality/hash behavior, aliasing, iteration order and duplicate handling. A target spread/deep clone is not automatically Kotlin `copy()`. |
| Numbers, time and serialization | Check integer range/overflow/division, decimal precision and scale, rounding, date units/time zones and missing/null serialization. Do not route money or 64-bit IDs through JS `number` without proven compatibility. |
| Coroutines, flows and lifecycle | Preserve submission vs completion, suspension points, cancellation, error propagation and lifetime. Do not await fire-and-forget work or serialize independent work merely because calls are adjacent. Compare only ordering the source guarantees. |

For example, a Kotlin data-class property declared in the class body is not copied by generated
`copy()`. Buckwheat's `Transaction.uid` therefore resets to its initializer when copying constructor
fields. Preserve that behavior even if retaining the database ID looks more reasonable. Likewise,
a repository removal followed by a state write inside `launch` publishes only after normal return;
publishing before persistence or clearing undo state when the source retains it changes behavior.
These are examples to investigate in source, not assumptions to apply to every transaction class.

## Adapt platforms explicitly

For an unavailable API, bind the source symbol and behavior to the target adapter and document its
inputs, return/errors, effects, timing/lifetime guarantees, known differences and corresponding
tests in the existing ledger/scenarios. API names alone cannot prove equivalence. Do not fake a
Room, Coroutine, LiveData or network implementation and then report the full library as migrated.
If code is unavailable or no permitted equivalent can be demonstrated, keep that boundary
unresolved. Security/privacy constraints still apply; follow
[platform-capabilities.md](platform-capabilities.md). A necessary security change is a disclosed
departure, not an invisible "fix" that passes a parity gate.

## Verify the behavior, including defects

Start with existing Android tests: reuse their inputs, initial state and expected results. When
they are missing, run source-derived characterization cases against the original implementation
in a controlled environment. Reconcile a source/test disagreement explicitly. For the same cases,
compare returned values, resulting state, errors and external effects on Android and Harmony;
compare ordered traces only within the source's ordering guarantees. For concurrent work, examine
the relevant schedules and cancellation boundaries rather than asserting one observed total order.
Use synthetic non-sensitive data and boundary ports only where the real environment is unavailable.

A small host JVM-versus-target-logic comparison is useful early feedback, not device parity.
Prefer compiling the original source files against narrow platform test ports. If only a method
can be isolated, copy its complete span mechanically and retain its source location; keep business
expressions unchanged. Rewriting the source algorithm into a second harness creates a model of the
source, not an executed source oracle. Label such cases as source-derived tests rather than source
execution, and keep literal fixture labels/routes separate from observed calls or stored values.
Apply the same business/platform boundary to the source oracle: execute reached original bodies
and queries, substituting only platform mechanisms. A handwritten replacement for application
rules is a source model; disclose that limit rather than treating agreement with it as parity.
Record the exact original source, unchanged extracted-method spans if used, target/harness hashes,
tool versions, shared inputs, command exits and results. State precisely which adapters are real,
which are controlled ports, and what was not exercised. A decimal carried as opaque text proves
copy/transport for those cases, not decimal arithmetic. A controlled queue proves that tested
schedule, not Android coroutine dispatch or Harmony lifecycle behavior. SDK parsing/bytecode
compilation is not strict ArkTS type checking, a HAP build or device execution.

Protect material semantics with a deliberately changed target variant (for example retaining an ID
the source resets, or publishing before persistence). It must fail the same source/target
comparison. Do not modify the Android baseline or expected output to make the target pass.
Unexercised source paths remain unverified, not silently excluded from the page/flow scope.

When executed tests can emit the same observations, reuse the existing local comparator:

```bash
python3 "$SKILL_ROOT/scripts/compare_behavior_traces.py" \
  --source "$SOURCE_LOG" --target "$TARGET_LOG" \
  --source-prefix 'OBS=' --target-prefix 'OBS=' --expected-records "$EXPECTED_RECORDS"
```

Select observations from the source cases: relevant state, complete boundary payloads/persisted
fields, results and guaranteed effect order. Keep fixture data synthetic and non-sensitive;
normalize only documented platform differences such as sandbox path roots. Determine the expected
record count from the selected cases, not the intersection of available source/target output.
Logs must come from executed tests; matching handwritten observations prove nothing about an
implementation. The comparator detects omitted/changed/reordered observations and preserves value
types. It does not discover omitted source chains or verify that a model's specification is true.
Use the source-to-target reconciliation for that, and keep the real test exits alongside the
comparison. A comparator pass never sets whole-page `business_verified`.

For the optional structured audit path, retain the source and target gates in
[behavior-contract-v2.md](behavior-contract-v2.md). A direct dossier run or host test cannot create
their `runtime_complete` or `application_complete` flags. In either procedure, record actual native
build/device results and untested behavior honestly. Report tested semantic scope separately from
full application completeness.

## Current completion summary

Keep one current conclusion in the existing dossier, with earlier runs linked as history. Report
source-scope reconciliation, implementation gaps, executed behavior checks and required native/UI
checks separately. Name the current step and next concrete action; a count of passing tests or
an old pending paragraph does not communicate page completion. Record approved platform differences
with their affected behavior, and keep unavailable external-service checks distinct from missing
code. The current conclusion follows the requested source scope, not just the rows that happened
to pass the CLI.
