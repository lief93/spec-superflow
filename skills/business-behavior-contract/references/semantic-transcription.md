# Semantic transcription review

Review behavior at native consumer use sites, not by matching names or copying syntax.

## Preserve

- event ownership and the exact handler chain;
- state initial values, write owners, lifetime, and observable transitions;
- branch conditions and the distinct outcome of every observed case;
- navigation destination and back-stack effects;
- request inputs, output mapping, persistence effects, and available dependency boundaries;
- async entry, normal return, local failure handling, local cancellation handling, and lifecycle scope;
- validation/security conditions and their valid/invalid outcomes;
- scenario observables that distinguish each supported path.

## Fail closed

Keep a fact unresolved when the required dependency source is absent, a dynamic/native call cannot be inspected, syntax is unsupported, or a behavior is suggested only by a symbol name. Do not invent retry, authentication, cancellation, defaults, error mapping, or platform guarantees.

When target code exists, compare the actual values, resulting state, errors, navigation, persistence, and external effects. A compile success, matching declaration, or passing unrelated test is not semantic evidence.
