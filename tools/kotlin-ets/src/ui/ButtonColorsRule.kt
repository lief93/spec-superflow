@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

private val buttonSource = SourceSpan("EtsButtonColors.kt", -1, -1)
internal val buttonColorsType = etsClassSymbol("EtsButtonColors", buttonSource).type as EtsNamedType
private val defaultsType = etsClassSymbol("EtsButtonDefaults", buttonSource).type as EtsNamedType
private val defaultsObject = EtsSymbol("material:buttonDefaults", "__etsButtonDefaults", defaultsType, buttonSource)
private val colorFields = listOf("containerColor", "contentColor", "disabledContainerColor", "disabledContentColor")

internal fun defaultButtonColors(scope: Scope, at: SourceSpan, text: Boolean): EtsExpression {
    val scheme = materialScheme(materialContext(scope, at), at)
    fun role(name: String) = EtsMember(scheme, name, EtsTypes.NUMBER, at)
    // AndroidX copies (replaces) the alpha channel; it does not multiply it.
    fun alpha(value: EtsExpression, byte: Int) = EtsBinary("+",
        EtsBinary("&", value, EtsLiteral(0xFFFFFF, EtsTypes.NUMBER, at), EtsTypes.NUMBER, at),
        EtsLiteral(byte.toLong() * 0x1000000L, EtsTypes.NUMBER, at), EtsTypes.NUMBER, at)
    val transparent = EtsLiteral(0, EtsTypes.NUMBER, at)
    return EtsNew(buttonColorsType, listOf(if (text) transparent else role("primary"),
        role(if (text) "primary" else "onPrimary"), if (text) transparent else alpha(role("onSurface"), 31),
        alpha(role("onSurface"), 97)), at)
}

internal class ComposeButtonColorsRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        if (sourceFile(owner) != null) return null
        return when (symbolName(owner)) {
            "androidx.compose.material3.ButtonColors" -> buttonColorsType
            "androidx.compose.material3.ButtonDefaults" -> defaultsType
            else -> null
        }
    }
    override fun lowerObject(value: IrGetObjectValue, language: Language, scope: Scope): EtsExpression? =
        if (sourceFile(value.symbol.owner) == null && symbolName(value.symbol.owner) == "androidx.compose.material3.ButtonDefaults")
            EtsReference(defaultsObject, language.source(value)) else null

    override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner.parent as IrClass
        if (sourceFile(owner) != null || symbolName(owner) != "androidx.compose.material3.ButtonColors") return null
        if (call.symbol.owner.valueParameters.map { it.name.asString() } != colorFields)
            throw Unsupported(Diagnostic("UNSUPPORTED", "Unsupported ButtonColors constructor signature", language.source(call)))
        return EtsNew(buttonColorsType, colorFields.map { language.expression(argument(call, it)!!, scope) }, language.source(call))
    }
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val api = symbolName(owner)
        val at = language.source(call)
        if (api in setOf("androidx.compose.material3.ButtonDefaults.buttonColors", "androidx.compose.material3.ButtonDefaults.textButtonColors")) {
            val receiver = call.dispatchReceiver
            if (receiver !is IrGetObjectValue && receiver !is IrGetValue)
                throw Unsupported(Diagnostic("UNSUPPORTED", "Bind ButtonDefaults receiver to a source variable before calling its color factory", at))
            if (owner.valueParameters.isNotEmpty() && owner.valueParameters.map { it.name.asString() } != colorFields)
                throw Unsupported(Diagnostic("UNSUPPORTED", "Unsupported ButtonDefaults color factory signature", at))
            val defaults = defaultButtonColors(scope, at, api.endsWith("textButtonColors")) as EtsNew
            return EtsNew(buttonColorsType, colorFields.mapIndexed { index, name ->
                argument(call, name)?.let { language.expression(it, scope) } ?: defaults.arguments[index]
            }, at)
        }
        val property = owner.correspondingPropertySymbol?.owner ?: return null
        if (property.getter?.symbol != owner.symbol) return null
        if (symbolName(property.parent as? IrClass ?: return null) == "androidx.compose.material3.ButtonColors" && property.name.asString() in colorFields)
            return EtsMember(language.expression(call.dispatchReceiver!!, scope), property.name.asString(), EtsTypes.NUMBER, at)
        return null
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        var colors = false
        var defaults = false
        program.files.forEach { it.declarations.forEach { declaration -> walkEts(declaration) { node ->
            fun uses(type: EtsType): Boolean = when (type) {
                is EtsNamedType -> {
                    if (type == buttonColorsType) colors = true
                    if (type == defaultsType) defaults = true
                    type.arguments.any(::uses)
                }
                is EtsFunctionType -> { type.parameters.forEach(::uses); uses(type.result) }
                is EtsNullableType -> uses(type.inner)
                else -> false
            }
            if (node is EtsExpression) uses(node.type)
            if (node is EtsFunction) uses(node.symbol.type)
            if (node is EtsField) uses(node.symbol.type)
        } } }
        if (!colors && !defaults) return emptyList()
        val at = buttonSource
        val declarations = mutableListOf<EtsDeclaration>()
        if (colors) {
            val self = EtsReference(EtsSymbol("button:colors:this", "this", buttonColorsType, at, true))
            val fields = colorFields.map { EtsField(EtsSymbol("button:colors:$it", it, EtsTypes.NUMBER, at), readonly = true) }
            val params = fields.map { EtsParameter(it.symbol.copy(id = it.symbol.id + ":parameter")) }
            val body = fields.zip(params).map { (f, p) -> EtsExpressionStatement(EtsAssignment(
                EtsMember(self, f.symbol.name, f.symbol.type, at, f.symbol.id), EtsReference(p.symbol), at)) }
            declarations += EtsClass(buttonColorsType.name, fields + EtsFunction("constructor", params, EtsTypes.VOID,
                body, at, kind = EtsFunctionKind.CONSTRUCTOR), at, exported = true, valueSnapshot = true)
        }
        if (defaults) {
            declarations += EtsClass(defaultsType.name, listOf(EtsFunction("constructor", emptyList(), EtsTypes.VOID,
                emptyList(), at, kind = EtsFunctionKind.CONSTRUCTOR)), at, exported = true)
            declarations += EtsGlobal(defaultsObject, EtsNew(defaultsType, emptyList(), at), false, exported = true)
        }
        return listOf(EtsFile(at.file!!, declarations))
    }
}
