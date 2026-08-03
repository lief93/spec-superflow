## MODIFIED Requirements

### Requirement: Final review blocks closing without replacing mechanical gates

For exact `workflow: full`, Primary SHALL finish and freeze implementation,
tests, applicable package and runtime evidence, risks, and PR summary before the
fixed Reviewer performs one final semantic review. The final review SHALL occur
before the single `executing` to `closing` transition.

#### Scenario: Final candidate is approved

- **WHEN** the final candidate is current, uses an explicit stable Git base, and Reviewer returns `Approved`
- **THEN** Primary SHALL make no substantive write
- **AND** `release-archivist` SHALL own the guarded transition to `closing`
- **AND** Primary SHALL verify the persisted state is exactly `closing`

#### Scenario: Final candidate requests changes

- **WHEN** Reviewer returns `Request Changes`
- **THEN** workflow state SHALL remain `executing`
- **AND** Primary SHALL repair only located targets, rerun affected gates, freeze a new candidate, and resume the same stage-scoped Reviewer context for the one permitted re-review
