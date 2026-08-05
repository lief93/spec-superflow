# User Intent: One Offline VSIX With Independent Spec and Matt Plugins

## Problem

The current VSIX installs only the Spec Superflow Agent Plugin. The user wants
one offline-installable VSIX that also exposes Matt Pocock's published
engineering Skills as a separate Agent Plugin, without merging the two
workflows, changing Spec Superflow behavior, or requiring an internal-network
machine to fetch anything during build or installation.

## Confirmed Scope

- Keep the existing assembled Spec Plugin at `./agent-plugin` and add a
  separate Matt Plugin at `./matt-plugin` in the same VSIX.
- Declare both roots through
  `extensions/spec-superflow-companion/package.json > contributes.chatPlugins`
  so VS Code Agent Picker can discover `Spec Superflow` and `Matt Engineering`
  as separate entries after one VSIX installation.
- Make `Matt Engineering` a usable Agent/router rather than an inventory-only
  entry. Real VS Code Copilot evidence must show the selected Matt entry loading
  and following at least one unprefixed user-invoked Skill (`ask-matt`) and one
  model-invoked Skill (`diagnosing-bugs`) without invoking Spec or `ssf`.
- Preserve the Spec Plugin's current `/workflow-init`, CLI bootstrap,
  Language Model Tools, Example MCP, Skills, commands, Agents, and packaged CLI
  behavior. Spec does not automatically invoke Matt, and Matt does not invoke
  `ssf` or use Spec's `changes/` workflow.
- Vendor the exact 22 paths listed by
  `mattpocock/skills@2ab958093e83e0ec752e6c1c5932da465bf23e0c` in
  `.claude-plugin/plugin.json`: `ask-matt`, `diagnosing-bugs`,
  `grill-with-docs`, `triage`, `improve-codebase-architecture`,
  `setup-matt-pocock-skills`, `tdd`, `to-spec`, `to-tickets`, `wayfinder`,
  `implement`, `prototype`, `research`, `domain-modeling`,
  `codebase-design`, `code-review`, `resolving-merge-conflicts`, `grill-me`,
  `grilling`, `handoff`, `teach`, and `writing-great-skills`.
- Keep each published Skill name unchanged, with no `matt-` prefix. Preserve
  its `SKILL.md` and all sibling resources it references, together with the
  upstream MIT license and auditable repository, commit, version, and manifest
  provenance.
- Exclude upstream `skills/in-progress`, `skills/deprecated`,
  `skills/personal`, `skills/misc`, and every other path not selected by the
  fixed official manifest.
- Make normal VSIX build and installation offline and deterministic. A separate
  maintainer-only synchronization command may access the network, but it is not
  part of build or install. The current vendored input remains the fixed
  22-Skill commit; a future explicit sync derives its proposed inventory from
  that requested commit's official manifest, reports additions and removals,
  and must fail safely rather than silently overwrite local adaptations.
- Preserve upstream Claude/Codex-specific fields and subagent-oriented text as
  source material while documenting their actual VS Code Copilot support. A
  structural or protocol test is not evidence of a real Copilot runtime pass;
  unexecuted runtime cases, including `code-review`, `research`, and
  `wayfinder`, remain `PENDING`.

## Non-goals

- No second VSIX, online marketplace dependency, registry download, or network
  fetch during build or installation.
- No merge of Matt Skills into the Spec Plugin root, no cross-workflow routing,
  and no shared workflow state.
- No renaming of upstream Skills and no resolution of possible duplicate Skill
  names between installed Plugins in this change. Host resolution for an
  existing duplicate such as `grill-me` remains explicitly `PENDING` and is not
  used to claim or reject this change's Plugin-root isolation.
- No vendoring of unlisted upstream directories or repository-wide upstream
  content merely because it exists at the pinned commit.
- No claim that unsupported host semantics have been translated or that an
  unexecuted VS Code Copilot workflow has passed.
- No tag, release, npm publication, marketplace publication, remote-computer
  access, or company-internal-network validation in this change.

## Success Criteria

1. One built VSIX exposes exactly the Spec and Matt Plugin roots, and VS Code
   Agent Picker can distinguish `Spec Superflow` from `Matt Engineering`.
2. Real VS Code Copilot validation through `Matt Engineering` loads and follows
   `ask-matt` as a user-invoked Skill and `diagnosing-bugs` as a model-invoked
   Skill without invoking Spec, `ssf`, or a Spec Change.
3. The Spec Plugin keeps its existing assembled payload and user-visible
   bootstrap, workflow, CLI, and Example MCP behavior.
4. The Matt Plugin contains exactly the 22 fixed-manifest Skills under their
   original names, with every required sibling resource present and excluded
   upstream categories absent.
5. License and provenance data identify the MIT license, upstream repository,
   exact commit, upstream plugin version, manifest path, and selected paths.
6. Building and installing from a complete local checkout performs no network
   access and produces a reproducible staged payload and VSIX for fixed inputs.
7. A maintainer sync derives the proposed inventory from the requested commit's
   official manifest and explicitly reports any count/name changes, while
   mismatch, missing content, or local adaptation conflicts fail nonzero
   without a partial or silent overwrite.
8. Matt and Spec keep separate Plugin roots, Agent entries, routing ownership,
   and state conventions; Matt does not depend on `ssf` or `changes/`, while
   cross-Plugin duplicate-name resolution remains `PENDING`.
9. Compatibility records distinguish source preservation, structural checks,
   and real Copilot runtime evidence; anything not actually exercised stays
   `PENDING`.
