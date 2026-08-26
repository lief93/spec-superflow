# 03 — Prove reusable capture with Ekspensify

**What to build:** Run the same checked evidence path for the fixed Ekspensify revision, including reuse of an existing source and deterministic repair of a wrong-HEAD checkout before workflow execution.

**Blocked by:** 02 — Freeze one complete Banking evidence tracer.

**Status:** ready-for-agent

- [ ] A verified reuse source is accepted without mutating the read-only candidate.
- [ ] An existing wrong-HEAD working copy is fetched, detached at the fixed revision, and verified before migration starts.
- [ ] Wrong remote or final revision mismatch fails closed and records command/exit evidence.
- [ ] Ekspensify freezes the same complete evidence family and central Skill-identity reference as Banking.
