@file:OptIn(org.jetbrains.kotlin.ir.ObsoleteDescriptorBasedAPI::class)
package dev.ets

import org.jetbrains.kotlin.backend.common.lower.FlattenStringConcatenationLowering
import org.jetbrains.kotlin.backend.jvm.JvmBackendContext
import org.jetbrains.kotlin.backend.jvm.JvmGeneratorExtensionsImpl
import org.jetbrains.kotlin.backend.jvm.JvmIrDeserializerImpl
import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFir2IrPipelineArtifact
import org.jetbrains.kotlin.codegen.state.GenerationState
import org.jetbrains.kotlin.fir.backend.jvm.FirJvmBackendClassResolver
import org.jetbrains.kotlin.fir.backend.jvm.FirJvmBackendExtension
import org.jetbrains.kotlin.fir.backend.utils.extractFirDeclarations
import org.jetbrains.kotlin.ir.util.ExternalDependenciesGenerator

/** Reuse one compiler IR pass, not the JVM lowering pipeline or its code generator. */
fun lowerStringConcatenations(input: JvmFir2IrPipelineArtifact) {
    val context = createJvmLoweringContext(input)
    val lowering = FlattenStringConcatenationLowering(context)
    input.result.irModuleFragment.files.forEach(lowering::lower)
}

internal fun createJvmLoweringContext(input: JvmFir2IrPipelineArtifact): JvmBackendContext {
    val result = input.result
    val state = GenerationState(
        input.environment.project,
        result.irModuleFragment.descriptor,
        input.configuration,
        diagnosticReporter = input.diagnosticCollector,
        jvmBackendClassResolver = FirJvmBackendClassResolver(result.components),
    )
    val context = JvmBackendContext(
        state,
        result.irBuiltIns,
        result.symbolTable,
        JvmGeneratorExtensionsImpl(input.configuration),
        FirJvmBackendExtension(result.components,
            result.irActualizedResult?.actualizedExpectDeclarations?.extractFirDeclarations()),
        null,
        JvmIrDeserializerImpl(),
        result.components.irProviders,
        result.pluginContext,
    )
    // As in JvmIrCodegenFactory, constructing the context can reference new symbols.
    ExternalDependenciesGenerator(result.symbolTable, result.components.irProviders)
        .generateUnboundSymbolsAsDependencies()
    return context
}
