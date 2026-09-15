@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrDeclarationOrigin
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable
import org.jetbrains.kotlin.ir.util.isNullable

/** The existing array-backed collection representation supplies Kotlin's empty predicate. */
internal object CollectionEmptinessRules : CallRule {
    private val collections = setOf("kotlin.collections.Collection", "kotlin.collections.List", "kotlin.collections.MutableList")

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        val name = symbolName(owner)
        val extension = name == "kotlin.collections.isNotEmpty"
        if (!extension && name !in collections.map { "$it.isEmpty" }) return null
        if (sourceFile(owner) != null || owner.isSuspend || call.superQualifierSymbol != null ||
            owner.valueParameters.isNotEmpty() || call.valueArgumentsCount != 0 ||
            !owner.returnType.isBoolean() || !call.type.isBoolean()) return null
        val receiver = if (extension) call.extensionReceiver else call.dispatchReceiver
        val receiverType = receiver?.type as? IrSimpleType ?: return null
        if (receiverType.isNullable() || receiverType.classOrNull?.owner?.fqNameWhenAvailable?.asString() !in collections ||
            receiverType.arguments.size != 1) return null
        if (extension) {
            if (owner.origin != IrDeclarationOrigin.IR_EXTERNAL_DECLARATION_STUB || !owner.isInline || owner.isFakeOverride ||
                owner.dispatchReceiverParameter != null || call.dispatchReceiver != null ||
                owner.typeParameters.size != 1 || owner.typeParameters.single().isReified || call.typeArgumentsCount != 1) return null
            val declared = owner.extensionReceiverParameter?.type as? IrSimpleType ?: return null
            if (declared.isNullable() || declared.classOrNull?.owner?.fqNameWhenAvailable?.asString() != "kotlin.collections.Collection") return null
            val element = (declared.arguments.singleOrNull() as? IrTypeProjection)?.type as? IrSimpleType ?: return null
            if (element.classifier != owner.typeParameters.single().symbol ||
                element.nullability != SimpleTypeNullability.NOT_SPECIFIED || element.arguments.isNotEmpty()) return null
            val actual = (receiverType.arguments.single() as? IrTypeProjection)?.type ?: return null
            if (call.getTypeArgument(0) != actual) return null
        } else if (owner.extensionReceiverParameter != null || call.extensionReceiver != null ||
            owner.dispatchReceiverParameter == null || owner.typeParameters.isNotEmpty() || call.typeArgumentsCount != 0) return null
        val at = language.source(call)
        val length = EtsMember(language.expression(receiver, scope), "length", EtsTypes.NUMBER, at)
        return EtsBinary(if (extension) "!==" else "===", length, EtsLiteral(0, EtsTypes.NUMBER, at), EtsTypes.BOOLEAN, at)
    }
}
