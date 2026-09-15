@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.backend.common.lower.AbstractValueUsageTransformer
import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFir2IrPipelineArtifact
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.expressions.impl.IrTypeOperatorCallImpl
import org.jetbrains.kotlin.ir.declarations.IrValueParameter
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.types.impl.makeTypeProjection
import org.jetbrains.kotlin.ir.visitors.transformChildrenVoid

/** FIR may omit nullability-only smart casts. Reify checked usage types for ETS. */
internal fun lowerExpectedNullability(input: JvmFir2IrPipelineArtifact) {
    val lowering = object : AbstractValueUsageTransformer(input.result.irBuiltIns) {
        override fun IrExpression.useAs(type: IrType): IrExpression {
            // Char and String share ETS storage but not Kotlin's boxed identity.
            if (this.type.makeNotNull().isChar() && type.makeNotNull().isAny())
                return IrTypeOperatorCallImpl(startOffset, endOffset, type,
                    IrTypeOperator.IMPLICIT_CAST, type, this)
            if (!this.type.isNullable() || type.isNullable() || this.type.makeNotNull() != type) return this
            return IrTypeOperatorCallImpl(startOffset, endOffset, type,
                IrTypeOperator.IMPLICIT_CAST, type, this)
        }

        override fun IrExpression.useAsValueArgument(expression: IrFunctionAccessExpression,
            parameter: IrValueParameter): IrExpression {
            val function = expression.symbol.owner
            if (function.origin == org.jetbrains.kotlin.ir.IrBuiltIns.BUILTIN_OPERATOR &&
                this.type.makeNotNull().isChar() && parameter.type.makeNotNull().isAny()) return this
            if (expression !is IrCall || function.typeParameters.isEmpty() ||
                function.typeParameters.size != expression.typeArgumentsCount)
                return useAsValue(parameter)
            val arguments = function.typeParameters.indices.map { index ->
                expression.getTypeArgument(index)?.let { makeTypeProjection(it, org.jetbrains.kotlin.types.Variance.INVARIANT) }
                    ?: return useAsValue(parameter)
            }
            val expected = IrTypeSubstitutor(function.typeParameters.map { it.symbol }, arguments,
                allowEmptySubstitution = true).substitute(parameter.type)
            return useAs(expected)
        }

        override fun useAsVarargElement(element: IrExpression, expression: IrVararg): IrExpression =
            element.useAs(expression.varargElementType)

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
