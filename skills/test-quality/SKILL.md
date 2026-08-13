---
name: test-quality
description: Design or implement tests that completely and honestly prove acceptance criteria. Use while authoring tasks.md test plans and before writing or changing tests during implementation.
---

# Test Quality

Turn each acceptance criterion into the smallest reliable set of tests that
would fail for every meaningful violation of that criterion.

This Skill does not own workflow state, approval, review, or TDD sequencing.
Do not invoke another Agent. Do not create another planning artifact. Keep its working
coverage ledger in the current context; write results only into the existing
`tasks.md` test rows or test source.

## Inputs

Read the exact Requirement and Scenario, relevant Design decision, real
production seam, existing test files, test configuration, and repository
commands. Do not design from the Scenario title alone.

If a Requirement, Scenario, or Design section is malformed or has a parse
failure, stop and name the exact section. If a referenced test file, harness,
or configuration is missing, do not invent it; record the narrow gap in the
existing plan as a missing file and identify the minimum seam or developer
decision required.

## Search Budget

Inspect in order: named production seam, nearest tests and fakes, module test
configuration, then all implementations and every test double affected by a
changed interface. Use targeted symbol and path searches; compile affected modules.
Stop researching when repository evidence supports the harness, command, and
assertion mechanism. Record any remaining narrow uncertainty. Do not decompile
binaries or inspect unrelated modules, local caches, or framework internals.

## Clause Ledger

Before choosing tests, split every Scenario into observable clauses:

- **Precondition**: state and data required before the WHEN.
- **Action or event**: the exact WHEN, including who triggers it.
- **Intermediate outcome**: progress, retained content, ordering, or in-flight
  behavior that must be observable before completion.
- **Terminal outcome**: every THEN and AND after success or failure.
- **Negative outcome**: old or stale value absent, forbidden call not made,
  dialog not shown, navigation not intercepted, or duplicate request blocked.
- **Invariant**: content, identity, persistence, selection, or ownership that
  must remain unchanged.

Map every WHEN, THEN, and AND clause to at least one concrete setup, action,
and assertion. Multiple clauses may share one case when that case can observe
them honestly. Do not create one test mechanically per sentence.

## Alternative Paths

Inspect user intent, the Spec, and existing code for alternative entry paths
that reach the same business state or enforce the same rule: direct action,
restored state, retry, lifecycle event, navigation entry, or equivalent mode.
Cover a path only when approved behavior or repository evidence establishes it
and it could bypass the primary proof. Do not invent product behavior for test
completeness; report a required but unspecified path as a planning defect.

An edge case or boundary value changes data on one path. An alternative path
changes the entry or trigger. A failure path changes the expected outcome.

## Choose Proof

Use the lowest stable layer that can observe the risk:

- Pure mapping, state transition, ordering, call count, concurrency, and
  filtering: Unit or Component.
- Serialization, persistence, repository delegation, module wiring, and real
  boundary behavior: Integration or the repository's equivalent.
- Visible content, accessibility semantics, interaction, navigation, focus,
  and error recovery: UI.
- A user-triggered WHEN operates the real rendered control. Calling its
  callback directly may prove wiring, but cannot alone prove the visible AC.
- A lifecycle, external, or system event may use a real injectable seam, but
  the test must still assert the resulting visible behavior when the AC is
  user-visible.

Add a layer only for a distinct acceptance risk. Code coverage percentage is
supporting data, not acceptance-criterion coverage.

Keep each fixture within that production layer's responsibility. A
presentational or rendering layer that receives already-derived or filtered
state cannot prove the upstream derivation by receiving unfiltered input and
expecting the view to transform it. Prove user input dispatch through the real
rendered control, prove derivation in its state owner, and prove the resulting
rendered state separately. Combine them only when the real harness can inject
and observe the full production path. A presentational test must not filter its
own fixture when the production state owner owns filtering. Use the real state
owner or full production integration; otherwise record the missing integration
seam and limit the UI test to rendered control dispatch or an already-derived result.

## Prove The Harness

For every planned or implemented case, verify:

1. The precondition is controllable in the real harness.
2. The action reaches the production seam named by the Design.
3. Each claimed result is observed by an explicit assertion.
4. The repository command can select the exact case or reports it by name.
5. Removing or breaking one claimed behavior would make the case fail.

If step 5 is false, strengthen or remove the claim. If the state cannot be
controlled, plan the smallest architecture-consistent rendering or injection
seam. Do not use an inert or no-op fake, an inaccessible state, a test-only
production route, or a duplicate business implementation in the test. If mutually
exclusive designs imply different seams, record the developer decision gap and
each option's test obligation; select neither for the plan until Design decides.

## Reusable Risk Patterns
Apply only patterns relevant to the AC:

- **State transition**: assert before, intermediate, and terminal states. For
  replacement, assert the new value appears and the old or stale value is
  absent.
- **Success and failure**: control both; assert retained data, progress removal,
  retry/error affordance, and recovery where required.
- **Empty and boundary values**: use explicit zero/empty, one, many, limit,
  and invalid fixtures when behavior differs. One item disappearing does not
  prove an empty result.
- **Persistence**: write through the public owner, then recreate the owner and
  storage engine over the same file or bytes. The same in-memory object or fake
  does not prove process recreation; use real storage for that stronger claim.
- **Concurrency**: hold the first operation at a barrier, deferred, or
  controllable scheduler; trigger a competing action through the same state owner
  or same production entry while it is in flight and verify it reaches the
  production seam; then assert calls and outcomes before releasing the barrier.
  A control disappearing or being absent does not prove deduplication. If the
  harness cannot trigger the competing action through a production entry, record
  a planning gap; do not weaken, rephrase, or replace the acceptance criterion
  with "no spontaneous second call."
- **Collections and lazy UI**: do not infer all items from composed nodes. Use
  existing visible text, accessibility semantics, count metadata, or scrolling
  to assert representative unchanged content. Do not add test tags or semantics
  solely to prove unchanged collection content; add them only when item identity
  or location is itself an acceptance outcome.
- **Navigation and lifecycle variants**: arrange and assert every named state,
  not one representative state when the AC explicitly lists several.
- **Accessibility**: when visible text and accessibility semantics are both
  outcomes, assert both and assert stale semantics are gone after updates.

Avoid fixed sleeps. Await a deterministic state, event, idling signal, virtual
time advance, or framework synchronization point.

## False Proofs

Reject these as the sole proof of a behavioral AC:

- compile or build success;
- no crash or screen launch only;
- Markdown, documentation, file existence, or source-text checks;
- aggregate test count without the exact case result;
- callback count when the AC also requires a rendered state transition;
- a child composable parameter when the AC requires application-state
  derivation;
- a fake that returns one fixed value but cannot drive the claimed branch;
- screenshot replacement without behavioral assertions.

## Planning Use

For each `tasks.md > TDD Test Plan` row:

- Name the exact layer, platform, test file, and case.
- In `Proves`, state the fixture/precondition, action, and observable assertions
  concisely; include intermediate, negative, and invariant outcomes when the
  AC requires them.
- Use `Update` only when the real existing case can own the added assertions;
  otherwise use a distinct `Add`. Use `Run existing` only for unchanged
  behavior already asserted by that exact case.
- Derive every module-scoped exact command from repository evidence; do not
  invent a task or flag. Verify every command before recording it through task
  discovery or dry-run; JVM and instrumentation use different selection syntax.
  If task discovery and dry-run cannot run because the toolchain or environment
  is unavailable, do not record an exact command. Label the syntax as a candidate
  command and mark command verification blocked until it runs successfully.

Before freezing Tasks, run the mutation question for every clause: “If an
implementation omitted or reversed this clause, which exact test would fail?”
Any clause without an answer is a planning defect.

Then run an **aggregate AC coverage** check after every AC has its rows. Walk
the end-to-end user journey across Requirements and Scenarios: find any
uncovered trigger, result, connection between ACs, evidenced alternative path,
failure/recovery, or invariant. Treat an empty Requirement or journey row as a
coverage gap. Reject duplicate proof where the same test is claimed by multiple
ACs, and reject rows that prove only compile/build success. Repair the smallest
existing test set; do not add one test mechanically per AC or layer.

Apply these completion gates before returning:

- For a changed interface, record the exact search symbol and all matched paths;
  reconcile every match with File Changes, naming every concrete implementation
  and every test double, then include an affected-module compile or test command.
- For a visible transition, one harness observes before and after rendered states
  from the action. Do not reuse a static test from a different Scenario. A
  stateful host must not duplicate business logic; exercise the real
  state owner or production integration seam. Each user-visible Scenario has its own UI row.
- For process-recreation persistence, use a file-backed test or recreate a new
  storage engine from bytes. Neither a serializer round trip nor owner
  re-instantiation alone proves application restart restoration.

## Implementation Use

Before production code, implement the named tests from the approved plan.
Check the actual setup, action, and assertions against the clause ledger.
New behavior must produce the workflow's real RED; characterization uses its
honest baseline PASS. A failure caused only by compilation, environment, or a
broken fixture is not behavioral RED. Hand control back to `build-executor`
after tests express the approved behavior; that Skill owns GREEN and the rest
of execution.
