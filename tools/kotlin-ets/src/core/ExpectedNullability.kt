@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.backend.common.lower.AbstractValueUsageTransformer
import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFir2IrPipelineArtifact
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.expressions.impl.IrTypeOperatorCallImpl
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.visitors.transformChildrenVoid

/** FIR may omit nullability-only smart casts. Reify checked usage types for ETS. */
internal fun lowerExpectedNullability(input: JvmFir2IrPipelineArtifact) {
    val lowering = object : AbstractValueUsageTransformer(input.result.irBuiltIns) {
        override fun IrExpression.useAs(type: IrType): IrExpression {
            if (!this.type.isNullable() || type.isNullable() || this.type.makeNotNull() != type) return this
            return IrTypeOperatorCallImpl(startOffset, endOffset, type,
                IrTypeOperator.IMPLICIT_CAST, type, this)
        }

        // These nodes remain unsupported by the target; the common visitor's TODO
        // must not replace the existing source-linked target diagnostic.
        override fun visitPropertyReference(expression: IrPropertyReference): IrExpression {
            expression.transformChildrenVoid(this)
            return expression
        }

        override fun visitLocalDelegatedPropertyReference(expression: IrLocalDelegatedPropertyReference): IrExpression {
            expression.transformChildrenVoid(this)
            return expression
        }
    }
    input.result.irModuleFragment.transformChildrenVoid(lowering)
}
