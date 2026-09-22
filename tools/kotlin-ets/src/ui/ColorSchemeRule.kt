@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

private val materialColorSchemeSource = SourceSpan("EtsMaterialColorScheme.kt", -1, -1)
internal val materialColorSchemeType = etsClassSymbol("EtsMaterialColorScheme", materialColorSchemeSource).type as EtsNamedType
internal val materialColorValuesType = etsClassSymbol("EtsMaterialColorValues", materialColorSchemeSource).type as EtsNamedType

// AndroidX Material3 ColorLightTokens/ColorDarkTokens, palette v0_210. This is
// the target ColorScheme contract order; resolved source factory overloads bind
// to it by semantic role name.
internal val materialColorSchemeDefaults = linkedMapOf(
    "primary" to (0xFF6750A4L to 0xFFD0BCFFL),
    "onPrimary" to (0xFFFFFFFFL to 0xFF381E72L),
    "primaryContainer" to (0xFFEADDFFL to 0xFF4F378BL),
    "onPrimaryContainer" to (0xFF21005DL to 0xFFEADDFFL),
    "inversePrimary" to (0xFFD0BCFFL to 0xFF6750A4L),
    "secondary" to (0xFF625B71L to 0xFFCCC2DCL),
    "onSecondary" to (0xFFFFFFFFL to 0xFF332D41L),
    "secondaryContainer" to (0xFFE8DEF8L to 0xFF4A4458L),
    "onSecondaryContainer" to (0xFF1D192BL to 0xFFE8DEF8L),
    "tertiary" to (0xFF7D5260L to 0xFFEFB8C8L),
    "onTertiary" to (0xFFFFFFFFL to 0xFF492532L),
    "tertiaryContainer" to (0xFFFFD8E4L to 0xFF633B48L),
    "onTertiaryContainer" to (0xFF31111DL to 0xFFFFD8E4L),
    "background" to (0xFFFEF7FFL to 0xFF141218L),
    "onBackground" to (0xFF1D1B20L to 0xFFE6E0E9L),
    "surface" to (0xFFFEF7FFL to 0xFF141218L),
    "onSurface" to (0xFF1D1B20L to 0xFFE6E0E9L),
    "surfaceVariant" to (0xFFE7E0ECL to 0xFF49454FL),
    "onSurfaceVariant" to (0xFF49454FL to 0xFFCAC4D0L),
    "surfaceTint" to (0xFF6750A4L to 0xFFD0BCFFL),
    "inverseSurface" to (0xFF322F35L to 0xFFE6E0E9L),
    "inverseOnSurface" to (0xFFF5EFF7L to 0xFF322F35L),
    "error" to (0xFFB3261EL to 0xFFF2B8B5L),
    "onError" to (0xFFFFFFFFL to 0xFF601410L),
    "errorContainer" to (0xFFF9DEDCL to 0xFF8C1D18L),
    "onErrorContainer" to (0xFF410E0BL to 0xFFF9DEDCL),
    "outline" to (0xFF79747EL to 0xFF938F99L),
    "outlineVariant" to (0xFFCAC4D0L to 0xFF49454FL),
    "scrim" to (0xFF000000L to 0xFF000000L),
    "surfaceBright" to (0xFFFEF7FFL to 0xFF3B383EL),
    "surfaceContainer" to (0xFFF3EDF7L to 0xFF211F26L),
    "surfaceContainerHigh" to (0xFFECE6F0L to 0xFF2B2930L),
    "surfaceContainerHighest" to (0xFFE6E0E9L to 0xFF36343BL),
    "surfaceContainerLow" to (0xFFF7F2FAL to 0xFF1D1B20L),
    "surfaceContainerLowest" to (0xFFFFFFFFL to 0xFF0F0D13L),
    "surfaceDim" to (0xFFDED8E1L to 0xFF141218L),
    "primaryFixed" to (0xFFEADDFFL to 0xFFEADDFFL),
    "primaryFixedDim" to (0xFFD0BCFFL to 0xFFD0BCFFL),
    "onPrimaryFixed" to (0xFF21005DL to 0xFF21005DL),
    "onPrimaryFixedVariant" to (0xFF4F378BL to 0xFF4F378BL),
    "secondaryFixed" to (0xFFE8DEF8L to 0xFFE8DEF8L),
    "secondaryFixedDim" to (0xFFCCC2DCL to 0xFFCCC2DCL),
    "onSecondaryFixed" to (0xFF1D192BL to 0xFF1D192BL),
    "onSecondaryFixedVariant" to (0xFF4A4458L to 0xFF4A4458L),
    "tertiaryFixed" to (0xFFFFD8E4L to 0xFFFFD8E4L),
    "tertiaryFixedDim" to (0xFFEFB8C8L to 0xFFEFB8C8L),
    "onTertiaryFixed" to (0xFF31111DL to 0xFF31111DL),
    "onTertiaryFixedVariant" to (0xFF633B48L to 0xFF633B48L),
)

internal val materialColorSchemeParameters = materialColorSchemeDefaults.keys.map {
    if (it == "surfaceTint") EtsNullableType(EtsTypes.NUMBER) else EtsTypes.NUMBER
}

internal class ComposeColorSchemeRule : CallRule {
    override fun targetFiles(program: EtsProgram): List<EtsFile> =
        if (materialColorSchemeUsed(program)) listOf(materialColorSchemeFile()) else emptyList()

    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        return materialColorSchemeType.takeIf {
            symbolName(owner) == "androidx.compose.material3.ColorScheme" && sourceFile(owner) == null
        }
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val api = symbolName(owner)
        val at = language.source(call)
        if (api in setOf("androidx.compose.material3.lightColorScheme", "androidx.compose.material3.darkColorScheme")) {
            if (owner.dispatchReceiverParameter != null || owner.extensionReceiverParameter != null ||
                owner.returnType.classOrNull?.owner?.let(::symbolName) != "androidx.compose.material3.ColorScheme")
                throw Unsupported(Diagnostic("UNSUPPORTED", "Unsupported Material3 ColorScheme factory receiver or result type", at))
            val parameters = owner.valueParameters
            val names = parameters.map { it.name.asString() }
            val unknown = names.filterNot(materialColorSchemeDefaults::containsKey)
            if (unknown.isNotEmpty() || names.distinct().size != names.size)
                throw Unsupported(Diagnostic("UNSUPPORTED",
                    "Unsupported Material3 ColorScheme roles: ${unknown.ifEmpty { names }}", at))
            val roleOrder = materialColorSchemeDefaults.keys.withIndex().associate { it.value to it.index }
            val resolvedOrder = names.map(roleOrder::getValue)
            if (resolvedOrder != resolvedOrder.sorted())
                throw Unsupported(Diagnostic("UNSUPPORTED",
                    "Material3 ColorScheme role order cannot preserve source evaluation order", at))
            parameters.firstOrNull {
                it.varargElementType != null || it.type.classOrNull?.owner?.let(::symbolName) != colorType
            }?.let { parameter ->
                throw Unsupported(Diagnostic("UNSUPPORTED",
                    "Material3 ColorScheme role ${parameter.name} must resolve to Color", at))
            }
            val dark = api == "androidx.compose.material3.darkColorScheme"
            val explicit = parameters.mapIndexedNotNull { index, parameter ->
                call.getValueArgument(index)?.let { value ->
                    parameter.name.asString() to language.expression(value, scope)
                }
            }.toMap()
            val values = materialColorSchemeDefaults.map { (name, defaults) ->
                val fallback = EtsLiteral(if (dark) defaults.second else defaults.first, EtsTypes.NUMBER, at)
                explicit[name]?.let { value ->
                    if (name == "surfaceTint") value
                    else resolveComposeColor(value, fallback, value.source)
                } ?: if (name == "surfaceTint") EtsLiteral(null, EtsTypes.NULL, at) else fallback
            }
            return EtsCast(EtsNew(materialColorValuesType, values, at), materialColorSchemeType, at)
        }
        val property = owner.correspondingPropertySymbol?.owner ?: return null
        val parent = property.parent as? IrClass ?: return null
        if (symbolName(parent) != "androidx.compose.material3.ColorScheme" ||
            property.getter?.symbol != owner.symbol || property.name.asString() !in materialColorSchemeDefaults) return null
        val receiver = call.dispatchReceiver ?: return null
        return EtsMember(language.expression(receiver, scope), property.name.asString(), EtsTypes.NUMBER, at)
    }
}

private fun materialColorSchemeFile(): EtsFile {
    val at = materialColorSchemeSource
    val parameters = materialColorSchemeDefaults.keys.zip(materialColorSchemeParameters).map { (name, type) ->
        EtsParameter(EtsSymbol("material:colorScheme:parameter:$name", name, type, at))
    }
    val receiver = EtsReference(EtsSymbol("material:colorScheme:this", "this", materialColorValuesType, at, external = true))
    val fields = materialColorSchemeDefaults.keys.map { name ->
        EtsField(EtsSymbol("material:colorScheme:field:$name", name, EtsTypes.NUMBER, at), readonly = true)
    }
    val body = fields.zip(parameters).map { (field, parameter) ->
        val argument = EtsReference(parameter.symbol)
        val value = if (field.symbol.name == "surfaceTint")
            EtsBinary("??", argument, EtsReference(parameters.first().symbol), EtsTypes.NUMBER, at) else argument
        EtsExpressionStatement(EtsAssignment(EtsMember(receiver, field.symbol.name, EtsTypes.NUMBER, at,
            field.symbol.id), value, at))
    }
    val constructor = EtsFunction("constructor", parameters, EtsTypes.VOID, body, at, kind = EtsFunctionKind.CONSTRUCTOR)
    return EtsFile(at.file!!, listOf(
        EtsClass(materialColorSchemeType.name, fields, at, exported = true, kind = EtsClassKind.INTERFACE),
        EtsClass(materialColorValuesType.name, fields + constructor, at, exported = true, interfaces = listOf(materialColorSchemeType))))
}

/** Include the value type even in files that only receive/return it. */
internal fun materialColorSchemeUsed(program: EtsProgram): Boolean {
    var used = false
    fun type(value: EtsType) {
        when (value) {
            is EtsNamedType -> {
                if (value.symbolId in setOf(materialColorSchemeType.symbolId, materialColorValuesType.symbolId)) {
                    require(value == materialColorSchemeType || value == materialColorValuesType) { "Malformed Material ColorScheme type" }
                    used = true
                }
                value.arguments.forEach(::type)
            }
            is EtsFunctionType -> { value.parameters.forEach(::type); type(value.result); value.typeParameters.forEach { it.upperBound?.let(::type) } }
            is EtsNullableType -> type(value.inner)
            is EtsTupleType -> value.elements.forEach(::type)
            is EtsRecordType -> value.fields.values.forEach(::type)
            is EtsCapturedType -> { type(value.readType); type(value.writeType) }
            is EtsTypeParameterType -> Unit
        }
    }
    program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
        if (node is EtsExpression) type(node.type)
        when (node) {
            is EtsFunction -> type(node.symbol.type)
            is EtsVariable -> type(node.symbol.type)
            is EtsGlobal -> type(node.symbol.type)
            is EtsField -> type(node.symbol.type)
            is EtsClass -> node.typeParameters.forEach { it.upperBound?.let(::type) }
            else -> Unit
        }
    } } }
    return used
}
