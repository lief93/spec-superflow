@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.backend.common.lower.ReturnableBlockTransformer
import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFir2IrPipelineArtifact
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.IrFunction
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.inline.CommonInlineCallableReferenceToLambdaPhase
import org.jetbrains.kotlin.ir.inline.FunctionInlining
import org.jetbrains.kotlin.ir.inline.InlineFunctionResolver
import org.jetbrains.kotlin.ir.inline.InlineMode
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable
import org.jetbrains.kotlin.ir.util.patchDeclarationParents
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.load.kotlin.JvmPackagePartSource
import org.jetbrains.kotlin.load.kotlin.KotlinJvmBinarySourceElement

internal data class UnavailableInlineBody(val symbol: String, val source: SourceSpan, val evidence: String)

private fun binaryBodyEvidence(function: IrFunction): String {
    val binaryClass = when (val source = function.containerSource) {
        is JvmPackagePartSource -> source.knownJvmBinaryClass
        is KotlinJvmBinarySourceElement -> source.binaryClass
        else -> null
    } ?: return "JVM binary metadata is unavailable for this declaration."
    val bytes = binaryClass.classHeader.serializedIr
        ?: return "JVM binary metadata contains no serialized IR."
    return "JVM binary metadata contains serialized IR (${bytes.size} bytes), but the serialized dependency " +
        "format ${binaryClass.classHeader.kind} is outside the supported top-level JVM file-facade body route."
}

/** Select only bodies supplied by the session's checked source/binary provider. */
internal fun lowerSourceInlineFunctions(input: JvmFir2IrPipelineArtifact, bodies: FunctionBodies): List<UnavailableInlineBody> {
    val module = input.result.irModuleFragment
    val unavailable = mutableListOf<UnavailableInlineBody>()
    module.files.forEach { file ->
        file.acceptChildrenVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrCall && element.symbol.owner.isInline && element.symbol.owner.body == null &&
                    bodies.resolve(element.symbol) !is FunctionBody.Available) {
                    val function = element.symbol.owner
                    unavailable.add(UnavailableInlineBody(function.fqNameWhenAvailable?.asString() ?: function.name.asString(),
                        SourceSpan(file.fileEntry.name, element.startOffset, element.endOffset), binaryBodyEvidence(function)))
                }
                element.acceptChildrenVoid(this)
            }
        })
    }
    val resolver = object : InlineFunctionResolver(InlineMode.ALL_INLINE_FUNCTIONS) {
        override fun needsInlining(function: IrFunction): Boolean =
            function.isInline && bodies.resolve(function.symbol) is FunctionBody.Available
    }
    val context = createJvmLoweringContext(input)
    val callableReferences = CommonInlineCallableReferenceToLambdaPhase(context, resolver)
    module.files.forEach(callableReferences::lower)
    FunctionInlining(context, resolver, produceOuterThisFields = false).inline(module)
    module.transformChildrenVoid(ReturnableBlockTransformer(context))
    module.patchDeclarationParents()
    return unavailable
}

internal fun explainUnavailableInlineBody(failure: Unsupported, unavailable: List<UnavailableInlineBody>): Unsupported {
    val body = unavailable.firstOrNull { it.source == failure.diagnostic.source } ?: return failure
    return Unsupported(failure.diagnostic.copy(message =
        "External inline call has no loaded IR body: ${body.symbol}. " +
            "Provide explicit dependency source or a supported serialized dependency; this call has no usable binary IR body. " +
            "${body.evidence} ${failure.diagnostic.message}"))
}
