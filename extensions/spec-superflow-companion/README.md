# Spec Superflow Companion Probe

This extension is an offline capability probe. It registers one read-only VS
Code Language Model Tool named `spec_superflow_companion_probe`. Calling it
returns fixed local JSON:

```json
{"ok":true,"source":"spec-superflow-companion-vsix","networkUsed":false}
```

It does not use MCP, start a process, access the workspace, read credentials,
or make network requests. It does not change `/workflow-init` yet.

## Offline validation

The repository includes the prebuilt offline package at
`release-assets/companion-probe/spec-superflow-companion-0.0.1.vsix` and its
SHA-256 checksum beside it.

1. Install the packaged `.vsix` with **Extensions: Install from VSIX...**.
2. Open Chat and choose **Configure Tools**.
3. Search for **Spec Superflow Companion Probe** and enable it.
4. Ask Agent to call `#specSuperflowCompanionProbe`.
5. Confirm the returned JSON exactly matches the value above.

If the tool is absent, company policy also blocks Extension Language Model
Tools. Stop there; installing the VSIX cannot replace that policy.
