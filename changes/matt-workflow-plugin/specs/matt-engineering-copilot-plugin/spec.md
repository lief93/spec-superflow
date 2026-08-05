# Matt Engineering Copilot Plugin Specification

## ADDED Requirements

### Requirement: One offline VSIX exposes two independent Agent Plugins

The companion VSIX SHALL declare the existing `./agent-plugin` and the new
`./matt-plugin` as separate `contributes.chatPlugins` roots. A single VSIX
installation SHALL expose distinguishable `Spec Superflow` and
`Matt Engineering` entries without requiring a content download.

#### Scenario: User installs the complete VSIX offline

- **WHEN** the user installs the locally built VSIX on a supported VS Code host with network access unavailable
- **THEN** installation SHALL complete without a registry, URL, or other content fetch
- **AND** Agent Picker SHALL expose separate `Spec Superflow` and `Matt Engineering` entries backed by different Plugin roots
- **AND** the installed extension SHALL not declare a third Agent Plugin root

### Requirement: Existing Spec Superflow behavior remains intact

Adding the Matt Plugin SHALL preserve the existing Spec Plugin assembly and its
`/workflow-init`, CLI bootstrap, Language Model Tools, Example MCP, Skills,
commands, Agents, and packaged CLI behavior. Spec SHALL NOT automatically
invoke or initialize the Matt workflow.

#### Scenario: User selects Spec Superflow from the dual-Plugin VSIX

- **WHEN** the user runs an existing Spec setup, workflow, or Example MCP path through `Spec Superflow`
- **THEN** the same Spec-owned entry, tool names, Plugin-root resources, CLI source restrictions, and workflow behavior SHALL remain available
- **AND** no Matt Skill or Matt-owned state SHALL be invoked or created unless the user separately selects `Matt Engineering`

### Requirement: Matt Plugin content matches the pinned official manifest

The Matt Plugin SHALL be sourced from
`mattpocock/skills@2ab958093e83e0ec752e6c1c5932da465bf23e0c` and SHALL include
exactly the 22 Skill paths selected by that commit's
`.claude-plugin/plugin.json`: `ask-matt`, `diagnosing-bugs`,
`grill-with-docs`, `triage`, `improve-codebase-architecture`,
`setup-matt-pocock-skills`, `tdd`, `to-spec`, `to-tickets`, `wayfinder`,
`implement`, `prototype`, `research`, `domain-modeling`, `codebase-design`,
`code-review`, `resolving-merge-conflicts`, `grill-me`, `grilling`, `handoff`,
`teach`, and `writing-great-skills`.

#### Scenario: Maintainer verifies the vendored Skill inventory

- **WHEN** package verification compares `matt-plugin` with the pinned official manifest
- **THEN** all 22 selected Skill directories SHALL exist under their original unprefixed names with their original `SKILL.md`
- **AND** each selected directory's referenced sibling files SHALL be present
- **AND** no Skill from upstream `skills/in-progress`, `skills/deprecated`, `skills/personal`, `skills/misc`, or any other unselected path SHALL be included

### Requirement: Matt Engineering provides a usable Agent and Skill router

The `Matt Engineering` entry SHALL load the Matt Plugin as an actionable
Agent/router without introducing a Spec state machine or depending on `ssf`.
The current release SHALL prove both an unprefixed user-invoked Skill and an
unprefixed model-invoked Skill in a real supported VS Code Copilot runtime.

#### Scenario: User explicitly invokes Ask Matt

- **WHEN** the user selects `Matt Engineering` and explicitly invokes the user-invoked `ask-matt` Skill
- **THEN** VS Code Copilot SHALL load and follow the packaged `ask-matt` router instructions and return Matt workflow guidance
- **AND** the interaction SHALL not invoke a Spec Skill, `ssf`, `/workflow-init`, or create a Spec `changes/` directory

#### Scenario: User reports a bug through Matt Engineering

- **WHEN** the user selects `Matt Engineering` and describes a bug that matches the model-invoked `diagnosing-bugs` Skill
- **THEN** VS Code Copilot SHALL load and follow the packaged `diagnosing-bugs` feedback-loop guidance without requiring explicit Skill selection
- **AND** the interaction SHALL not invoke a Spec Skill, `ssf`, `/workflow-init`, or create a Spec `changes/` directory
- **AND** evidence for both Matt scenarios SHALL identify the VSIX digest, VS Code version, selected Agent, invoked Skill, and observable response

### Requirement: Vendored content has auditable license and provenance

The packaged Matt Plugin SHALL retain the upstream MIT license and SHALL carry
machine-checkable provenance identifying the upstream repository, exact commit,
upstream plugin version `1.2.0`, source manifest path, selected Skill paths, and
vendored content digests.

#### Scenario: Reviewer audits a built package without network access

- **WHEN** a reviewer inspects the staged or installed Matt Plugin using only packaged files
- **THEN** the reviewer SHALL be able to verify the MIT attribution and exact upstream identity
- **AND** the recorded selected paths and digests SHALL match the packaged Skill files and required resources
- **AND** missing, extra, or changed vendored content SHALL make package verification fail nonzero

### Requirement: Normal build and installation are offline and deterministic

The standard VSIX assembly, verification, and installation paths SHALL consume
only repository-owned files and local toolchain executables. For a fixed source
tree and supported toolchain, repeated builds SHALL produce the same staged
file inventory, per-file content digests, and VSIX bytes.

#### Scenario: Maintainer repeats the build with network unavailable

- **WHEN** the same clean source commit is built twice while public network access is unavailable
- **THEN** both builds SHALL succeed without invoking an upstream clone, registry, URL, package download, or update command
- **AND** both staged payload manifests and per-file digests SHALL be identical
- **AND** both final VSIX SHA-256 digests SHALL be identical

### Requirement: Upstream synchronization is explicit and fails safely

Any upstream synchronization capability SHALL be maintainer-only, separately
invoked, and pinned to an explicit upstream commit. The current package SHALL
remain fixed to its approved 22-Skill inventory. A future synchronization SHALL
derive its proposed inventory from the requested commit's official manifest,
validate license, selected content, and destination safety, and expose every
name/count change for review rather than silently overwrite a local adaptation.
Normal build and installation SHALL NOT invoke it.

#### Scenario: Maintainer proposes an acceptable pinned revision

- **WHEN** the maintainer explicitly requests synchronization for a resolvable commit whose official manifest, license, and every manifest-selected path pass validation
- **THEN** synchronization SHALL prepare the manifest-selected content and updated provenance as a reviewable repository diff
- **AND** additions, removals, renamed paths, and the previous and proposed Skill counts SHALL be reported explicitly, including when the proposed count is not 22
- **AND** no unselected upstream directory SHALL be imported
- **AND** later normal builds SHALL use only that vendored result

#### Scenario: Synchronization encounters unsafe or conflicting input

- **WHEN** the commit, manifest, license, selected path, digest expectation, destination boundary, or local adaptation safety check fails
- **THEN** synchronization SHALL exit nonzero
- **AND** it SHALL leave the previously vendored Plugin complete and usable without a partial replacement or silent overwrite

### Requirement: Host compatibility claims remain evidence-based

The Matt Plugin SHALL preserve upstream Claude/Codex-specific metadata and
subagent-oriented instructions needed for provenance while documenting which
semantics VS Code Copilot supports, adapts, or does not execute. Cross-Plugin
resolution for duplicate Skill names, including `grill-me`, SHALL remain
`PENDING` and outside isolation acceptance rather than be hidden by automatic
renaming. Structural, schema, and protocol checks SHALL NOT be reported as real
Copilot workflow passes.

#### Scenario: Packaged Skill uses host-specific or subagent semantics

- **WHEN** compatibility verification encounters a host-specific field or a workflow such as `code-review`, `research`, or `wayfinder` that depends on subagent behavior
- **THEN** the compatibility record SHALL identify the original construct and any explicit Copilot adaptation or unsupported behavior
- **AND** the original vendored source and provenance SHALL remain auditable
- **AND** each workflow lacking real VS Code Copilot runtime evidence SHALL remain `PENDING` rather than `PASS`

#### Scenario: Installed Plugins contain the same Skill name

- **WHEN** package or host verification finds an unprefixed Skill name such as `grill-me` in both installed Plugin roots
- **THEN** the compatibility record SHALL keep cross-Plugin host resolution `PENDING`
- **AND** verification SHALL not claim selected-Agent Skill exclusivity, automatically rename either Skill, or use root separation alone as runtime proof

#### Scenario: Real Copilot runtime evidence is recorded

- **WHEN** an identified Matt workflow is actually exercised through the packaged Plugin in a supported VS Code Copilot runtime
- **THEN** its status MAY move from `PENDING` only with evidence that names the package identity, host version, invoked entry, observable result, and any remaining limitation
- **AND** that evidence SHALL not imply that unexecuted Matt workflows also passed
