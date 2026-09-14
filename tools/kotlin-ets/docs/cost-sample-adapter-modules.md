# Cost sample 1: independent adapter modules

Accepted 2026-09-14 after focused tests, fixed independent review, one finding
and a passing re-review. Main implemented the shared API/wiring; Parfit implemented
discovery, examples and CLI evidence. Aristotle reviewed the frozen result.

## Measured boundary

Local token_count cumulative-counter differences between dispatch-start.json
(08:08:03 UTC) and acceptance.json (08:37:31 UTC), under
`.work/cost-trial/adapter-modules/`. Elapsed: 29m28s. Preparation before dispatch,
prior R2H publication, and this report/commit/push after acceptance are excluded.
Counter samples are asynchronous and may lag the boundary slightly. These are
observed token counts, not billing or account-quota consumption.

| Role | Uncached input | Cached input | Output |
| --- | ---: | ---: | ---: |
| Main | 146,480 | 6,208,256 | 11,839 |
| Parfit | 144,799 | 4,216,448 | 35,594 |
| Aristotle | 35,033 | 2,480,256 | 4,737 |
| Total | 326,312 | 12,904,960 | 52,170 |

Cached input is included in total input (13,231,272), not added twice.
Reasoning is included in output. The long persistent tasks replay substantial
cached context; raw totals cannot be equated to subscription usage or cost.

## Time and rework

- Main implementation/checks froze at approximately 08:15:52; Parfit was still
  preparing tests when granted the compiler slot, so no idle slot wait was measured.
- First review began after 08:28:00. Review windows: 2m13s and 31s, no rebuilds.
- Parfit's first recorded window was 17m01s; initial inspection preceded that
  clock. Initial CLI/JVM child logs sum to 158.237s. This excludes main tests,
  fresh post-review tests and SDK setup; it is not total build time.
- Four initial harness/fixture/example corrections were retained. One independent
  review finding required a real RED reproduction, explicit default-modifier
  rejection, a fresh eight-case CLI run and a fresh SDK compile.
- Main waited after its writer freeze while Parfit finished; that waiting overlaps
  developer work, so it must not be added to elapsed time. Coordination-only token
  costs cannot be separated exactly from main implementation counters.

## Decision

This sample proves actual cost, not a speedup: no comparable serial implementation
was run, and repeating it would waste quota. The useful implementation overlap
does not establish that two writers were more cost-effective. Use ONE persistent
developer for sample 2, main coordination only, with the same fixed independent
reviewer and acceptance standard. Avoid broad repeated status reads. If two
different workloads do not give clear evidence of benefit, retain serial work.
