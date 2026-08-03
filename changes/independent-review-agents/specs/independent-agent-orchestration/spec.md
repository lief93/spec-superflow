## MODIFIED Requirements

### Requirement: Full workflow uses one Primary and one fixed independent Reviewer

For exact `workflow: full`, the Plugin SHALL expose one user-visible Primary
that owns planning, implementation, verification, and finding repair, plus one
hidden read-only Reviewer. Each stage's initial review SHALL start in a fresh
independent context, and only that context MAY be resumed for the stage's one
permitted re-review. The workflow SHALL NOT add a Dev role, extra workflow
state, or host continuity protocol.

#### Scenario: Primary requests an independent semantic review

- **WHEN** a full-workflow review checkpoint is reached
- **THEN** Primary SHALL invoke the fixed Reviewer in a fresh stage-scoped independent context
- **AND** Reviewer SHALL receive only the exact Change directory and review stage; the host SHALL remove any Primary-authored schema, summary, candidate, path index, evidence index, or copied body before execution
- **AND** Reviewer SHALL run the read-only `review candidate` command and use ordinary project-read and terminal tools to discover the current artifacts, repository evidence, and final SCM view itself
- **AND** Reviewer SHALL return to Primary without modifying files or Git state, running tests or any other workflow command, changing state, contacting the user, calling MCP, or invoking another Agent
- **AND** after every Reviewer return Primary SHALL write the raw JSON unchanged, run `review record`, and then run `review check` before interpreting the verdict or editing
- **AND** after one repair Primary SHALL resume the same stage-scoped Reviewer context, while a second `Request Changes` SHALL fail closed without a third review

#### Scenario: Non-full workflow continues

- **WHEN** persisted workflow is `hotfix` or `tweak`
- **THEN** the existing fast path SHALL continue without creating or checking independent Review artifacts
