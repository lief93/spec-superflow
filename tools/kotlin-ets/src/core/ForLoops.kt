@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.util.Collections
import java.util.IdentityHashMap
import org.jetbrains.kotlin.backend.common.CommonBackendContext
import org.jetbrains.kotlin.backend.common.lower.loops.ForLoopsLowering
import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFir2IrPipelineArtifact
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.types.impl.makeTypeProjection
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.types.Variance

/** Reuse common progression/array analysis, not JVM counter-loop optimizations. */
internal fun lowerForLoops(input: JvmFir2IrPipelineArtifact) {
    val module = input.result.irModuleFragment
    val originalCalls = Collections.newSetFromMap(IdentityHashMap<IrCall, Boolean>())
    module.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
        override fun visitCall(expression: IrCall) {
            originalCalls.add(expression)
            super.visitCall(expression)
        }
    })
    val realContext = createJvmLoweringContext(input)
    val context = object : CommonBackendContext by realContext {
        override val preferJavaLikeCounterLoop = false
    }
    val lowering = ForLoopsLowering(context)
    module.files.forEach(lowering::lower)
    module.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
        override fun visitCall(expression: IrCall) {
            super.visitCall(expression)
            if (expression in originalCalls) return
            val owner = expression.symbol.owner
            val receiver = expression.dispatchReceiver?.type as? IrSimpleType
            if (receiver != null && receiver.arguments.isNotEmpty()) {
                val parent = owner.parent as? IrClass ?: return
                if (receiver.classifier != parent.symbol || receiver.arguments.size != parent.typeParameters.size) return
            }
            if ((0 until expression.typeArgumentsCount).any { expression.getTypeArgument(it) == null }) return
            // Common loop builders may leave declaration T under an instantiated implicit cast.
            // Substitute only new calls; preserve their symbol, cast, offsets and original calls.
            val substitutor = IrTypeSubstitutor(expression.getTypeSubstitutionMap(owner).mapValues {
                makeTypeProjection(it.value, Variance.INVARIANT)
            }, allowEmptySubstitution = true)
            expression.type = substitutor.substitute(expression.type)
        }
    })
    module.patchDeclarationParents()
}
