# Runtime Evidence

## Package And Host

- VSIX identity: `magebyte.spec-superflow-companion@0.15.0` — `PASS`
- VSIX SHA-256:
  `31a3c6f2af20d7238933469e6ca5acef006c6938904ce281f8677f1ec88988ef`
- VS Code 1.123 isolated profile: `PASS`
- Agent Picker discovery: `Spec Superflow` and `Matt Engineering` — `PASS`

## Approved Canaries

| Skill | Invocation | Status | Evidence |
|---|---|---|---|
| `ask-matt` | Explicit | `PASS` | `evidence/runtime/ask-matt-transcript.jsonl` and `ask-matt.png`; the Agent loaded `ask-matt` and selected `prototype` without Spec activity. |
| `diagnosing-bugs` | Automatic | `PASS` | `evidence/runtime/diagnosing-bugs-transcript.jsonl` and `diagnosing-bugs.png`; the Agent loaded the Skill before `node test.mjs`, reproduced `5` versus `6`, and returned three falsifiable hypotheses without editing. |
| Spec Superflow smoke | Explicit Agent selection | `PASS` | `evidence/runtime/spec-superflow-smoke-transcript.jsonl` and `spec-superflow-smoke.png`; the existing router identified `exploring` and performed no CLI or file mutation. |

The machine-readable record is `evidence/runtime/raw-evidence.json`; the
fail-closed checker accepted it with two canaries and 20 pending Skills.

## Compatibility Boundary

All other 20 Matt Skills and duplicate `grill-me` host resolution remain
`PENDING`. Static source, package, or schema tests do not convert them to PASS.

## Environment Restoration

- Isolated profile removal: `PASS`
- Candidate processes: `0`
- Candidate configuration references: `0`
- Real user settings/MCP/CLI snapshot before and after:
  `d209dadc1d5e6014ab4eadb61cf4ffc968dec13e1f5da25a2d78bd530db9067c`
