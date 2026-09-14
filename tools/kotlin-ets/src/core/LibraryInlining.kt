@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.backend.common.lower.ReturnableBlockTransformer
import org.jetbrains.kotlin.backend.common.ir.ValueRemapper
import org.jetbrains.kotlin.backend.common.lower.inline.KlibSyntheticAccessorGenerator
import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFir2IrPipelineArtifact
import org.jetbrains.kotlin.descriptors.DescriptorVisibilities
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.backend.js.utils.NameTable
import org.jetbrains.kotlin.ir.declarations.IrDeclarationWithName
import org.jetbrains.kotlin.ir.declarations.IrFunction
import org.jetbrains.kotlin.ir.declarations.IrFile
import org.jetbrains.kotlin.ir.declarations.IrTypeParametersContainer
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrExpression
import org.jetbrains.kotlin.ir.expressions.IrInlinedFunctionBlock
import org.jetbrains.kotlin.ir.inline.CommonInlineCallableReferenceToLambdaPhase
import org.jetbrains.kotlin.ir.inline.FunctionInlining
import org.jetbrains.kotlin.ir.inline.InlineFunctionResolver
import org.jetbrains.kotlin.ir.inline.InlineMode
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.util.TypeRemapper
import org.jetbrains.kotlin.ir.util.remapTypes
import org.jetbrains.kotlin.ir.util.remapTypeParameters
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable
import org.jetbrains.kotlin.ir.util.patchDeclarationParents
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.name.Name
import org.jetbrains.kotlin.utils.addToStdlib.assignFrom

internal data class UnavailableInlineBody(val symbol: String, val source: SourceSpan, val evidence: String)

/** Select only bodies supplied by the session's checked source/binary provider. */
internal fun lowerSourceInlineFunctions(input: JvmFir2IrPipelineArtifact, bodies: FunctionBodies): List<UnavailableInlineBody> {
    val module = input.result.irModuleFragment
    val unavailable = mutableListOf<UnavailableInlineBody>()
    module.files.forEach { file ->
        file.acceptChildrenVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrCall && element.symbol.owner.isInline && element.symbol.owner.body == null) {
                    val function = element.symbol.owner
                    val resolution = bodies.resolve(element.symbol)
                    if (resolution is FunctionBody.Unavailable) {
                        unavailable.add(UnavailableInlineBody(function.fqNameWhenAvailable?.asString() ?: function.name.asString(),
                            SourceSpan(file.fileEntry.name, element.startOffset, element.endOffset), resolution.reason.evidence))
                    }
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
    val accessors = KlibSyntheticAccessorGenerator(context)
    val added = linkedMapOf<IrFunction, IrFunction>()
    module.files.forEach { file ->
        file.transformChildrenVoid(object : IrElementTransformerVoid() {
            private var inlineDepth = 0

            override fun visitInlinedFunctionBlock(inlinedBlock: IrInlinedFunctionBlock): IrExpression {
                inlineDepth++
                try {
                    return super.visitInlinedFunctionBlock(inlinedBlock)
                } finally {
                    inlineDepth--
                }
            }

            override fun visitCall(expression: IrCall): IrExpression {
                expression.transformChildrenVoid(this)
                val function = expression.symbol.owner
                val owner = function.parent as? IrFile ?: return expression
                if (inlineDepth == 0 || owner === file || owner !in module.files ||
                    !DescriptorVisibilities.isPrivate(function.visibility)) return expression
                // Only bridge source-owned private calls moved across files by the official inliner.
                val accessor = accessors.getSyntheticFunctionAccessor(expression, null)
                if (added.putIfAbsent(accessor, function) == null) {
                    accessor.remapTypes(object : TypeRemapper {
                        override fun enterScope(irTypeParametersContainer: IrTypeParametersContainer) = Unit
                        override fun leaveScope() = Unit
                        override fun remapType(type: IrType): IrType = type.remapTypeParameters(function, accessor)
                    })
                    accessor.transformChildrenVoid(ValueRemapper(function.parameters.zip(accessor.parameters)
                        .associate { (source, target) -> source.symbol to target.symbol }))
                }
                return accessors.modifyFunctionAccessExpression(expression, accessor.symbol).also {
                    // The shared generator assumes defaults were lowered; ETS still keeps omitted slots.
                    it.arguments.assignFrom(expression.arguments)
                }
            }
        })
    }
    val reserved = mutableSetOf<String>()
    module.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            if (element is IrDeclarationWithName && !element.name.isSpecial) reserved.add(element.name.asString())
            element.acceptChildrenVoid(this)
        }
    })
    val names = NameTable<IrFunction>(reserved = reserved)
    // Synthetic spans are not declaration identities; order and name by the original helpers.
    added.entries.sortedWith(compareBy({ (it.value.parent as IrFile).fileEntry.name },
        { it.value.startOffset }, { it.value.endOffset })).forEach { (accessor, function) ->
        accessor.name = Name.identifier(names.declareFreshName(function, accessor.name.asString()))
        (accessor.parent as IrFile).declarations.add(accessor)
    }
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
