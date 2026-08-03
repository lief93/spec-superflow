## MODIFIED Requirements

### Requirement: Existing state and decision-point flow remains authoritative

Independent review SHALL reuse the existing workflow states, guarded
`state transition`, and user-authored `state set` decision-point fields. It
SHALL add only candidate-identity bindings needed to prove DP-1, DP-2, and DP-3
refer to current approved artifacts.

#### Scenario: Planning advances through the existing state machine

- **WHEN** current Planning reviews and decision-point bindings satisfy the guard
- **THEN** workflow SHALL advance through `exploring`, `specifying`, `bridging`, `approved-for-build`, `executing`, and `closing` with existing transition commands
- **AND** missing or stale bindings SHALL fail closed without introducing a second state machine
