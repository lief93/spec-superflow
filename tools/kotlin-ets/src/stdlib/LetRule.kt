@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrDeclarationOrigin
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable

/** Ordinary let calls; source/binary bodies still take the official inliner path first. */
internal object LetRule : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (symbolName(owner) != "kotlin.let" || sourceFile(owner) != null ||
            owner.origin != IrDeclarationOrigin.IR_EXTERNAL_DECLARATION_STUB || !owner.isInline ||
            owner.isSuspend || owner.isFakeOverride || owner.dispatchReceiverParameter != null ||
            call.dispatchReceiver != null || call.superQualifierSymbol != null ||
            owner.typeParameters.size != 2 || owner.typeParameters.any { it.isReified } ||
            call.typeArgumentsCount != 2 || owner.valueParameters.size != 1 || call.valueArgumentsCount != 1) return null
        val input = owner.extensionReceiverParameter?.type as? IrSimpleType ?: return null
        val output = owner.returnType as? IrSimpleType ?: return null
        if (listOf(input, output).zip(owner.typeParameters).any { (type, parameter) ->
            type.classifier != parameter.symbol || type.arguments.isNotEmpty() ||
                type.nullability != SimpleTypeNullability.NOT_SPECIFIED }) return null
        val block = owner.valueParameters.single()
        val signature = block.type as? IrSimpleType ?: return null
        if (block.isNoinline || block.isCrossinline || block.defaultValue != null || block.varargElementType != null ||
            signature.classOrNull?.owner?.fqNameWhenAvailable?.asString() != "kotlin.Function1" ||
            signature.arguments.map { (it as? IrTypeProjection)?.type } != listOf(input, output)) return null
        val receiver = call.extensionReceiver ?: return null
        val callback = call.getValueArgument(0) ?: return null
        val inputType = language.type(call.getTypeArgument(0) ?: return null)
        val outputType = language.type(call.getTypeArgument(1) ?: return null)
        if (language.type(call.type) != outputType) return null
        val at = language.source(call)
        val value = EtsSymbol("let:${at.file}:${at.start}:value", "__etsReceiver", inputType, at)
        val action = EtsSymbol("let:${at.file}:${at.start}:block", "__etsBlock", EtsFunctionType(listOf(inputType), outputType), at)
        val invoke = EtsCall(EtsReference(action), listOf(EtsReference(value)), outputType, at)
        val body = if (outputType == EtsTypes.VOID) EtsExpressionStatement(invoke) else EtsReturn(invoke, at)
        // Call arguments preserve Kotlin's receiver-before-block evaluation, each exactly once.
        return EtsCall(EtsLambda(listOf(EtsParameter(value), EtsParameter(action)), listOf(body), outputType, at),
            listOf(language.expression(receiver, scope), language.expression(callback, scope)), outputType, at)
    }
}
