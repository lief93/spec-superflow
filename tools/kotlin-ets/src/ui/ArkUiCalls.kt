@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrExpression

/** Typed target API construction shared by Compose rules; no source-code output. */
internal class ArkUiCalls(private val language: Language, val diagnostics: DiagnosticSink) {
    fun literal(value: Any, owner: IrElement) = EtsLiteral(value, when (value) {
        is String -> EtsTypes.STRING; is Boolean -> EtsTypes.BOOLEAN; is Number -> EtsTypes.NUMBER
        else -> error("Unsupported target literal")
    }, language.source(owner))

    fun call(name: String, args: List<EtsExpression>, owner: IrElement,
        types: List<EtsType> = args.map { it.type }, result: EtsType = EtsTypes.VOID,
        receiver: EtsExpression? = null, identity: String = "arkui:$name"): EtsCall {
        val source = language.source(owner)
        val signature = EtsFunctionType(types, result)
        val callee = if (receiver == null) EtsReference(EtsSymbol(identity, name, signature, source, true))
            else EtsMember(receiver, name, signature, source)
        return EtsCall(callee, args, result, source)
    }

    fun attribute(name: String, args: List<EtsExpression>, owner: IrElement): EtsCall {
        val value = args.singleOrNull() ?: diagnostics.unsupported(owner, "Target attribute requires one argument: $name")
        val expected = when (name) {
            "id", "accessibilityText", "accessibilityLevel" -> EtsTypes.STRING
            "enabled", "loop", "indicator", "select", "vertical", "clip", "focusable", "enableScrollInteraction" -> EtsTypes.BOOLEAN
            "scrollable" -> EtsNamedType("ScrollDirection")
            "scrollBar" -> EtsNamedType("BarState")
            "index", "fontSize", "fontColor", "fontWeight", "backgroundColor", "maxLines", "strokeWidth", "color", "opacity", "layoutWeight" -> EtsTypes.NUMBER
            "hitTestBehavior" -> EtsNamedType("HitTestMode")
            "type" -> value.type.takeIf { it == EtsNamedType("ButtonType") || it == EtsNamedType("InputType") }
            "buttonStyle" -> EtsNamedType("ButtonStyleMode")
            "constraintSize" -> value.type.takeIf { it is EtsRecordType && it.name == "ConstraintSizeOptions" &&
                it.fields.all { (name, type) -> name in setOf("minWidth", "minHeight", "maxWidth", "maxHeight") && type == EtsTypes.NUMBER } }
            "align" -> EtsNamedType("Alignment")
            "objectFit" -> EtsNamedType("ImageFit")
            "colorFilter" -> EtsNamedType("ColorFilter")
            "onClick" -> EtsFunctionType(emptyList(), EtsTypes.VOID)
            "onChange" -> value.type.takeIf {
                it == EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.VOID) ||
                    it == EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.VOID)
            } ?: EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.VOID)
            "onChildTouchTest" -> EtsFunctionType(listOf(EtsNamedType("Array", listOf(EtsNamedType("TouchTestInfo")))), EtsNamedType("TouchResult"))
            "width", "height", "borderRadius" -> value.type.takeIf { it == EtsTypes.NUMBER || it == EtsTypes.STRING }
            "offset" -> value.type.takeIf { it is EtsRecordType && it.name == "Position" &&
                it.fields.keys.all { field -> field in setOf("x", "y") } && it.fields.values.all { it == EtsTypes.NUMBER } }
            "rotate" -> value.type.takeIf { it is EtsRecordType && it.name == "RotateOptions" &&
                it.fields.keys.all { field -> field in setOf("x", "y", "z", "angle", "centerX", "centerY", "centerZ", "perspective") } }
            "padding" -> value.type.takeIf { it == EtsTypes.NUMBER || it is EtsRecordType && it.name == "Padding" }
            "responseRegion", "mouseResponseRegion" -> value.type.takeIf { it is EtsRecordType && it.name == "Rectangle" }
            "alignItems" -> value.type.takeIf { it in listOf(EtsNamedType("HorizontalAlign"), EtsNamedType("VerticalAlign")) }
            "justifyContent" -> EtsNamedType("FlexAlign")
            "attributeModifier" -> EtsNamedType("__etsMaterialTypography", symbolId = "compose:materialTypography", external = true)
                .takeIf { value.type == it } ?: textAttributeModifierType
            else -> null
        } ?: diagnostics.unsupported(owner, "Unsupported target attribute signature: $name")
        return call(name, args, owner, listOf(expected))
    }

    fun native(name: String, args: List<EtsExpression>, owner: IrElement, children: List<EtsStatement>? = null): EtsUiElement {
        val expected = when (name) {
            "Text", "Span" -> listOf(EtsTypes.STRING)
            "Image" -> listOf(args.singleOrNull()?.type?.takeIf { it == ImageResources.RESOURCE || it == EtsTypes.STRING }
                ?: diagnostics.unsupported(owner, "Image requires Resource or URL string"))
            "Stack" -> listOf(stackOptions(owner).type)
            "WithTheme" -> listOf(EtsRecordType("SurfaceThemeOptions", mapOf("theme" to
                EtsRecordType("SurfaceTheme", mapOf("colors" to
                    EtsRecordType("SurfaceColors", mapOf("fontPrimary" to EtsTypes.NUMBER)))))))
            "Swiper" -> listOf(EtsNamedType("SwiperController"))
            "Column", "Row" -> if (args.isEmpty()) emptyList() else listOf(
                EtsRecordType("${name}Options", mapOf("space" to EtsTypes.NUMBER)))
            "Button", "Divider", "Checkbox", "Scroll" -> emptyList()
            "TextInput" -> listOf(EtsRecordType("TextInputOptions", mapOf("text" to EtsTypes.STRING)))
            "Toggle" -> listOf(EtsRecordType("ToggleOptions", mapOf("type" to EtsNamedType("ToggleType"), "isOn" to EtsTypes.BOOLEAN)))
            else -> diagnostics.unsupported(owner, "Unknown target control: $name")
        }
        return EtsUiElement(call(name, args, owner, expected), children)
    }

    fun enumValue(type: String, name: String, owner: IrElement): EtsExpression {
        val source = language.source(owner)
        val targetType = EtsNamedType(type)
        return EtsMember(EtsReference(EtsSymbol("arkui:$type", type, targetType, source, true)), name, targetType, source)
    }

    fun record(name: String, values: Map<String, EtsExpression>, owner: IrElement) =
        EtsObject(values, EtsRecordType(name, values.mapValues { it.value.type }), language.source(owner))

    fun stackOptions(owner: IrElement) = record("StackOptions", linkedMapOf("alignContent" to enumValue("Alignment", "TopStart", owner)), owner)

    fun booleanChange(expression: IrExpression, scope: Scope): EtsCall {
        val callback = language.expression(expression, scope)
        val expected = EtsFunctionType(listOf(EtsTypes.BOOLEAN), EtsTypes.VOID)
        if (!etsAssignable(callback.type, expected))
            diagnostics.unsupported(expression, "Selection callback requires a non-null (Boolean) -> Unit value")
        // onChange is overloaded by control: selection callbacks differ from Swiper's numeric index.
        return call("onChange", listOf(callback), expression, listOf(expected))
    }

    fun checkArguments(call: IrCall, supported: Set<String>, omittable: Set<String> = emptySet()) {
        call.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
            val argument = call.getValueArgument(index)
            if (argument != null && parameter.name.asString() !in supported) {
                val message = "Unsupported ${symbolName(call.symbol.owner)} argument: ${parameter.name}"
                if (parameter.name.asString() !in omittable) diagnostics.unsupported(argument, message)
                diagnostics.omitUi(argument, message, "${symbolName(call.symbol.owner)}.${parameter.name}",
                    "omitted_display_argument", "Argument evaluation and its display behavior are omitted; target default applies.")
            }
        }
    }
}
