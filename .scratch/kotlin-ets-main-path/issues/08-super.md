# Explicit super member calls

Status: focused acceptance passed
Scope: L7 common source class methods and property accessors
Review: deferred

Use official superQualifierSymbol and resolved declaration identities, existing
heritage/substitution/constructor machinery and target member validation. Native
super must dispatch to the base implementation; no source-name matching or
rewriting ordinary this calls. Verify overrides, inherited implementations,
protected members, accessors, parameter effects and cross-file model returns.

## Implementation and evidence

The existing IR call consumer selects native EtsSuper from the source class base.
Member identity, generic substitution and protected access remain validated;
ordinary virtual calls made inside a base method still use the derived receiver.
Final stored properties use instance storage rather than prototype lookup.

Reference: official Kotlin/JS irToJs/jsAstUtils.kt superQualifierSymbol branch;
ETS uses native super rather than the JS prototype/call fallback.

- RED super/.work/run-6kRycI: source-linked explicit-super refusal.
- super/.work/run-EsaaEO: four composed JVM/flat/module observations, unchanged
  input hashes, strict host types and deterministic reverse source order.
- /private/tmp/kotlin-ets-super-sdk-WQtvZ8: four unchanged modules through
  CompileArkTS, ABC/HAP. No native execution claim.
- Target suite kotlin-ets-target-tests.olAULD passed, including protected super
  calls and refusals for unrelated bases and use outside a class.
- The first fixture had a reverse dependency from Base to the file declaring
  Child via its logger. Moved only test tracing into Trace.kt. Cyclic module
  initialization is not claimed by this acceptance.
