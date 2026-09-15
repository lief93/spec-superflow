@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

internal class ComposeTextStyleRule : CallRule {
    override fun targetContracts(program: EtsProgram) = textStyleNativeContracts(program)
    override fun targetFiles(program: EtsProgram): List<EtsFile> =
        (if (usesTextStyle(program)) listOf(textStyleFile()) else emptyList()) + textStyleRenderingFiles(program)

    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        if (sourceFile(owner) != null) return null
        return when (symbolName(owner)) {
            "androidx.compose.ui.text.TextStyle" -> textStyleType
            "androidx.compose.ui.text.style.TextAlign" -> EtsNamedType("TextAlign")
            "androidx.compose.ui.text.style.TextOverflow" -> EtsNamedType("TextOverflow")
            else -> null
        }
    }
    override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner.parent as IrClass
        if (sourceFile(owner) != null || symbolName(owner) != "androidx.compose.ui.text.TextStyle") return null
        call.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
            if (parameter.name.asString() !in textStyleFields && call.getValueArgument(index) != null)
                reject(call, language, "Unsupported TextStyle argument: ${parameter.name}")
        }
        val at = language.source(call)
        return EtsNew(textStyleType, textStyleFields.keys.map { name ->
            argument(call, name)?.let { language.expression(it, scope) } ?: EtsLiteral(null, EtsTypes.NULL, at)
        }, at)
    }
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val property = owner.correspondingPropertySymbol?.owner ?: return null
        if (property.getter?.symbol != owner.symbol) return null
        val parent = property.parent as? IrClass ?: return null
        val name = property.name.asString()
        val at = language.source(call)
        val enums = when (symbolName(parent)) {
            "androidx.compose.ui.text.style.TextAlign.Companion" -> "TextAlign" to mapOf("Start" to "Start", "End" to "End", "Center" to "Center", "Justify" to "JUSTIFY")
            "androidx.compose.ui.text.style.TextOverflow.Companion" -> "TextOverflow" to mapOf("Clip" to "Clip", "Ellipsis" to "Ellipsis")
            else -> null
        }
        if (enums != null) {
            val target = enums.second[name] ?: reject(call, language, "Unsupported ${enums.first} value: $name")
            val type = EtsNamedType(enums.first)
            return EtsMember(EtsReference(EtsSymbol("arkui:${enums.first}", enums.first, type, at, true)), target, type, at)
        }
        if (symbolName(parent) == "androidx.compose.ui.text.TextStyle" && name in setOf("fontFamily", "fontWeight", "fontStyle")) {
            return EtsMember(language.expression(call.dispatchReceiver ?: return null, scope), name,
                EtsNullableType(textStyleFields.getValue(name)), at)
        }
        return null
    }
    private fun reject(value: IrExpression, language: Language, message: String): Nothing =
        throw Unsupported(Diagnostic("UNSUPPORTED", message, language.source(value)))
}
