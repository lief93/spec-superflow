# User Intent

The Android-to-Harmony migration workflow must plan and execute a complete
Harmony version of an Android application: all business flows, observable
behaviors, and supported platform capabilities remain in scope, with high UI
fidelity. A successful build or complete source-file accounting is not a
successful migration by itself.

This change focuses only on the planning seam between the existing capability
graph and migration execution. It must produce executable vertical-slice work
rooted in real application routes or pages. A slice must follow resolved
navigation, declaration, import, and call relationships into its state,
business, repository, network, storage, platform, UI-system, control, and test
obligations. It must not create one task per source file or Composable, use
filename-token similarity as authoritative ownership, or place unmatched work
in the first available slice.

The Spec Workflow remains the single user entry. Internal planner utilities are
maintainer/debug implementation details. The workflow must fail closed for
ambiguous ownership, stale or tampered inputs, invalid dependencies, and
incomplete evidence. Review-queue ambiguity blocks only affected slices when a
real relationship identifies that scope.

Constraints:

- Do not use AI image or screenshot recognition.
- Preserve unrelated worktree changes.
- Do not commit or push during this change unless the user later requests it.
- Validate with fixed public Jetpack Compose projects; never use private or
  internal source code or data.
- Use Spec Workflow planning, contract, execution, test, review, and evidence
  stages instead of an external everyday-development review gate.
