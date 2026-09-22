package dev.ets

import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFir2IrPipelineArtifact

/**
 * Ordered IR-to-IR pipeline. Frontend owns compiler lifetime and FIR2IR;
 * this type owns phase order. Implementations stay in `src/core` for this
 * batch so behavior matches `arch/kotlin-ets-v2`.
 */
object EtsLoweringPhases {
    enum class Id {
        SOURCE_INLINE,
        LOCAL_DECLARATIONS,
        INHERITED_DEFAULTS,
        NATIVE_CONSTRUCTOR_DISPATCH,
        SECONDARY_CONSTRUCTORS,
        FOR_LOOPS,
        STRING_CONCATENATION,
        EXPECTED_NULLABILITY,
        GENERIC_BOUNDS,
        REBIND_INLINED_CAPTURES,
    }

    val order: List<Id> = listOf(
        Id.SOURCE_INLINE,
        Id.LOCAL_DECLARATIONS,
        Id.INHERITED_DEFAULTS,
        Id.NATIVE_CONSTRUCTOR_DISPATCH,
        Id.SECONDARY_CONSTRUCTORS,
        Id.FOR_LOOPS,
        Id.STRING_CONCATENATION,
        Id.EXPECTED_NULLABILITY,
        Id.GENERIC_BOUNDS,
        Id.REBIND_INLINED_CAPTURES,
    )

    internal data class Result(
        val unavailableInlineBodies: List<UnavailableInlineBody>,
        val context: EtsBackendContext,
    )

    internal fun run(
        input: JvmFir2IrPipelineArtifact,
        bodies: FunctionBodies,
        rebindInlinedCaptures: () -> Unit,
    ): Result {
        val unavailable = JvmEtsIrLowerings.lowerSourceInlineFunctions(input, bodies)
        JvmEtsIrLowerings.lowerLocalDeclarations(input)
        JvmEtsIrLowerings.lowerInheritedDefaults(input)
        JvmEtsIrLowerings.lowerNativeConstructorDispatch(input)
        JvmEtsIrLowerings.lowerSecondaryConstructors(input)
        JvmEtsIrLowerings.lowerForLoops(input)
        JvmEtsIrLowerings.lowerStringConcatenations(input)
        JvmEtsIrLowerings.lowerExpectedNullability(input)
        JvmEtsIrLowerings.lowerGenericBounds(input)
        rebindInlinedCaptures()
        return Result(unavailable, EtsBackendContext.from(input))
    }
}

/**
 * JVM-frontend adapter that hosts official common passes. The only production
 * caller is [EtsLoweringPhases]. Keep JVM backend lowering types in `src/core`,
 * never in `src/target` or `src/output`.
 */
internal object JvmEtsIrLowerings {
    fun lowerSourceInlineFunctions(input: JvmFir2IrPipelineArtifact, bodies: FunctionBodies) =
        dev.ets.lowerSourceInlineFunctions(input, bodies)
    fun lowerLocalDeclarations(input: JvmFir2IrPipelineArtifact) = dev.ets.lowerLocalDeclarations(input)
    fun lowerInheritedDefaults(input: JvmFir2IrPipelineArtifact) = dev.ets.lowerInheritedDefaults(input)
    fun lowerNativeConstructorDispatch(input: JvmFir2IrPipelineArtifact) = dev.ets.lowerNativeConstructorDispatch(input)
    fun lowerSecondaryConstructors(input: JvmFir2IrPipelineArtifact) = dev.ets.lowerSecondaryConstructors(input)
    fun lowerForLoops(input: JvmFir2IrPipelineArtifact) = dev.ets.lowerForLoops(input)
    fun lowerStringConcatenations(input: JvmFir2IrPipelineArtifact) = dev.ets.lowerStringConcatenations(input)
    fun lowerExpectedNullability(input: JvmFir2IrPipelineArtifact) = dev.ets.lowerExpectedNullability(input)
    fun lowerGenericBounds(input: JvmFir2IrPipelineArtifact) = dev.ets.lowerGenericBounds(input)
}
