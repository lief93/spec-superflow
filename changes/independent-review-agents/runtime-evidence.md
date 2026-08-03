# Runtime Evidence

## Current Proven Evidence

### Host contract tests

- Command: `node --test tests/lib/managed-review-workflow.test.mjs tests/lib/opencode-plugin.test.mjs tests/lib/vscode-agent-plugin.test.mjs`
- Result: `46/46 PASS` after the body-free handoff, mandatory return chain, and
  overlap-first repair.
- Proves: one visible Primary, one hidden fixed read-only Reviewer, three exact
  full checkpoints, metadata/path-only handoff, Reviewer-owned SCM inspection,
  raw-write/record/check ordering, overlap-first Planning review,
  non-full/bootstrap isolation, and VS Code/OpenCode source registration
  contracts.

### OpenCode public Reviewer tools

- Test: `tests/integration/opencode-runtime.test.mjs`
- Scope: resolves repository and freshly packed Plugin configuration with pinned
  OpenCode 1.14.48. Through public `opencode debug agent ... --tool` interfaces,
  the declared Reviewer identity executes `git status`, fixed-base `git diff`,
  `git log`, `git show`, and reads an untracked sentinel. The fixture compares
  candidate identity, porcelain-v2 status, and cached diff before and after.
- Status: `1/1 PASS`; required SCM/file reads succeed and all three before/after
  values remain byte-identical in the temporary repository. This is public host
  tool evidence, not a model-driven semantic workflow.

### CLI and guard runtime

- Scope: public `ssf review candidate|record|check`, fixed report transport,
  stage dependencies, candidate staleness, existing state lifecycle, transition
  guards, body-free public candidate, tracked gitlink mode `160000`, and final
  explicit-base Git coverage.
- Status: focused Review CLI and guard suites PASS, including the no-`O_NOFOLLOW`
  symlink regression; related Review/candidate/host/worktree suite `69/69 PASS`;
  complete source suite `422/422 PASS`.
- Frozen worktree reference: review base
  `ffa26726f555e0ccc58d95e0a64ddba3c388bf00`; identity
  `sha256:1ca2acd43f4c457e79c13d54361bd7d0d1569913bd6410a7a425854b95a7c9bd`;
  65 changed files outside the excluded current Change; cached diff 0 bytes.
- Gitlink regression: a pure temporary local submodule first reproduced the
  directory-as-file failure. Current tests prove mode/length/hash metadata,
  body-free public output, and identity changes for commit pointer, dirty
  worktree, and unstaged-to-staged transitions without network or recursion.

### Model-driven diagnostic

- Pre-fix local GPT-5.4 Design/Tasks E2E: `FAIL`. The generated run under
  `/tmp/spec-superflow-mars-dt-retest.RemA7M` showed an oversized inlined
  handoff, skipped raw result record/check processing, blockers split across
  review rounds, an unresolved upstream Scenario overlap treated as a Tasks
  repair, and Android runtime quantity calls misclaimed as static-selector
  proof.
- Post-fix model-driven E2E: `PENDING`; it has not been rerun. The source and
  pinned resolved-prompt PASS results below are contract evidence, not a model
  business-flow substitute.

### Exact delivery package

- Archive: `/tmp/spec-superflow-independent-review-gitlink-pack.bMqULr/spec-superflow-0.14.0.tgz`
- SHA-256: `8315d2b411227244919962d62b76474d72c6285755b134d59614a3559e673d42`
- Entries: `175`
- Result: exact archive offline-installed into an isolated prefix with registry
  redirected to `127.0.0.1:9`; installed version `0.14.0`, installed-source
  doctor, installed gitlink collector smoke, and package hygiene all PASS.

## PENDING Real Runtime

- Real VS Code Chat execution of Proposal/Specs, Design/Tasks, final fixed
  Reviewer, and repair/re-review has not been rerun after simplification.
- Complete post-fix model-driven OpenCode business workflow has not been rerun;
  the public Reviewer tool probe is not a semantic business-flow substitute.
- Company-internal validation has not been run by this development environment.

These items remain `PENDING`. No static test, protocol fixture, or aggregate
test count is treated as proof that they passed.

## Environment Safety

- Tests use temporary directories, isolated Git repositories, package prefixes,
  and temporary OpenCode homes.
- No remote computer or company-internal network is accessed.
- No real credential, Token, host task identifier, or user configuration is
  stored in this evidence.
- No tag, release, npm publish, or external package upload is performed.
