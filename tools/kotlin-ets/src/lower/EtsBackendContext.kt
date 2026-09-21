package dev.ets

import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFir2IrPipelineArtifact
import org.jetbrains.kotlin.ir.declarations.IrModuleFragment
import org.jetbrains.kotlin.ir.types.IrTypeSystemContext
import org.jetbrains.kotlin.ir.types.IrTypeSystemContextImpl

/**
 * Named owner of ETS IR-to-IR services.
 *
 * This is not a second IR and not a `CommonBackendContext` implementation.
 * Official common passes still receive the frontend JVM adapter
 * (`createJvmLoweringContext`) from `src/core`. New `src/lower` code must not
 * import JVM backend lowering types; migration of those passes onto this type
 * is recorded in `docs/ets-lowering-inventory.md`.
 */
class EtsBackendContext internal constructor(
    val module: IrModuleFragment,
    val types: IrTypeSystemContext,
) {
    companion object {
        internal fun from(input: JvmFir2IrPipelineArtifact): EtsBackendContext =
            EtsBackendContext(input.result.irModuleFragment, IrTypeSystemContextImpl(input.result.irBuiltIns))
    }
}
