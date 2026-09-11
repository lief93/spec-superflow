# Composable Value Classification

## Requirement

Do not turn value-producing Android composables such as an inferred-return
`getRawString` into empty ArkUI builders. Preserve adapter results through source
component arguments to native text, including source-organized multi-file output.

## Implementation Boundary

- Classify from PSI value-use positions and resolved source declarations, not
  callable casing or the `@Composable` annotation alone.
- Follow inferred expression-bodied helper returns. Retain known UI emitters and
  invoked composable slots. Creating a UI lambda does not execute that lambda.
- Report known mixed value/UI functions instead of silently dropping their UI.
- Reuse bounded callable evaluation to recognize immediately invoked returned
  lambdas/references; unknown invocation targets remain diagnostic even inside a
  value-used helper. Callable projection must not depend on an unrelated adapter manifest.
- Resolve same-file/same-package adapter calls using shared source symbol lookup;
  do not choose an ambiguous overload or another package's same-named function.
- Keep the backend's single page-JSON input and existing adapter interface.

This is bounded source analysis, not full Kotlin type inference, arbitrary
business-logic translation, or proof that a third-party function has no effects.

## Verification

1. Reproduce inferred getters as erroneous UI builders before the change.
2. Cover direct Text, button labels, nested component parameters, repeated calls,
   local/helper forwarding, exact Android adapter symbols, aliases, overloads,
   missing adapters, actual UI wrappers/slots, and mixed value/UI functions.
3. Run the full page CLI with separate Page, Banner and Copy source files and an
   explicit synthetic project adapter. Require a passing generation result and
   adapter values consumed by Text, not merely an adapter import.
4. Compile the generated page with the native ArkTS SDK without editing generated
   ETS; distinguish compile acceptance from device/visual acceptance.
5. Review a frozen candidate independently before committing task files.
