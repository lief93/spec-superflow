@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import dev.ets.widgets.*
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.parentAsClass
import org.jetbrains.kotlin.ir.visitors.*

private val shapeSource = SourceSpan("EtsShape.kt", -1, -1)
internal val shapeType = etsClassSymbol("EtsShape", shapeSource).type as EtsNamedType
internal val materialShapesType = etsClassSymbol("EtsMaterialShapes", shapeSource).type as EtsNamedType
internal val pathShapeType = EtsNamedType("__etsPathShape", symbolId = "arkui:PathShape", external = true)
private val shapeSlots = listOf("extraSmall", "small", "medium", "large", "extraLarge")

private fun defaultShapeValues(at: SourceSpan) = ThemeShapes(
    rounded(4.0, at), rounded(8.0, at), rounded(12.0, at), rounded(16.0, at), rounded(28.0, at), at)

private fun rounded(value: Double, at: SourceSpan) = CornerShape(CornerShapeKind.ROUNDED,
    value, value, value, value, at)

private fun shapeValue(value: CornerShape<Double, SourceSpan>, at: SourceSpan): EtsExpression = EtsNew(shapeType, listOf(
    EtsLiteral(value.kind.name.lowercase(), EtsTypes.STRING, at),
    EtsLiteral(value.topStart, EtsTypes.NUMBER, at), EtsLiteral(value.topEnd, EtsTypes.NUMBER, at),
    EtsLiteral(value.bottomEnd, EtsTypes.NUMBER, at), EtsLiteral(value.bottomStart, EtsTypes.NUMBER, at)), at)

private fun shapesValue(value: ThemeShapes<Double, SourceSpan>, at: SourceSpan): EtsExpression =
    EtsNew(materialShapesType, listOf(value.extraSmall, value.small, value.medium, value.large, value.extraLarge)
        .map { shapeValue(it, at) }, at)

internal fun materialShapes(context: EtsExpression, at: SourceSpan): EtsExpression {
    if (context is EtsNew && context.classType == materialContextType && context.arguments.size >= 4)
        return context.arguments[3]
    return EtsMember(context, "shapes", materialShapesType, at)
}

/** Converts a proven rounded/circle Shape into ArkUI's legal radius parameter. */
private fun arkBorderRadius(value: EtsExpression, owner: IrElement, diagnostics: DiagnosticSink,
    sourceKind: CornerShapeKind?): EtsExpression {
    fun shape(expression: EtsExpression): EtsNew? = when (expression) {
        is EtsNew -> expression.takeIf { it.classType == shapeType }
        is EtsMember -> {
            val container = expression.receiver as? EtsNew
            if (container?.classType != materialShapesType) null
            else container.arguments.getOrNull(shapeSlots.indexOf(expression.name))?.let(::shape)
        }
        else -> null
    }
    val concrete = shape(value)
    val kind = sourceKind?.name?.lowercase() ?: (concrete?.arguments?.firstOrNull() as? EtsLiteral)?.value as? String
    if (kind == CornerShapeKind.CUT.name.lowercase()) diagnostics.unsupported(owner,
        "CutCornerShape cannot be represented by a size-independent ArkUI component shape")
    if (kind == CornerShapeKind.CIRCLE.name.lowercase())
        return EtsLiteral("50%", EtsTypes.STRING, value.source)
    val fields = listOf("topLeft" to "topStart", "topRight" to "topEnd",
        "bottomRight" to "bottomEnd", "bottomLeft" to "bottomStart")
    val corners = linkedMapOf<String, EtsExpression>()
    fields.forEachIndexed { index, (target, source) -> corners[target] =
        concrete?.arguments?.getOrNull(index + 1) ?: EtsMember(value, source, EtsTypes.NUMBER, value.source) }
    return EtsObject(corners, EtsRecordType("BorderRadiuses", corners.mapValues { EtsTypes.NUMBER }), value.source)
}

/** Resolved static Material3 Shape semantics, including providers outside the selected page closure. */
internal class ComposeShapeRule : CallRule {
    private data class Binding(val shapes: ThemeShapes<Double, SourceSpan>?, val failure: Diagnostic?, val at: SourceSpan)
    private val bindings = mutableListOf<Binding>()
    private data class SourceCall(val call: IrCall, val root: IrDeclaration)
    private val sourceCalls = mutableListOf<SourceCall>()

    override fun prepareModule(module: IrModuleFragment, diagnostics: DiagnosticSink) {
        bindings.clear()
        sourceCalls.clear()
        module.files.forEach { file ->
            val previous = diagnostics.currentFile
            diagnostics.currentFile = file.fileEntry.name
            try {
                file.declarations.forEach { root ->
                    root.acceptVoid(object : IrElementVisitorVoid {
                        override fun visitElement(element: IrElement) {
                            if (element is IrCall && sourceFile(element.symbol.owner) != null)
                                sourceCalls += SourceCall(element, root)
                            if (element is IrCall && sourceFile(element.symbol.owner) == null &&
                                symbolName(element.symbol.owner) == "androidx.compose.material3.MaterialTheme") {
                                argument(element, "shapes")?.let { expression ->
                                    val at = sourceSpan(expression, diagnostics)
                                    bindings += try { Binding(staticShapes(expression, diagnostics), null, at) }
                                    catch (failure: Unsupported) { Binding(null, failure.diagnostic, at) }
                                }
                            }
                            element.acceptChildrenVoid(this)
                        }
                    })
                }
            } finally { diagnostics.currentFile = previous }
        }
    }

    fun initialShapes(at: SourceSpan): EtsExpression {
        return shapesValue(selectedShapes(at), at)
    }

    fun borderRadius(source: IrExpression, language: Language, scope: Scope,
        diagnostics: DiagnosticSink): EtsExpression {
        val kind = sourceKind(source, diagnostics)
        return arkBorderRadius(language.expression(source, scope), source, diagnostics, kind)
    }

    fun themeBorderRadius(name: String, context: EtsExpression, owner: IrElement,
        diagnostics: DiagnosticSink): EtsExpression {
        val at = sourceSpan(owner, diagnostics)
        val value = EtsMember(materialShapes(context, at), name, shapeType, at)
        return arkBorderRadius(value, owner, diagnostics, slot(selectedShapes(at), name).kind)
    }

    fun cutClip(source: IrExpression, width: EtsExpression?, height: EtsExpression?,
        diagnostics: DiagnosticSink): EtsExpression? {
        if (sourceKind(source, diagnostics) != CornerShapeKind.CUT) return null
        val widthValue = ((width as? EtsLiteral)?.value as? Number)?.toDouble()
        val heightValue = ((height as? EtsLiteral)?.value as? Number)?.toDouble()
        if (widthValue == null || heightValue == null || widthValue <= 0.0 || heightValue <= 0.0)
            diagnostics.unsupported(source, "CutCornerShape requires statically known positive component width and height")
        val shape = sourceShape(source, diagnostics)
        val scale = minOf(1.0,
            ratio(widthValue, shape.topStart + shape.topEnd),
            ratio(widthValue, shape.bottomStart + shape.bottomEnd),
            ratio(heightValue, shape.topStart + shape.bottomStart),
            ratio(heightValue, shape.topEnd + shape.bottomEnd))
        val topStart = shape.topStart * scale
        val topEnd = shape.topEnd * scale
        val bottomEnd = shape.bottomEnd * scale
        val bottomStart = shape.bottomStart * scale
        fun number(value: Double): String = if (value % 1.0 == 0.0) value.toLong().toString() else value.toString()
        val commands = "M ${number(topStart)} 0 H ${number(widthValue - topEnd)} L ${number(widthValue)} ${number(topEnd)} " +
            "V ${number(heightValue - bottomEnd)} L ${number(widthValue - bottomEnd)} ${number(heightValue)} " +
            "H ${number(bottomStart)} L 0 ${number(heightValue - bottomStart)} V ${number(topStart)} Z"
        val at = sourceSpan(source, diagnostics)
        val options = EtsObject(mapOf("commands" to EtsLiteral(commands, EtsTypes.STRING, at)),
            EtsRecordType("PathShapeOptions", mapOf("commands" to EtsTypes.STRING)), at)
        return EtsNew(pathShapeType, listOf(options), at)
    }

    private fun ratio(size: Double, corners: Double): Double = if (corners == 0.0) 1.0 else size / corners

    private fun selectedShapes(at: SourceSpan): ThemeShapes<Double, SourceSpan> {
        bindings.firstOrNull { it.failure != null }?.failure?.let { throw Unsupported(it) }
        val values = bindings.map { requireNotNull(it.shapes) }.distinctBy(::signature)
        if (values.size > 1) throw Unsupported(Diagnostic("UNSUPPORTED",
            "Multiple distinct project MaterialTheme shapes bindings are ambiguous for this page", bindings[1].at))
        return values.singleOrNull() ?: defaultShapeValues(at)
    }

    private fun sourceKind(source: IrExpression, diagnostics: DiagnosticSink): CornerShapeKind {
        val resolved = staticReference(source) ?: diagnostics.unsupported(source, "Runtime Shape selection is unsupported")
        val call = resolved as? IrCall
        val api = call?.symbol?.owner?.let(::symbolName)
        val property = call?.symbol?.owner?.correspondingPropertySymbol?.owner
        return when {
            api == "androidx.compose.foundation.shape.RoundedCornerShape" -> CornerShapeKind.ROUNDED
            api == "androidx.compose.foundation.shape.CutCornerShape" -> CornerShapeKind.CUT
            property?.let(::symbolName) == "androidx.compose.foundation.shape.CircleShape" -> CornerShapeKind.CIRCLE
            property?.let(::symbolName) == "androidx.compose.ui.graphics.RectangleShape" -> CornerShapeKind.ROUNDED
            (property?.parent as? IrClass)?.let(::symbolName) == "androidx.compose.material3.Shapes" &&
                property.name.asString() in shapeSlots -> slot(selectedShapes(sourceSpan(source, diagnostics)), property.name.asString()).kind
            resolved is IrGetValue && resolved.symbol.owner is IrValueParameter -> {
                val parameter = resolved.symbol.owner as IrValueParameter
                val function = parameter.parent as IrFunction
                val index = function.valueParameters.indexOf(parameter)
                val kinds = sourceCalls.filter { it.call.symbol.owner == function &&
                    sourceFile(it.root)?.declarations?.contains(it.root) == true }.map { sourceCall ->
                    val argument = sourceCall.call.getValueArgument(index) ?: diagnostics.unsupported(source,
                        "Shape parameter requires a static source argument")
                    sourceKind(argument, diagnostics)
                }
                if (kinds.isEmpty()) diagnostics.unsupported(source,
                    "Shape parameter requires statically provable source call sites")
                if (CornerShapeKind.CUT in kinds) CornerShapeKind.CUT else CornerShapeKind.ROUNDED
            }
            else -> diagnostics.unsupported(source, "Custom or arbitrary Shape implementations are unsupported")
        }
    }

    private fun sourceShape(source: IrExpression, diagnostics: DiagnosticSink): CornerShape<Double, SourceSpan> {
        val resolved = staticReference(source) ?: diagnostics.unsupported(source, "Runtime Shape selection is unsupported")
        if (resolved is IrGetValue && resolved.symbol.owner is IrValueParameter) {
            val parameter = resolved.symbol.owner as IrValueParameter
            val function = parameter.parent as IrFunction
            val index = function.valueParameters.indexOf(parameter)
            val values = sourceCalls.filter { it.call.symbol.owner == function &&
                sourceFile(it.root)?.declarations?.contains(it.root) == true }.map { sourceCall ->
                val argument = sourceCall.call.getValueArgument(index) ?: diagnostics.unsupported(source,
                    "Shape parameter requires a static source argument")
                staticShape(argument, diagnostics)
            }.distinctBy { listOf(it.kind, it.topStart, it.topEnd, it.bottomEnd, it.bottomStart) }
            return values.singleOrNull() ?: diagnostics.unsupported(source,
                "Shape parameter requires one statically provable corner shape")
        }
        val call = resolved as? IrCall
        val property = call?.symbol?.owner?.correspondingPropertySymbol?.owner
        if ((property?.parent as? IrClass)?.let(::symbolName) == "androidx.compose.material3.Shapes" &&
            property.name.asString() in shapeSlots)
            return slot(selectedShapes(sourceSpan(source, diagnostics)), property.name.asString())
        return staticShape(source, diagnostics)
    }

    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        if (sourceFile(owner) != null) return null
        return when (symbolName(owner)) {
            "androidx.compose.material3.Shapes" -> materialShapesType
            "androidx.compose.ui.graphics.Shape", "androidx.compose.foundation.shape.CornerBasedShape",
            "androidx.compose.foundation.shape.RoundedCornerShape", "androidx.compose.foundation.shape.CutCornerShape" -> shapeType
            else -> null
        }
    }

    override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? {
        if (sourceFile(call.symbol.owner) != null || symbolName(call.symbol.owner.parentAsClass) != "androidx.compose.material3.Shapes") return null
        val defaults = defaultShapeValues(language.source(call))
        val values = shapeSlots.map { name -> argument(call, name)?.let { language.expression(it, scope) }
            ?: shapeValue(slot(defaults, name), language.source(call)) }
        return EtsNew(materialShapesType, values, language.source(call))
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val function = call.symbol.owner
        if (sourceFile(function) != null) return null
        val at = language.source(call)
        val api = symbolName(function)
        if (api in setOf("androidx.compose.foundation.shape.RoundedCornerShape",
                "androidx.compose.foundation.shape.CutCornerShape")) {
            val kind = if (api.endsWith("CutCornerShape")) CornerShapeKind.CUT else CornerShapeKind.ROUNDED
            val values = cornerArguments(call, at, { EtsLiteral(0, EtsTypes.NUMBER, at) }) {
                expression -> language.expression(expression, scope)
            }
            return EtsNew(shapeType, listOf(EtsLiteral(kind.name.lowercase(), EtsTypes.STRING, at)) + values, at)
        }
        val property = function.correspondingPropertySymbol?.owner ?: return null
        if (property.getter?.symbol != function.symbol) return null
        val propertyName = symbolName(property)
        if ((property.parent as? IrClass)?.let(::symbolName) == "androidx.compose.material3.Shapes" &&
            property.name.asString() in shapeSlots) {
            val receiver = call.dispatchReceiver ?: return null
            return EtsMember(language.expression(receiver, scope), property.name.asString(), shapeType, at)
        }
        return when (propertyName) {
            "androidx.compose.foundation.shape.CircleShape" -> shapeValue(CornerShape(CornerShapeKind.CIRCLE,
                999999.0, 999999.0, 999999.0, 999999.0, at), at)
            "androidx.compose.ui.graphics.RectangleShape" -> shapeValue(rounded(0.0, at), at)
            else -> null
        }
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        var used = false
        fun type(value: EtsType) {
            when (value) {
                is EtsNamedType -> { if (value.symbolId in setOf(shapeType.symbolId, materialShapesType.symbolId)) used = true; value.arguments.forEach(::type) }
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
        return if (used) listOf(shapeFile()) else emptyList()
    }

    override fun targetImports(program: EtsProgram): List<EtsImport> {
        var used = false
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) {
            if (it is EtsNew && it.classType == pathShapeType) used = true
        } } }
        return if (used) listOf(EtsImport("@kit.ArkUI", "PathShape", pathShapeType.name)) else emptyList()
    }

    private fun <V> cornerArguments(call: IrCall, at: SourceSpan, zero: () -> V,
        lower: (IrExpression) -> V): List<V> {
        val parameters = call.symbol.owner.valueParameters
        val dp = "androidx.compose.ui.unit.Dp"
        if (parameters.size == 1 && parameters.single().type.classFqName?.asString() == dp) {
            val value = call.getValueArgument(0) ?: throw Unsupported(Diagnostic("UNSUPPORTED",
                "Corner shape requires a static Dp size", at))
            return List(4) { lower(value) }
        }
        val names = listOf("topStart", "topEnd", "bottomEnd", "bottomStart")
        if (parameters.map { it.name.asString() } == names && parameters.all { it.type.classFqName?.asString() == dp }) {
            return names.map { name -> argument(call, name)?.let(lower) ?: zero() }
        }
        throw Unsupported(Diagnostic("UNSUPPORTED", "Percentage corner sizes are unsupported", at))
    }

    private fun staticShapes(expression: IrExpression, diagnostics: DiagnosticSink): ThemeShapes<Double, SourceSpan> {
        val resolved = staticReference(expression) ?: diagnostics.unsupported(expression,
            "Runtime MaterialTheme shapes selection is unsupported")
        val call = resolved as? IrConstructorCall
            ?: diagnostics.unsupported(expression, "MaterialTheme shapes requires a static Shapes constructor")
        if (sourceFile(call.symbol.owner) != null || symbolName(call.symbol.owner.parentAsClass) != "androidx.compose.material3.Shapes")
            diagnostics.unsupported(expression, "MaterialTheme shapes requires a static Shapes constructor")
        val at = sourceSpan(expression, diagnostics)
        val defaults = defaultShapeValues(at)
        val values = shapeSlots.associateWith { name ->
            argument(call, name)?.let { staticShape(it, diagnostics) } ?: slot(defaults, name)
        }
        return ThemeShapes(values.getValue("extraSmall"), values.getValue("small"), values.getValue("medium"),
            values.getValue("large"), values.getValue("extraLarge"), at)
    }

    private fun staticShape(expression: IrExpression, diagnostics: DiagnosticSink): CornerShape<Double, SourceSpan> {
        val resolved = staticReference(expression) ?: diagnostics.unsupported(expression,
            "Runtime Shape selection is unsupported")
        if (resolved is IrCall && sourceFile(resolved.symbol.owner) == null) {
            val api = symbolName(resolved.symbol.owner)
            if (api in setOf("androidx.compose.foundation.shape.RoundedCornerShape",
                    "androidx.compose.foundation.shape.CutCornerShape")) {
                val values = try { cornerArguments(resolved, sourceSpan(resolved, diagnostics), { 0.0 }) { staticDp(it, diagnostics) } }
                    catch (failure: Unsupported) { throw Unsupported(failure.diagnostic.copy(source = sourceSpan(expression, diagnostics))) }
                val kind = if (api.endsWith("CutCornerShape")) CornerShapeKind.CUT else CornerShapeKind.ROUNDED
                return CornerShape(kind, values[0], values[1], values[2], values[3], sourceSpan(expression, diagnostics))
            }
            val property = resolved.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName)
            if (property == "androidx.compose.foundation.shape.CircleShape") return CornerShape(CornerShapeKind.CIRCLE,
                999999.0, 999999.0, 999999.0, 999999.0, sourceSpan(expression, diagnostics))
            if (property == "androidx.compose.ui.graphics.RectangleShape") return rounded(0.0, sourceSpan(expression, diagnostics))
        }
        diagnostics.unsupported(expression, "Custom or arbitrary Shape implementations are unsupported")
    }

    private fun staticDp(expression: IrExpression, diagnostics: DiagnosticSink): Double {
        val resolved = staticReference(expression) ?: expression
        if (resolved is IrCall && resolved.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName) ==
            "androidx.compose.ui.unit.dp") {
            val receiver = resolved.extensionReceiver ?: resolved.dispatchReceiver
                ?: diagnostics.unsupported(expression, "Static corner size requires Dp")
            val number = (staticReference(receiver) as? IrConst)?.value as? Number
                ?: diagnostics.unsupported(expression, "Static corner size requires a numeric Dp literal")
            val value = number.toDouble()
            if (!value.isFinite() || value < 0.0) diagnostics.unsupported(expression,
                "Corner size must be finite and non-negative")
            return value.toFloat().toDouble()
        }
        diagnostics.unsupported(expression, "Static corner size requires a numeric Dp literal")
    }

    private fun staticReference(expression: IrExpression): IrExpression? = when (expression) {
        is IrGetValue -> (expression.symbol.owner as? IrVariable)?.takeUnless { it.isVar }?.initializer?.let(::staticReference)
            ?: expression
        is IrGetField -> expression.symbol.owner.initializer?.expression?.let(::staticReference) ?: expression
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

    private fun signature(value: ThemeShapes<Double, SourceSpan>) = shapeSlots.joinToString("|") { name ->
        val shape = slot(value, name)
        listOf(shape.kind, shape.topStart, shape.topEnd, shape.bottomEnd, shape.bottomStart).joinToString(":")
    }
}

private fun <V, S> slot(value: ThemeShapes<V, S>, name: String): CornerShape<V, S> = when (name) {
    "extraSmall" -> value.extraSmall; "small" -> value.small; "medium" -> value.medium
    "large" -> value.large; "extraLarge" -> value.extraLarge; else -> error("Unknown Shapes slot: $name")
}

private fun shapeFile(): EtsFile {
    val at = shapeSource
    fun clazz(type: EtsNamedType, values: LinkedHashMap<String, EtsType>): EtsClass {
        val self = EtsReference(EtsSymbol("shape:${type.name}:this", "this", type, at, external = true))
        val parameters = values.map { (name, fieldType) -> EtsParameter(EtsSymbol("shape:${type.name}:parameter:$name", name, fieldType, at)) }
        val fields = values.map { (name, fieldType) -> EtsField(EtsSymbol("shape:${type.name}:field:$name", name, fieldType, at), readonly = true) }
        val constructor = EtsFunction("constructor", parameters, EtsTypes.VOID, fields.zip(parameters).map { (field, parameter) ->
            EtsExpressionStatement(EtsAssignment(EtsMember(self, field.symbol.name, field.symbol.type, at, field.symbol.id),
                EtsReference(parameter.symbol), at))
        }, at, kind = EtsFunctionKind.CONSTRUCTOR)
        return EtsClass(type.name, fields + constructor, at, exported = true, valueSnapshot = true)
    }
    return EtsFile(at.file!!, listOf(
        clazz(shapeType, linkedMapOf("kind" to EtsTypes.STRING, "topStart" to EtsTypes.NUMBER,
            "topEnd" to EtsTypes.NUMBER, "bottomEnd" to EtsTypes.NUMBER, "bottomStart" to EtsTypes.NUMBER)),
        clazz(materialShapesType, linkedMapOf(*shapeSlots.map { it to shapeType }.toTypedArray()))))
}
