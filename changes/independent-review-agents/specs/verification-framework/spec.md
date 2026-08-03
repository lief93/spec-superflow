## MODIFIED Requirements

### Requirement: Review CLI records only current stage evidence

The CLI SHALL expose only `review candidate`, `review record`, and
`review check` for stages `proposal-specs`, `design-tasks`, and `final`. Each
stage SHALL use a fixed pending-report inbox and one current result. Review
evidence SHALL bind the exact current candidate identity and fail closed when
the result is malformed, unapproved, or stale.

#### Scenario: Primary records a valid Reviewer result

- **WHEN** the fixed pending-report file is a regular in-change file with the exact schema, stage, candidate identity, verdict, and allowed finding paths
- **THEN** `review record` SHALL atomically replace only that stage current result
- **AND** `review check` SHALL pass only while the bound candidate remains current

#### Scenario: Review transport or result is unsafe

- **WHEN** the inbox is overridden, traverses outside the Change, is a symlink or directory, has a wrong stage, contains forbidden keys, has a Finding line that is not a positive integer, or does not match the current candidate
- **THEN** record or check SHALL exit nonzero without changing workflow state or another stage result

### Requirement: Final candidate covers the complete worktree

Final public candidate SHALL contain only metadata and path references, with no
tracked diff or untracked source text. Its identity SHALL internally include the
Change-owned `execution_base_commit`, porcelain status, complete
base-to-worktree diff, every untracked byte, and final evidence inputs. The CLI
SHALL record the actual `HEAD` only when a Change first enters `executing`, SHALL
not overwrite it on a later `debugging` to `executing` transition, and SHALL let
different Changes retain different bases. A mixed worktree is a review risk, not
a transition blocker. Reviewer SHALL independently obtain the fixed-base SCM
view and read every changed-file entry through ordinary host tools.

#### Scenario: Change enters execution

- **WHEN** a Change first transitions from `approved-for-build` to `executing`
- **THEN** the CLI SHALL persist the repository's resolved `HEAD` as its immutable `execution_base_commit`
- **AND** later commits or a `debugging` round trip SHALL not replace that commit

#### Scenario: Final work changes after approval

- **WHEN** any final candidate input changes after the current review
- **THEN** `review check` SHALL report the result stale and closing SHALL remain blocked

#### Scenario: Reviewer discovers and inspects a frozen final candidate

- **WHEN** Reviewer receives only the Change directory and `final` stage
- **THEN** Reviewer SHALL run `review candidate` without a caller-selected base so the CLI resolves the Change's `execution_base_commit`
- **THEN** Reviewer SHALL run read-only status, fixed-base diff, log, and necessary base-file inspection and SHALL read every untracked path
- **AND** the public candidate SHALL contain no tracked diff or untracked source text
- **AND** candidate identity, porcelain status, and cached diff SHALL remain unchanged after inspection
