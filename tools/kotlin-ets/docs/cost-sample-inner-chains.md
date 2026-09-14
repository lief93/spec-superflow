# Cost sample 2: inner chains, main-only takeover

The user corrected "single developer" to mean the main assistant alone, without
developer or reviewer agents. Preserve this policy; no further agent work is
needed to measure whether to keep it.

Counters are local token_count cumulative differences under
`.work/cost-trial/inner-chains/`. They are not account usage or billing. Cached
input is a subset of input and reasoning is a subset of output.

| Window / role | Uncached input | Cached input | Output |
| --- | ---: | ---: | ---: |
| Dispatch to handoff baseline / main | 6,970 | 1,533,184 | 3,026 |
| Dispatch to handoff baseline / delegated preparation | 87,432 | 955,904 | 8,272 |
| Main-only implementation through acceptance / main | 24,087 | 3,572,096 | 6,072 |

No reviewer usage occurred. After the main-only baseline, both agent counters
were unchanged. The initial 12m23s window includes delegated contract/fixture
preparation, user correction and scheduling wait; it is not active coding time.
Main-only window was 08:58:34 to 09:06:10 UTC, 7m36s. Publication/reporting after
acceptance is excluded; asynchronous telemetry may lag boundaries slightly.

Main reused handed-over uncompiled fixtures, wrote the runner, established RED,
implemented core/consumer changes and ran GREEN plus affected regressions. No
post-GREEN correction was needed. GREEN child logs alone sum to 114.329 seconds;
this is not the sum of baseline/regression builds. Evidence in docs/inner-chains.md.

This is NOT a controlled performance comparison: task sizes differ and solo work
benefited from delegated preparation. Do not claim a percentage speedup or token
saving from comparison with adapter modules. Continue main-only work per the
explicit user instruction, with tests and self-checks, not independent agents.
