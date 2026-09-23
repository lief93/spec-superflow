@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

private val drawSource = SourceSpan("ComposeDrawGeometry.kt", -1, -1)
private val drawSizeType = etsClassSymbol("ComposeDrawSize", drawSource).type as EtsNamedType
private val drawOffsetType = etsClassSymbol("ComposeDrawOffset", drawSource).type as EtsNamedType
private val drawScopeType = etsClassSymbol("ComposeDrawScope", drawSource).type as EtsNamedType

private fun drawSize(width: EtsExpression, height: EtsExpression, at: SourceSpan) =
    EtsNew(drawSizeType, listOf(width, height), at)
private fun drawOffset(x: EtsExpression, y: EtsExpression, at: SourceSpan) =
    EtsNew(drawOffsetType, listOf(x, y), at)
private fun drawScope(size: EtsExpression, at: SourceSpan) = EtsNew(drawScopeType, listOf(size), at)

/** Target geometry values shared by Canvas and other drawing adapters. */
internal class ComposeDrawGeometryRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        if (sourceFile(owner) != null) return null
        return when (symbolName(owner)) {
            "androidx.compose.ui.graphics.drawscope.DrawScope" -> drawScopeType
            "androidx.compose.ui.geometry.Size" -> drawSizeType
            "androidx.compose.ui.geometry.Offset" -> drawOffsetType
            else -> null
        }
    }

    override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner.parent as? IrClass ?: return null
        if (sourceFile(owner) != null || symbolName(owner) != "androidx.compose.ui.geometry.Offset") return null
        val x = argument(call, "x") ?: return null
        val y = argument(call, "y") ?: return null
        return drawOffset(language.expression(x, scope), language.expression(y, scope), language.source(call))
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        if (symbolName(owner) == "androidx.compose.ui.geometry.Offset") {
            val x = argument(call, "x") ?: return null
            val y = argument(call, "y") ?: return null
            return drawOffset(language.expression(x, scope), language.expression(y, scope), language.source(call))
        }
        if (symbolName(owner) !in setOf("androidx.compose.ui.geometry.Size.<get-width>",
                "androidx.compose.ui.geometry.Size.<get-height>")) return null
        val name = owner.correspondingPropertySymbol?.owner?.name?.asString() ?: return null
        return EtsMember(language.expression(call.dispatchReceiver!!, scope), name, EtsTypes.NUMBER,
            language.source(call))
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        val drawTypes = setOf(drawSizeType, drawOffsetType, drawScopeType)
        var required = false
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
            fun uses(type: EtsType): Boolean = when (type) {
                is EtsNamedType -> type in drawTypes || type.arguments.any(::uses)
                is EtsFunctionType -> type.parameters.any(::uses) || uses(type.result)
                is EtsNullableType -> uses(type.inner)
                else -> false
            }
            if (node is EtsExpression && uses(node.type)) required = true
            if (node is EtsFunction && uses(node.symbol.type)) required = true
            if (node is EtsField && uses(node.symbol.type)) required = true
        } } }
        if (!required) return emptyList()
        fun valueClass(type: EtsNamedType, fields: List<Pair<String, EtsType>>): EtsClass {
            val self = EtsReference(EtsSymbol("draw:${type.name}:this", "this", type, drawSource, true))
            val targetFields = fields.map { (name, fieldType) ->
                EtsField(EtsSymbol("draw:${type.name}:$name", name, fieldType, drawSource), readonly = true)
            }
            val parameters = targetFields.map { EtsParameter(it.symbol.copy(id = it.symbol.id + ":parameter")) }
            val body = targetFields.zip(parameters).map { (field, parameter) -> EtsExpressionStatement(EtsAssignment(
                EtsMember(self, field.symbol.name, field.symbol.type, drawSource, field.symbol.id),
                EtsReference(parameter.symbol), drawSource)) }
            return EtsClass(type.name, targetFields + EtsFunction("constructor", parameters, EtsTypes.VOID,
                body, drawSource, kind = EtsFunctionKind.CONSTRUCTOR), drawSource,
                exported = true, valueSnapshot = true)
        }
        return listOf(EtsFile(drawSource.file!!, listOf(
            valueClass(drawSizeType, listOf("width" to EtsTypes.NUMBER, "height" to EtsTypes.NUMBER)),
            valueClass(drawOffsetType, listOf("x" to EtsTypes.NUMBER, "y" to EtsTypes.NUMBER)),
            valueClass(drawScopeType, listOf("size" to drawSizeType)),
        )))
    }
}

/** Basic DrawScope primitives represented with native ArkUI shape controls. */
internal class ComposeDrawScopeRule(
    private val target: ArkUiCalls,
    private val width: IrExpression,
    private val height: IrExpression,
) : CallRule {
    fun scopeValue(language: Language, scope: Scope): EtsExpression {
        val at = language.source(width)
        val targetWidth = requireSpecifiedDp(language.expression(width, scope), at, "Canvas width")
        val targetHeight = requireSpecifiedDp(language.expression(height, scope), language.source(height), "Canvas height")
        return drawScope(drawSize(targetWidth, targetHeight, at), at)
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val at = language.source(call)
        return when (symbolName(owner)) {
            "androidx.compose.ui.graphics.drawscope.DrawScope.<get-size>" -> {
                val receiver = call.dispatchReceiver ?: call.extensionReceiver ?: return null
                EtsMember(language.expression(receiver, scope), "size", drawSizeType, at)
            }
            else -> null
        }
    }

    override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
        if (sourceFile(call.symbol.owner) != null ||
            symbolName(call.symbol.owner) != "androidx.compose.ui.graphics.drawscope.DrawScope.drawCircle") return null
        target.checkArguments(call, setOf("color", "radius", "center", "alpha", "style", "colorFilter", "blendMode"))
        listOf("style", "colorFilter", "blendMode").forEach { name ->
            if (argument(call, name) != null) target.diagnostics.unsupported(call,
                "DrawScope.drawCircle $name is not supported by the native shape projection")
        }
        val colorSource = argument(call, "color") ?: target.diagnostics.unsupported(call, "drawCircle requires color")
        val radiusSource = argument(call, "radius") ?: target.diagnostics.unsupported(call, "drawCircle requires radius")
        val centerSource = argument(call, "center") ?: target.diagnostics.unsupported(call, "drawCircle requires center")
        val color = requireSpecifiedColor(language.expression(colorSource, scope), language.source(colorSource),
            "DrawScope.drawCircle color")
        val radius = language.expression(radiusSource, scope)
        if (radius.type != EtsTypes.NUMBER) target.diagnostics.unsupported(radiusSource, "drawCircle radius requires number")
        val center = language.expression(centerSource, scope)
        if (center.type != drawOffsetType) target.diagnostics.unsupported(centerSource, "drawCircle center requires Offset")
        val at = language.source(call)
        val diameter = EtsBinary("*", radius, EtsLiteral(2, EtsTypes.NUMBER, at), EtsTypes.NUMBER, at)
        fun coordinate(name: String) = EtsBinary("-", EtsMember(center, name, EtsTypes.NUMBER, at), radius,
            EtsTypes.NUMBER, at)
        val attributes = mutableListOf(
            target.attribute("width", listOf(diameter), call),
            target.attribute("height", listOf(diameter), call),
            target.attribute("fill", listOf(color), call),
            target.attribute("position", listOf(target.record("Position", linkedMapOf(
                "x" to coordinate("x"), "y" to coordinate("y")), call)), call),
        )
        argument(call, "alpha")?.let {
            attributes += target.attribute("opacity", listOf(language.expression(it, scope)), call)
        }
        return listOf(target.native("Circle", emptyList(), call).copy(attributes = attributes))
    }
}

internal class ComposeCanvasRule(
    private val target: ArkUiCalls,
    private val size: (IrExpression?, Scope) -> Pair<IrExpression, IrExpression>,
    private val content: (IrExpression, Scope, ComposeDrawScopeRule) -> List<EtsStatement>,
    private val decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null

    override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
        if (symbolName(call.symbol.owner) != "androidx.compose.foundation.Canvas") return null
        target.checkArguments(call, setOf("modifier", "onDraw"))
        val modifier = argument(call, "modifier")
        val (width, height) = size(modifier, scope)
        val drawRule = ComposeDrawScopeRule(target, width, height)
        val body = argument(call, "onDraw") ?: target.diagnostics.unsupported(call, "Canvas requires onDraw")
        val element = ComposeElement(target.native("Stack", listOf(target.stackOptions(call)), call,
            content(body, scope, drawRule)))
        return decorate(modifier, scope, element)
    }
}
