@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

internal class ComposeFontRule(private val resources: FontResources) : CallRule {
    private val prefix = "androidx.compose.ui.text.font."
    override fun targetFiles(program: EtsProgram) = fontValueFiles(program) + fontSelectionFiles(program)
    override fun targetImports(program: EtsProgram) = fontSelectionImports(program)
    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        if (sourceFile(owner) != null) return null
        return when (symbolName(owner)) {
            prefix + "Font", prefix + "ResourceFont" -> fontFaceType
            prefix + "FontFamily", prefix + "FontListFontFamily", prefix + "SystemFontFamily" -> fontFamilyType
            prefix + "FontWeight", prefix + "FontStyle" -> EtsTypes.NUMBER
            else -> null
        }
    }
    override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner.parent as IrClass
        if (sourceFile(owner) != null || symbolName(owner) != prefix + "FontWeight") return null
        val value = argument(call, "weight")?.let { language.expression(it, scope) }
        val weight = (value as? EtsLiteral)?.value as? Number
        if (weight == null || weight.toInt() !in 1..1000) reject(call, language, "FontWeight constructor requires a constant in 1..1000")
        return value
    }
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val name = symbolName(owner)
        val at = language.source(call)
        if (name == prefix + "Font") {
            val allowed = setOf("resId", "weight", "style")
            owner.valueParameters.forEachIndexed { index, parameter ->
                if (parameter.name.asString() !in allowed && call.getValueArgument(index) != null)
                    reject(call, language, "Font parameter is not supported: ${parameter.name}")
            }
            val resource = resources.resolve(argument(call, "resId") ?: reject(call, language, "Font requires local resId"), language, scope)
            return EtsNew(fontFaceType, listOf(EtsLiteral(resource, EtsTypes.STRING, at),
                argument(call, "weight")?.let { language.expression(it, scope) } ?: EtsLiteral(400, EtsTypes.NUMBER, at),
                argument(call, "style")?.let { language.expression(it, scope) } ?: EtsLiteral(0, EtsTypes.NUMBER, at)), at)
        }
        if (name == prefix + "FontFamily") {
            val input = argument(call, "fonts") ?: reject(call, language, "FontFamily requires nonempty font entries")
            val fonts = input as? IrVararg
                ?: reject(call, language, "FontFamily requires explicit local font entries")
            if (fonts.elements.isEmpty() || fonts.elements.any { it !is IrExpression })
                reject(call, language, "FontFamily requires nonempty, non-spread font entries")
            return EtsNew(fontFamilyType, listOf(EtsArray(fonts.elements.map { language.expression(it as IrExpression, scope) }, fontFaceType, at)), at)
        }
        val property = owner.correspondingPropertySymbol?.owner ?: return null
        if (property.getter?.symbol != owner.symbol) return null
        val parent = property.parent as? IrClass ?: return null
        val parentName = symbolName(parent)
        val propertyName = property.name.asString()
        if (parentName == prefix + "FontFamily.Companion" && propertyName == "Default") {
            return EtsNew(fontFamilyType, listOf(EtsArray(emptyList(), fontFaceType, at)), at)
        }
        if (parentName == prefix + "FontWeight.Companion") {
            val weight = mapOf("Thin" to 100, "ExtraLight" to 200, "Light" to 300, "Normal" to 400,
                "Medium" to 500, "SemiBold" to 600, "Bold" to 700, "ExtraBold" to 800, "Black" to 900)[propertyName]
                ?: (100..900 step 100).firstOrNull { "W$it" == propertyName } ?: return null
            return EtsLiteral(weight, EtsTypes.NUMBER, at)
        }
        if (parentName == prefix + "FontStyle.Companion") {
            val style = when (propertyName) { "Normal" -> 0; "Italic" -> 1; else -> return null }
            return EtsLiteral(style, EtsTypes.NUMBER, at)
        }
        val receiver = call.dispatchReceiver ?: return null
        if (parentName == prefix + "FontWeight" && propertyName == "weight") return language.expression(receiver, scope)
        if (parentName in setOf(prefix + "Font", prefix + "ResourceFont") && propertyName in setOf("weight", "style"))
            return EtsMember(language.expression(receiver, scope), propertyName, EtsTypes.NUMBER, at)
        return null
    }
    private fun reject(element: IrExpression, language: Language, message: String): Nothing =
        throw Unsupported(Diagnostic("UNSUPPORTED", message, language.source(element)))
}
