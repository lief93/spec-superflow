## MODIFIED Requirements

### Requirement: Planning has two independent semantic checkpoints

Exact `workflow: full` SHALL review Proposal and Specs before Design or Tasks,
and SHALL review Design and Tasks before creating `execution-contract.md`.
Reviewer approval and user decision points SHALL remain separate gates.

#### Scenario: Proposal and Specs become ready for DP-1

- **WHEN** current Proposal and delta Specs pass structural validation
- **THEN** Primary SHALL create and check a `proposal-specs` review candidate
- **AND** Reviewer SHALL reject unresolved Scenario overlap after comparing trigger, outcome, observable surface, acceptance risk, and subset or superset relationships
- **AND** Design and Tasks SHALL remain unwritten until the current result is `Approved` and the user confirms DP-1 bound to that candidate identity

#### Scenario: Design and Tasks become ready for DP-2

- **WHEN** DP-1 is current and Design and Tasks pass structural validation
- **THEN** Primary SHALL create and check a `design-tasks` review candidate
- **AND** Reviewer SHALL scan upstream overlap before downstream planning and fail closed with `upstream_conflict:` when distinct proof and single Test Case ownership cannot both hold
- **AND** Reviewer SHALL distinguish static source obligations from runtime proof, including that Android `getQuantityString(0/1/2)` does not prove static quantity selectors exist
- **AND** `execution-contract.md` SHALL remain unwritten until the current result is `Approved` and the user confirms DP-2 bound to that candidate identity
