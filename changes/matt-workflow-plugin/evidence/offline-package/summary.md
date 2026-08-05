# Offline Package Evidence

## Candidate

- Captured: `2026-08-05`
- VS Code: `1.123.0` (`6a44c352bd24569c417e530095901b649960f9f8`)
- Extension: `magebyte.spec-superflow-companion@0.15.0`
- Matt commit: `2ab958093e83e0ec752e6c1c5932da465bf23e0c`
- Temporary acceptance root:
  `/tmp/spec-superflow-matt-workflow-plugin-final-20260805-ZvM56n`

## Forced-Offline Procedure

Each of two runs used a different empty npm cache with:

```text
npm_config_offline=true
npm_config_registry=http://127.0.0.1:9/unreachable
```

For each run:

```text
node scripts/build-vscode-vsix.mjs --stage-only <stage>
node scripts/build-vscode-vsix.mjs <output.vsix>
```

All four commands exited `0`. The two sorted stage manifests were byte-for-byte
identical (`diff` exit `0`).

## Result

- Stage files: `256`
- VSIX entries: `256`
- Symlinks: `0`
- Plugin roots: exactly `extension/agent-plugin/plugin.json` and
  `extension/matt-plugin/plugin.json`
- Run 1 VSIX SHA-256:
  `31a3c6f2af20d7238933469e6ca5acef006c6938904ce281f8677f1ec88988ef`
- Run 2 VSIX SHA-256:
  `31a3c6f2af20d7238933469e6ca5acef006c6938904ce281f8677f1ec88988ef`
- Stage manifest SHA-256:
  `db25deca4f314b8ef99df42d50161cb5516e8c31bb9bb59cc4dd46517f869788`
- VSIX file-list SHA-256:
  `36be4bd3a74eab9260d3718bfc9bffbb4ea016be47cb1ed8d14d54c38c4549dc`

The full generated lists are `stage-files.sha256` and `vsix-files.txt` in this
directory. The accepted VSIX path is `<acceptance-root>/one.vsix`.

## Isolated Installation

The accepted VSIX installed with exit `0` into isolated `profile/` and
`extensions/` directories. `code --list-extensions --show-versions` returned:

```text
magebyte.spec-superflow-companion@0.15.0
```

No user-profile extension or setting was changed. Real Agent Picker and Chat
results are recorded separately in `runtime-evidence.md`.
