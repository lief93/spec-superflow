@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

private const val lineHeightStyleName = "androidx.compose.ui.text.style.LineHeightStyle"
private val lineHeightStyleSource = SourceSpan("EtsLineHeightStyle.kt", -1, -1)
internal val lineHeightAlignmentType = etsClassSymbol("EtsLineHeightAlignment", lineHeightStyleSource).type as EtsNamedType
internal val lineHeightTrimType = etsClassSymbol("EtsLineHeightTrim", lineHeightStyleSource).type as EtsNamedType
internal val lineHeightModeType = etsClassSymbol("EtsLineHeightMode", lineHeightStyleSource).type as EtsNamedType
internal val lineHeightStyleType = etsClassSymbol("EtsLineHeightStyle", lineHeightStyleSource).type as EtsNamedType

private val lineHeightTypes = linkedMapOf(
    lineHeightStyleName to lineHeightStyleType,
    "$lineHeightStyleName.Alignment" to lineHeightAlignmentType,
    "$lineHeightStyleName.Trim" to lineHeightTrimType,
    "$lineHeightStyleName.Mode" to lineHeightModeType,
)

private fun lineHeightValueSymbol(kind: String, name: String, type: EtsNamedType) =
    EtsSymbol("compose:lineHeightStyle:$kind:$name", "__etsLineHeight${kind}$name", type, lineHeightStyleSource)

private val lineHeightAlignmentValues = listOf("Top", "Center", "Proportional", "Bottom").associateWith {
    lineHeightValueSymbol("Alignment", it, lineHeightAlignmentType)
}
private val lineHeightTrimValues = listOf("FirstLineTop", "LastLineBottom", "Both", "None").associateWith {
    lineHeightValueSymbol("Trim", it, lineHeightTrimType)
}
private val lineHeightModeValues = listOf("Fixed", "Minimum").associateWith {
    lineHeightValueSymbol("Mode", it, lineHeightModeType)
}
private val defaultLineHeightStyle = EtsSymbol("compose:lineHeightStyle:default", "__etsLineHeightStyleDefault",
    lineHeightStyleType, lineHeightStyleSource)

internal fun lineHeightAlignment(name: String, at: SourceSpan) =
    EtsReference(lineHeightAlignmentValues.getValue(name), at)
internal fun lineHeightTrim(name: String, at: SourceSpan) = EtsReference(lineHeightTrimValues.getValue(name), at)
internal fun lineHeightMode(name: String, at: SourceSpan) = EtsReference(lineHeightModeValues.getValue(name), at)

internal class ComposeLineHeightStyleRule : CallRule {
    override fun targetFiles(program: EtsProgram): List<EtsFile> =
        if (usesLineHeightStyle(program)) listOf(lineHeightStyleFile()) else emptyList()

    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        if (sourceFile(owner) != null) return null
        return lineHeightTypes[symbolName(owner)]
    }

    override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner.parent as IrClass
        val name = symbolName(owner)
        if (sourceFile(owner) != null || name !in lineHeightTypes) return null
        if (name != lineHeightStyleName)
            reject(call, language, "Only published LineHeightStyle values are supported")
        val parameters = call.symbol.owner.valueParameters.map { it.name.asString() }
        if (parameters !in listOf(listOf("alignment", "trim"), listOf("alignment", "trim", "mode")))
            reject(call, language, "Unsupported LineHeightStyle constructor signature")
        val at = language.source(call)
        val alignment = argument(call, "alignment") ?: reject(call, language, "LineHeightStyle requires alignment")
        val trim = argument(call, "trim") ?: reject(call, language, "LineHeightStyle requires trim")
        return EtsNew(lineHeightStyleType, listOf(language.expression(alignment, scope),
            language.expression(trim, scope), argument(call, "mode")?.let { language.expression(it, scope) }
                ?: lineHeightMode("Fixed", at)), at)
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val at = language.source(call)
        val api = symbolName(owner)
        if (api == "kotlin.internal.ir.EQEQ" && call.valueArgumentsCount == 2) {
            val left = call.getValueArgument(0) ?: return null
            val right = call.getValueArgument(1) ?: return null
            val semantic = lineHeightTypes[left.type.classOrNull?.owner?.let(::symbolName)] ?: return null
            if (lineHeightTypes[right.type.classOrNull?.owner?.let(::symbolName)] != semantic) return null
            return equality(language.expression(left, scope), language.expression(right, scope), semantic, at)
        }
        if (api == "$lineHeightStyleName.copy") {
            val receiver = call.dispatchReceiver ?: reject(call, language, "LineHeightStyle.copy requires a receiver")
            val lowered = language.expression(receiver, scope)
            val values = listOf("alignment" to lineHeightAlignmentType, "trim" to lineHeightTrimType,
                "mode" to lineHeightModeType).map { (name, type) ->
                argument(call, name)?.let { language.expression(it, scope) }
                    ?: EtsMember(lowered, name, type, at)
            }
            return EtsNew(lineHeightStyleType, values, at)
        }
        if (owner.name.asString() == "equals" && owner.valueParameters.size == 1 &&
            (owner.parent as? IrClass)?.let(::symbolName) == lineHeightStyleName) {
            val receiver = call.dispatchReceiver ?: return null
            val other = call.getValueArgument(0) ?: return null
            if (other.type.classOrNull?.owner?.let(::symbolName) != lineHeightStyleName) return null
            return equality(language.expression(receiver, scope), language.expression(other, scope), lineHeightStyleType, at)
        }
        if (api.contains("constructor-impl") && api.startsWith(lineHeightStyleName + "."))
            reject(call, language, "Only published LineHeightStyle values are supported")

        val property = owner.correspondingPropertySymbol?.owner ?: return null
        if (property.getter?.symbol != owner.symbol) return null
        val parent = property.parent as? IrClass ?: return null
        val parentName = symbolName(parent)
        val propertyName = property.name.asString()
        when (parentName) {
            "$lineHeightStyleName.Alignment.Companion" -> lineHeightAlignmentValues[propertyName]?.let {
                return EtsReference(it, at)
            }
            "$lineHeightStyleName.Trim.Companion" -> lineHeightTrimValues[propertyName]?.let {
                return EtsReference(it, at)
            }
            "$lineHeightStyleName.Mode.Companion" -> lineHeightModeValues[propertyName]?.let {
                return EtsReference(it, at)
            }
            "$lineHeightStyleName.Companion" -> if (propertyName == "Default")
                return EtsReference(defaultLineHeightStyle, at)
            lineHeightStyleName -> {
                val type = when (propertyName) {
                    "alignment" -> lineHeightAlignmentType
                    "trim" -> lineHeightTrimType
                    "mode" -> lineHeightModeType
                    else -> return null
                }
                val receiver = call.dispatchReceiver ?: return null
                return EtsMember(language.expression(receiver, scope), propertyName, type, at)
            }
        }
        return null
    }

    private fun equality(left: EtsExpression, right: EtsExpression, type: EtsNamedType,
        at: SourceSpan): EtsExpression {
        if (type != lineHeightStyleType) return EtsBinary("===", left, right, EtsTypes.BOOLEAN, at)
        fun same(name: String, fieldType: EtsType) = EtsBinary("===",
            EtsMember(left, name, fieldType, at), EtsMember(right, name, fieldType, at), EtsTypes.BOOLEAN, at)
        return EtsBinary("&&", EtsBinary("&&", same("alignment", lineHeightAlignmentType),
            same("trim", lineHeightTrimType), EtsTypes.BOOLEAN, at), same("mode", lineHeightModeType),
            EtsTypes.BOOLEAN, at)
    }

    private fun reject(value: IrExpression, language: Language, message: String): Nothing =
        throw Unsupported(Diagnostic("UNSUPPORTED", message, language.source(value)))
}

private fun lineHeightStyleFile(): EtsFile {
    val at = lineHeightStyleSource
    fun emptyType(type: EtsNamedType) = EtsClass(type.name, listOf(EtsFunction("constructor", emptyList(),
        EtsTypes.VOID, emptyList(), at, kind = EtsFunctionKind.CONSTRUCTOR)), at, exported = true)
    val receiver = EtsReference(EtsSymbol("lineHeightStyle:this", "this", lineHeightStyleType, at, external = true))
    val values = linkedMapOf("alignment" to lineHeightAlignmentType, "trim" to lineHeightTrimType,
        "mode" to lineHeightModeType)
    val parameters = values.map { (name, type) ->
        EtsParameter(EtsSymbol("lineHeightStyle:parameter:$name", name, type, at))
    }
    val fields = values.map { (name, type) ->
        EtsField(EtsSymbol("lineHeightStyle:field:$name", name, type, at), readonly = true)
    }
    val constructor = EtsFunction("constructor", parameters, EtsTypes.VOID,
        fields.zip(parameters).map { (field, parameter) -> EtsExpressionStatement(EtsAssignment(
            EtsMember(receiver, field.symbol.name, field.symbol.type, at, field.symbol.id), EtsReference(parameter.symbol), at)) },
        at, kind = EtsFunctionKind.CONSTRUCTOR)
    val singletons = (lineHeightAlignmentValues.values.map { it to lineHeightAlignmentType } +
        lineHeightTrimValues.values.map { it to lineHeightTrimType } +
        lineHeightModeValues.values.map { it to lineHeightModeType }).map { (symbol, type) ->
        EtsGlobal(symbol, EtsNew(type, emptyList(), at), mutable = false, exported = true)
    }
    val default = EtsGlobal(defaultLineHeightStyle, EtsNew(lineHeightStyleType, listOf(
        lineHeightAlignment("Proportional", at), lineHeightTrim("Both", at), lineHeightMode("Fixed", at)), at),
        mutable = false, exported = true)
    return EtsFile(at.file!!, listOf(emptyType(lineHeightAlignmentType), emptyType(lineHeightTrimType),
        emptyType(lineHeightModeType), EtsClass(lineHeightStyleType.name, fields + constructor, at, exported = true)) +
        singletons + default)
}

private fun usesLineHeightStyle(program: EtsProgram): Boolean {
    var used = false
    fun type(value: EtsType) {
        when (value) {
            is EtsNamedType -> {
                if (value.symbolId in lineHeightTypes.values.mapNotNull { it.symbolId }) used = true
                value.arguments.forEach(::type)
            }
            is EtsNullableType -> type(value.inner)
            is EtsFunctionType -> { value.parameters.forEach(::type); type(value.result) }
            is EtsRecordType -> value.fields.values.forEach(::type)
            is EtsTupleType -> value.elements.forEach(::type)
            is EtsCapturedType -> { type(value.readType); type(value.writeType) }
            is EtsTypeParameterType -> Unit
        }
    }
    program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
        if (node is EtsExpression) type(node.type)
        when (node) {
            is EtsFunction -> type(node.symbol.type)
            is EtsField -> type(node.symbol.type)
            is EtsGlobal -> type(node.symbol.type)
            is EtsVariable -> type(node.symbol.type)
            else -> Unit
        }
    } } }
    return used
}
