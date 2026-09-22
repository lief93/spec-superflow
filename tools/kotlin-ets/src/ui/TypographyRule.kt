@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

private val typographySource = SourceSpan("EtsTypography.kt", -1, -1)
internal val typographyType = etsClassSymbol("EtsTypography", typographySource).type as EtsNamedType
// AndroidX Material3 1.3.2 TypeScaleTokens: size, line height, weight, tracking.
private val typographyDefaults = linkedMapOf(
    "displayLarge" to listOf(57, 64, 400, -0.2), "displayMedium" to listOf(45, 52, 400, 0),
    "displaySmall" to listOf(36, 44, 400, 0), "headlineLarge" to listOf(32, 40, 400, 0),
    "headlineMedium" to listOf(28, 36, 400, 0), "headlineSmall" to listOf(24, 32, 400, 0),
    "titleLarge" to listOf(22, 28, 400, 0), "titleMedium" to listOf(16, 24, 500, 0.2),
    "titleSmall" to listOf(14, 20, 500, 0.1), "bodyLarge" to listOf(16, 24, 400, 0.5),
    "bodyMedium" to listOf(14, 20, 400, 0.2), "bodySmall" to listOf(12, 16, 400, 0.4),
    "labelLarge" to listOf(14, 20, 500, 0.1), "labelMedium" to listOf(12, 16, 500, 0.5),
    "labelSmall" to listOf(11, 16, 500, 0.5))

internal fun defaultTypographyRole(name: String, at: SourceSpan): EtsExpression {
    val values = listOf("fontSize", "lineHeight", "fontWeight", "letterSpacing").zip(typographyDefaults.getValue(name)).toMap()
    return EtsNew(textStyleType, textStyleFields.keys.map { field ->
        values[field]?.let { EtsLiteral(it, EtsTypes.NUMBER, at) } ?: EtsLiteral(null, EtsTypes.NULL, at)
    }, at)
}
internal fun defaultTypography(at: SourceSpan) = EtsNew(typographyType, typographyDefaults.keys.map { defaultTypographyRole(it, at) }, at)
internal fun materialTypography(context: EtsExpression, at: SourceSpan) = EtsMember(context, "typography", typographyType, at)

internal class ComposeTypographyRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? = type.classOrNull?.owner?.let {
        if (sourceFile(it) == null && symbolName(it) == "androidx.compose.material3.Typography") typographyType else null
    }
    override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner.parent as IrClass
        if (sourceFile(owner) != null || symbolName(owner) != "androidx.compose.material3.Typography") return null
        if (call.symbol.owner.valueParameters.map { it.name.asString() } != typographyDefaults.keys.toList())
            throw Unsupported(Diagnostic("UNSUPPORTED", "Unsupported Typography constructor signature", language.source(call)))
        return EtsNew(typographyType, typographyDefaults.keys.map { name ->
            argument(call, name)?.let { language.expression(it, scope) } ?: defaultTypographyRole(name, language.source(call))
        }, language.source(call))
    }
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val property = owner.correspondingPropertySymbol?.owner ?: return null
        if (property.getter?.symbol != owner.symbol || symbolName(property.parent as? IrClass ?: return null) != "androidx.compose.material3.Typography") return null
        val name = property.name.asString()
        if (name !in typographyDefaults) return null
        return EtsMember(language.expression(call.dispatchReceiver!!, scope), name, textStyleType, language.source(call))
    }
    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        var used = false
        fun type(value: EtsType) {
            when (value) {
                is EtsNamedType -> { if (value.symbolId == typographyType.symbolId) used = true; value.arguments.forEach(::type) }
                is EtsNullableType -> type(value.inner)
                is EtsFunctionType -> { value.parameters.forEach(::type); type(value.result) }
                is EtsRecordType -> value.fields.values.forEach(::type)
                is EtsTupleType -> value.elements.forEach(::type)
                is EtsCapturedType -> { type(value.readType); type(value.writeType) }
                is EtsTypeParameterType -> Unit
            }
        }
        program.files.forEach { it.declarations.forEach { d -> walkEts(d) { n ->
            if (n is EtsExpression) type(n.type)
            when (n) {
                is EtsFunction -> type(n.symbol.type)
                is EtsField -> type(n.symbol.type)
                is EtsGlobal -> type(n.symbol.type)
                is EtsVariable -> type(n.symbol.type)
                else -> Unit
            }
        } } }
        if (!used) return emptyList()
        val at = typographySource
        val self = EtsReference(EtsSymbol("typography:this", "this", typographyType, at, true))
        val fields = typographyDefaults.keys.map { EtsField(EtsSymbol("typography:field:$it", it, textStyleType, at), readonly = true) }
        val params = fields.map { EtsParameter(it.symbol.copy(id = it.symbol.id + ":parameter")) }
        val body = fields.zip(params).map { (field, parameter) -> EtsExpressionStatement(EtsAssignment(
            EtsMember(self, field.symbol.name, field.symbol.type, at, field.symbol.id), EtsReference(parameter.symbol), at)) }
        return listOf(EtsFile(at.file!!, listOf(EtsClass(typographyType.name, fields + EtsFunction("constructor", params,
            EtsTypes.VOID, body, at, kind = EtsFunctionKind.CONSTRUCTOR), at, exported = true))))
    }
}
