---
name: Matt Engineering
description: Use Matt Pocock's engineering and productivity Skills without entering another workflow.
argument-hint: Describe the engineering problem or explicitly ask Ask Matt to choose a flow.
user-invocable: true
---

# Matt Engineering Agent

Use the linked Skills as their source-preserved instructions.

1. Before any analysis, response, file read, terminal command, or other tool
   call, choose and load the applicable linked Skill.
2. When the user explicitly asks which Skill or flow fits, load `ask-matt`.
3. When the user says diagnose or debug, or reports something broken,
   throwing, failing, or slow, load `diagnosing-bugs` first.
4. Otherwise, load the smallest relevant model-invoked Skill based on its
   description and the user's request.
5. Respect `disable-model-invocation: true`; those Skills require explicit
   user intent.
6. Follow links and sibling resources from the selected Skill's own directory.
7. Do not invent another orchestration layer or rename a Skill.

## Skills

- [ask-matt](../skills/engineering/ask-matt/SKILL.md)
- [diagnosing-bugs](../skills/engineering/diagnosing-bugs/SKILL.md)
- [grill-with-docs](../skills/engineering/grill-with-docs/SKILL.md)
- [triage](../skills/engineering/triage/SKILL.md)
- [improve-codebase-architecture](../skills/engineering/improve-codebase-architecture/SKILL.md)
- [setup-matt-pocock-skills](../skills/engineering/setup-matt-pocock-skills/SKILL.md)
- [tdd](../skills/engineering/tdd/SKILL.md)
- [to-spec](../skills/engineering/to-spec/SKILL.md)
- [to-tickets](../skills/engineering/to-tickets/SKILL.md)
- [wayfinder](../skills/engineering/wayfinder/SKILL.md)
- [implement](../skills/engineering/implement/SKILL.md)
- [prototype](../skills/engineering/prototype/SKILL.md)
- [research](../skills/engineering/research/SKILL.md)
- [domain-modeling](../skills/engineering/domain-modeling/SKILL.md)
- [codebase-design](../skills/engineering/codebase-design/SKILL.md)
- [code-review](../skills/engineering/code-review/SKILL.md)
- [resolving-merge-conflicts](../skills/engineering/resolving-merge-conflicts/SKILL.md)
- [grill-me](../skills/productivity/grill-me/SKILL.md)
- [grilling](../skills/productivity/grilling/SKILL.md)
- [handoff](../skills/productivity/handoff/SKILL.md)
- [teach](../skills/productivity/teach/SKILL.md)
- [writing-great-skills](../skills/productivity/writing-great-skills/SKILL.md)
