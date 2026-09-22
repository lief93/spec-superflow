@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import dev.ets.widgets.CardElevation
import org.jetbrains.kotlin.ir.declarations.IrVariable
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

private val cardElevationSource = SourceSpan("EtsCardElevation.kt", -1, -1)
internal val cardElevationType = etsClassSymbol("EtsCardElevation", cardElevationSource).type as EtsNamedType
private val cardDefaultsType = etsClassSymbol("EtsCardDefaults", cardElevationSource).type as EtsNamedType
private val cardDefaultsObject = EtsSymbol("material:cardDefaults", "__etsCardDefaults", cardDefaultsType, cardElevationSource)
private val elevationFields = listOf("defaultElevation", "pressedElevation", "focusedElevation",
    "hoveredElevation", "draggedElevation", "disabledElevation")
private val elevationDefaults = mapOf(
    "androidx.compose.material3.CardDefaults.cardElevation" to listOf(0.0, 0.0, 0.0, 1.0, 6.0, 0.0),
)

/** Resolves Material's six elevation states before the Harmony backend selects a static shadow. */
internal class ComposeCardElevationRule(private val diagnostics: DiagnosticSink) : CallRule {
    fun filledDefault(at: SourceSpan): CardElevation<Double, SourceSpan> =
        elevation(elevationDefaults.getValue("androidx.compose.material3.CardDefaults.cardElevation"), at)

    fun staticElevation(expression: IrExpression): CardElevation<Double, SourceSpan> {
        val resolved = staticReference(expression)
            ?: diagnostics.unsupported(expression, "Runtime CardElevation selection is unsupported")
        val call = resolved as? IrCall ?: diagnostics.unsupported(expression,
            "Card elevation must resolve to a static CardDefaults elevation factory")
        val api = symbolName(call.symbol.owner)
        val defaults = elevationDefaults[api] ?: diagnostics.unsupported(expression,
            "Card elevation must resolve to a static CardDefaults elevation factory")
        if (call.symbol.owner.valueParameters.map { it.name.asString() } != elevationFields)
            diagnostics.unsupported(expression, "Unsupported Material3 CardElevation factory signature")
        val values = elevationFields.mapIndexed { index, name ->
            argument(call, name)?.let(::staticDp) ?: defaults[index]
        }
        return elevation(values, sourceSpan(expression, diagnostics))
    }

    fun targetValue(value: CardElevation<Double, SourceSpan>, at: SourceSpan): EtsExpression =
        EtsNew(cardElevationType, listOf(value.default, value.pressed, value.focused,
            value.hovered, value.dragged, value.disabled).map { EtsLiteral(it, EtsTypes.NUMBER, at) }, at)

    fun defaultValue(value: EtsExpression, at: SourceSpan): EtsExpression =
        EtsMember(value, "defaultElevation", EtsTypes.NUMBER, at)

    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        return cardElevationType.takeIf {
            sourceFile(owner) == null && symbolName(owner) == "androidx.compose.material3.CardElevation"
        } ?: cardDefaultsType.takeIf {
            sourceFile(owner) == null && symbolName(owner) == "androidx.compose.material3.CardDefaults"
        }
    }

    override fun lowerObject(value: IrGetObjectValue, language: Language, scope: Scope): EtsExpression? =
        if (sourceFile(value.symbol.owner) == null && symbolName(value.symbol.owner) == "androidx.compose.material3.CardDefaults")
            EtsReference(cardDefaultsObject, language.source(value)) else null

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        if (sourceFile(call.symbol.owner) != null || symbolName(call.symbol.owner) !in elevationDefaults) return null
        val at = language.source(call)
        return targetValue(staticElevation(call), at)
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        var elevationUsed = false
        var defaultsUsed = false
        fun type(value: EtsType) {
            when (value) {
                is EtsNamedType -> {
                    if (value.symbolId == cardElevationType.symbolId) elevationUsed = true
                    if (value.symbolId == cardDefaultsType.symbolId) defaultsUsed = true
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
        if (!elevationUsed && !defaultsUsed) return emptyList()
        val file = cardElevationFile(elevationUsed, defaultsUsed)
        return listOf(file)
    }

    private fun staticDp(expression: IrExpression): Double {
        val resolved = staticReference(expression) ?: expression
        if (resolved is IrCall && resolved.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName) ==
            "androidx.compose.ui.unit.dp") {
            val receiver = resolved.extensionReceiver ?: resolved.dispatchReceiver
                ?: diagnostics.unsupported(expression, "Card elevation requires a static numeric Dp")
            val number = (staticReference(receiver) as? IrConst)?.value as? Number
                ?: diagnostics.unsupported(expression, "Card elevation requires a static numeric Dp")
            val value = number.toDouble()
            if (!value.isFinite() || value < 0.0)
                diagnostics.unsupported(expression, "Card elevation must be finite and non-negative")
            return value.toFloat().toDouble()
        }
        diagnostics.unsupported(expression, "Card elevation requires a static numeric Dp")
    }

    private fun staticReference(expression: IrExpression): IrExpression? = when (expression) {
        is IrGetValue -> {
            val owner = expression.symbol.owner as? IrVariable
            if (owner == null || owner.isVar || owner.initializer == null) expression
            else staticReference(owner.initializer!!)
        }
        is IrGetField -> {
            val initializer = expression.symbol.owner.initializer?.expression
            if (initializer == null) expression else staticReference(initializer)
        }
        is IrCall -> {
            val property = expression.symbol.owner.correspondingPropertySymbol?.owner
            if (sourceFile(expression.symbol.owner) != null && property?.getter?.symbol == expression.symbol)
                property.backingField?.initializer?.expression?.let(::staticReference)
            else expression
        }
        is IrTypeOperatorCall -> staticReference(expression.argument)
        is IrBlock -> (expression.statements.lastOrNull() as? IrExpression)?.let(::staticReference)
        is IrWhen -> null
        else -> expression
    }

    private fun elevation(values: List<Double>, at: SourceSpan) = CardElevation(
        values[0], values[1], values[2], values[3], values[4], values[5], at)
}

private fun cardElevationFile(elevation: Boolean, defaults: Boolean): EtsFile {
    val at = cardElevationSource
    val parameters = elevationFields.map { name ->
        EtsParameter(EtsSymbol("material:cardElevation:parameter:$name", name, EtsTypes.NUMBER, at))
    }
    val fields = elevationFields.map { name ->
        EtsField(EtsSymbol("material:cardElevation:field:$name", name, EtsTypes.NUMBER, at), readonly = true)
    }
    val self = EtsReference(EtsSymbol("material:cardElevation:this", "this", cardElevationType, at, external = true))
    val constructor = EtsFunction("constructor", parameters, EtsTypes.VOID, fields.zip(parameters).map { (field, parameter) ->
        EtsExpressionStatement(EtsAssignment(EtsMember(self, field.symbol.name, field.symbol.type, at, field.symbol.id),
            EtsReference(parameter.symbol), at))
    }, at, kind = EtsFunctionKind.CONSTRUCTOR)
    val declarations = mutableListOf<EtsDeclaration>()
    if (elevation) declarations += EtsClass(cardElevationType.name, fields + constructor, at,
        exported = true, valueSnapshot = true)
    if (defaults) {
        declarations += EtsClass(cardDefaultsType.name, listOf(EtsFunction("constructor", emptyList(), EtsTypes.VOID,
            emptyList(), at, kind = EtsFunctionKind.CONSTRUCTOR)), at, exported = true)
        declarations += EtsGlobal(cardDefaultsObject, EtsNew(cardDefaultsType, emptyList(), at), false, exported = true)
    }
    return EtsFile(at.file!!, declarations)
}
