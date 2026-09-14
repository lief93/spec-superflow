# Backend Module Contract

Run `bash tools/kotlin-ets/tests/backend/run.sh` from the repository. Uses cached
official Kotlin 2.1.20 compiler/JDK and the existing TypeScript host transpiler;
no Compose, SDK build, installation, screenshot or device operation.

The runner writes commands, input SHA256 identities, exit codes and stdout/stderr
into a new printed temporary evidence directory. It checks input stability at
the end rather than claiming a pass over changing production bytes.

1. Compile core (excluding Main), language, stdlib, Tree and Validator with the
   executable contract, but without Printer or UI. Run on a classpath where
   EtsPrinter is absent. Both fixtures enter through the real official FIR2IR
   `withKotlinModule` and public `EtsBackend.lower`, not hand-built IR mocks.
2. Walk all target data fields, rejecting compiler objects and opaque/string
   structural payloads. Check source method/parameter spans, typed defaults,
   class/object, conditional/while, captured symbol identity and symbol types.
   Actual IR calls resolving to source functions must be nonempty; every such
   call binds the corresponding EtsFunction.symbol with external=false, matched
   by its source span rather than treating a matching printed name as binding.
   A rule matching the actual resolved function symbol returns STRING for an
   Int call; lower must throw InvalidTarget/Unsupported at that source call and
   return no program. Printer validation alone cannot satisfy this assertion.
3. Compile Printer separately. Print the identical AST repeatedly with reused
   and fresh printer instances; assert identical bytes and unchanged AST.
4. Compile the original and renamed/changed-input fixtures on the JVM and
   compare ten results with execution of the printed target on the host. This
   is a module/host differential, not ArkUI SDK or complete ETS acceptance.

Initial RED evidence: `kotlin-ets-backend-tests.Arbpfi/lower-compile.stderr`
under the system temporary directory. Official compilation reached production
`LanguageLowering.kt:68`, rejected Any where EtsExpression was required during
the typed migration. No production file was modified by this test owner.

Second architecture RED: `kotlin-ets-backend-tests.iWxgt7` in the system temporary
directory. Both fixtures pass lower-only runtime contracts and wrong-rule
rejection without Printer. Separate Printer compilation fails at Printer.kt:53:
Kotlin cannot smart-cast `branch.condition`, a public property from the separately
compiled target module. Reported to the integration owner; the test must not
merge the modules to hide this dependency-boundary failure.
