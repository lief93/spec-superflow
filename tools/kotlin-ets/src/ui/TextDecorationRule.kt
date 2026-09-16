@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

internal val textDecorationType = EtsNamedType("TextDecorationType")
internal class ComposeTextDecorationRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? = type.classOrNull?.owner?.let {
        if (sourceFile(it) == null && symbolName(it) == "androidx.compose.ui.text.style.TextDecoration") textDecorationType else null
    }
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val property = owner.correspondingPropertySymbol?.owner ?: return null
        if (property.getter?.symbol != owner.symbol || symbolName(property.parent as? IrClass ?: return null) != "androidx.compose.ui.text.style.TextDecoration.Companion") return null
        val name = property.name.asString()
        if (name !in setOf("None", "Underline", "LineThrough")) return null
        if (call.dispatchReceiver !is IrGetObjectValue)
            throw Unsupported(Diagnostic("UNSUPPORTED", "TextDecoration constant requires the companion singleton receiver", language.source(call)))
        val at = language.source(call)
        return EtsMember(EtsReference(EtsSymbol("arkui:TextDecorationType", "TextDecorationType", textDecorationType, at, true)), name, textDecorationType, at)
    }
}
