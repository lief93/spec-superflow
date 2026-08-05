# Change Proposal

## Why

- The offline VSIX currently exposes only Spec Superflow, so users cannot
  install the separately authored Matt engineering workflow from the same
  transferable package.
- A single deterministic artifact is needed for an environment that cannot
  download Plugin content, while provenance, licensing, workflow isolation,
  and host-compatibility claims remain independently auditable.

## What Changes

- Extend the companion VSIX manifest from one `chatPlugins` root to two:
  existing `./agent-plugin` and new independent `./matt-plugin`.
- Assemble a `Matt Engineering` Plugin from exactly the 22 Skill paths in the
  pinned upstream `.claude-plugin/plugin.json`, retaining original names,
  Skill files, referenced sibling resources, MIT license, and provenance.
- Provide a usable Matt Agent/router and require real VS Code Copilot evidence
  for one user-invoked and one model-invoked Matt Skill, while leaving
  subagent-heavy and duplicate-name host semantics honestly `PENDING`.
- Add offline and reproducibility gates for the dual-Plugin staged payload and
  final VSIX, while preserving all existing Spec Plugin behavior and package
  contents.
- Add a maintainer-only pinned synchronization path that is separate from
  normal build/install, derives a proposed inventory from the requested
  commit's official manifest, makes count/name changes explicit, and fails
  safely on identity, content, or local adaptation conflicts.
- Record VS Code Copilot compatibility honestly: source preservation and
  structural validation do not promote unexecuted runtime workflows from
  `PENDING` to passed.

## Capabilities

### New Capabilities

- `matt-engineering-copilot-plugin` — package and expose the fixed upstream
  Matt Skill set as an independent, auditable, offline VS Code Agent Plugin
  beside Spec Superflow.

### Modified Capabilities

- None. Existing Spec Superflow behavior is a preservation constraint, not a
  behavioral redesign.

## Scope

### In Scope

- One VSIX with `./agent-plugin` and `./matt-plugin` declared as separate
  `chatPlugins`, discoverable as `Spec Superflow` and `Matt Engineering`.
- Exact vendoring of the 22 paths selected by upstream commit
  `2ab958093e83e0ec752e6c1c5932da465bf23e0c`, including required sibling
  resources, MIT license, and machine-checkable provenance.
- Offline deterministic staging, packaging, and installation checks.
- Safe maintainer synchronization that may fetch only when explicitly run and
  never silently overwrites local adaptations; the current package stays fixed
  at 22 Skills while a future requested manifest may propose a different
  inventory for review.
- A usable Matt Agent/router with real Copilot evidence for `ask-matt` and
  `diagnosing-bugs`, plus isolation checks and compatibility/evidence status
  for host-specific fields, subagent instructions, and representative complex
  Skills.

### Out of Scope

- Renaming Skills with `matt-` prefixes or resolving cross-Plugin name
  conflicts. Duplicate-name host resolution, including `grill-me`, remains
  `PENDING` and is not an isolation acceptance claim.
- Importing upstream in-progress, deprecated, personal, misc, or other
  non-manifest content.
- Changing Spec `/workflow-init`, CLI bootstrap, Agent/Skill routing, Language
  Model Tools, Example MCP, or packaged CLI behavior.
- Treating structural tests as real VS Code Copilot runtime evidence.
- Network-dependent build/install, publication, release, internal-network
  validation, or remote-computer work.

## Impact

- Affected code areas: companion extension manifest, VSIX assembly and package
  verification, a new `matt-plugin` source/assembly area, pinned sync tooling,
  compatibility documentation, provenance/license files, and focused tests.
- Affected APIs or interfaces: `contributes.chatPlugins` gains the independent
  `./matt-plugin` entry; existing Language Model Tool names and behavior remain
  unchanged.
- External systems or dependencies involved: source content is attributed to
  `https://github.com/mattpocock/skills` at exact commit
  `2ab958093e83e0ec752e6c1c5932da465bf23e0c` under MIT. Only the explicit
  maintainer sync path may contact that upstream; build and installation do
  not.
