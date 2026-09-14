@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.expressions.IrCall

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
            "id" -> EtsTypes.STRING
            "enabled", "loop", "indicator" -> EtsTypes.BOOLEAN
            "index", "fontSize", "fontColor", "backgroundColor" -> EtsTypes.NUMBER
            "onClick" -> EtsFunctionType(emptyList(), EtsTypes.VOID)
            "onChange" -> EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.VOID)
            "onChildTouchTest" -> EtsFunctionType(listOf(EtsNamedType("Array", listOf(EtsNamedType("TouchTestInfo")))), EtsNamedType("TouchResult"))
            "width", "height" -> value.type.takeIf { it == EtsTypes.NUMBER || it == EtsTypes.STRING }
            "padding" -> value.type.takeIf { it == EtsTypes.NUMBER || it is EtsRecordType && it.name == "Padding" }
            "responseRegion", "mouseResponseRegion" -> value.type.takeIf { it is EtsRecordType && it.name == "Rectangle" }
            "alignItems" -> value.type.takeIf { it in listOf(EtsNamedType("HorizontalAlign"), EtsNamedType("VerticalAlign")) }
            "justifyContent" -> EtsNamedType("FlexAlign")
            "attributeModifier" -> EtsNamedType("__etsMaterialTypography", symbolId = "compose:materialTypography", external = true)
            else -> null
        } ?: diagnostics.unsupported(owner, "Unsupported target attribute signature: $name")
        return call(name, args, owner, listOf(expected))
    }

    fun native(name: String, args: List<EtsExpression>, owner: IrElement, children: List<EtsStatement>? = null): EtsUiElement {
        val expected = when (name) {
            "Text" -> listOf(EtsTypes.STRING)
            "Stack" -> listOf(stackOptions(owner).type)
            "Swiper" -> listOf(EtsNamedType("SwiperController"))
            "Column", "Row", "Button" -> emptyList()
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

    fun checkArguments(call: IrCall, supported: Set<String>) {
        call.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
            if (call.getValueArgument(index) != null && parameter.name.asString() !in supported)
                diagnostics.unsupported(call.getValueArgument(index)!!, "Unsupported ${symbolName(call.symbol.owner)} argument: ${parameter.name}")
        }
    }
}
