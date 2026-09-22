package dev.ets.harmony

import dev.ets.*
import dev.ets.widgets.*

/** Only this module selects native controls and interprets ordered widget modifiers. */
class HarmonyWidgetBackend {
    fun lower(children: Children<EtsExpression, SourceSpan>): List<EtsUiElement> = children.widgets.map(::lower)

    fun lower(widget: Widget<EtsExpression, SourceSpan>): EtsUiElement {
        val at = widget.source
        fun native(name: String, arguments: List<EtsExpression> = emptyList(), children: List<EtsStatement>? = null) =
            EtsUiElement(call(name, arguments, at), children)
        val element = when (widget) {
            is Widget.Text -> {
                val text = consume(widget.text, WidgetValueType.STRING)
                native("Text", listOf(text)).copy(attributes = listOf(
                    call("align", listOf(enumValue("Alignment", "TopStart", at)), at)) + listOfNotNull(
                    widget.style.fontSize?.let { call("fontSize", listOf(consume(it, WidgetValueType.FONT_SIZE)), it.source) },
                    widget.style.fontWeight?.let { call("fontWeight", listOf(consume(it, WidgetValueType.FONT_WEIGHT)), it.source) },
                    widget.style.fontFamily?.let { call("fontFamily", listOf(consume(it, WidgetValueType.FONT_FAMILY)), it.source) },
                    widget.style.lineHeight?.let { call("lineHeight", listOf(consume(it, WidgetValueType.LINE_HEIGHT)), it.source) }))
            }
            is Widget.Image -> {
                val image = when (val source = widget.image) {
                    is ImageSource.Resource -> {
                        expect(source.value, resourceType, "Image.resource", source.source)
                        source.value
                    }
                    is ImageSource.Url -> {
                        expect(source.value, EtsTypes.STRING, "Image.url", source.source)
                        source.value
                    }
                }
                val accessibility = when (widget.contentDescription.type) {
                    EtsTypes.STRING -> call("accessibilityText", listOf(widget.contentDescription), at)
                    EtsTypes.NULL -> call("accessibilityLevel",
                        listOf(EtsLiteral("no", EtsTypes.STRING, at)), at)
                    else -> throw IllegalArgumentException(
                        "Image.contentDescription requires string or null at $at; got ${widget.contentDescription.type}")
                }
                native("Image", listOf(image)).copy(attributes = listOf(
                    call("objectFit", listOf(enumValue("ImageFit", "Contain", at)), at), accessibility))
            }
            is Widget.Button -> {
                val enabled = widget.enabled ?: EtsLiteral(true, EtsTypes.BOOLEAN, at)
                expect(enabled, EtsTypes.BOOLEAN, "Button.enabled", at)
                expect(widget.onClick, EtsFunctionType(emptyList(), EtsTypes.VOID), "Button.onClick", at)
                val content = native("Row", children = lower(widget.content)).copy(attributes = listOf(
                    call("alignItems", listOf(enumValue("VerticalAlign", "Center", at)), at),
                    call("justifyContent", listOf(enumValue("FlexAlign", "Center", at)), at)))
                native("Button", children = listOf(content)).copy(attributes = listOf(
                    call("enabled", listOf(enabled), at), call("onClick", listOf(widget.onClick), at)))
            }
            is Widget.TextField -> {
                expect(widget.value, EtsTypes.STRING, "TextField.value", at)
                expect(widget.onValueChange, EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.VOID),
                    "TextField.onValueChange", at)
                val enabled = widget.enabled ?: EtsLiteral(true, EtsTypes.BOOLEAN, at)
                expect(enabled, EtsTypes.BOOLEAN, "TextField.enabled", at)
                val options = EtsObject(mapOf("text" to widget.value),
                    EtsRecordType("TextInputOptions", mapOf("text" to EtsTypes.STRING)), at)
                native("TextInput", listOf(options)).copy(attributes = listOf(
                    call("enabled", listOf(enabled), at),
                    call("onChange", listOf(widget.onValueChange), at)))
            }
            is Widget.Row -> native("Row", children = lower(widget.children)).copy(attributes = listOf(
                call("alignItems", listOf(enumValue("VerticalAlign", "Top", at)), at)))
            is Widget.Column -> native("Column", children = lower(widget.children)).copy(attributes = listOf(
                call("alignItems", listOf(enumValue("HorizontalAlign", "Start", at)), at)))
            is Widget.Box -> native("Stack", listOf(stackOptions(at)), lower(widget.children))
        }
        // A distinct wrapper per operation retains its position and duplicates.
        // This preserves semantic structure, not Compose's complete measure policy.
        return widget.modifiers.asReversed().fold(element) { child, modifier ->
            val source = modifier.source
            val attributes = when (modifier) {
                is WidgetModifier.Size -> {
                    expect(modifier.width, EtsTypes.NUMBER, "Size.width", source)
                    expect(modifier.height, EtsTypes.NUMBER, "Size.height", source)
                    listOf(call("width", listOf(modifier.width), source),
                        call("height", listOf(modifier.height), source))
                }
                is WidgetModifier.Width -> {
                    expect(modifier.value, EtsTypes.NUMBER, "Width.value", source)
                    listOf(call("width", listOf(modifier.value), source))
                }
                is WidgetModifier.Height -> {
                    expect(modifier.value, EtsTypes.NUMBER, "Height.value", source)
                    listOf(call("height", listOf(modifier.value), source))
                }
                is WidgetModifier.Padding -> {
                    val sides = linkedMapOf("left" to modifier.start, "top" to modifier.top,
                        "right" to modifier.end, "bottom" to modifier.bottom)
                    sides.forEach { (side, value) -> expect(value, EtsTypes.NUMBER, "Padding.$side", source) }
                    listOf(call("padding", listOf(EtsObject(sides,
                        EtsRecordType("Padding", sides.mapValues { EtsTypes.NUMBER }), source)), source))
                }
                is WidgetModifier.Background -> {
                    val color = consume(modifier.color, WidgetValueType.COLOR)
                    listOf(call("backgroundColor", listOf(color), source))
                }
                is WidgetModifier.Click -> {
                    expect(modifier.onClick, EtsFunctionType(emptyList(), EtsTypes.VOID), "Click.onClick", source)
                    val enabled = modifier.enabled ?: EtsLiteral(true, EtsTypes.BOOLEAN, source)
                    expect(enabled, EtsTypes.BOOLEAN, "Click.enabled", source)
                    listOf(call("enabled", listOf(enabled), source),
                        call("onClick", listOf(modifier.onClick), source))
                }
            }
            EtsUiElement(call("Stack", listOf(stackOptions(source)), source), listOf(child), attributes)
        }
    }

    /** The only target-type interpretation for semantic widget values. */
    private fun consume(value: WidgetValue<EtsExpression, SourceSpan>, expected: WidgetValueType): EtsExpression {
        require(value.type == expected) {
            "Widget value requires $expected at ${value.source}; got ${value.type}"
        }
        val target = when (expected) {
            WidgetValueType.STRING, WidgetValueType.FONT_FAMILY -> EtsTypes.STRING
            WidgetValueType.COLOR, WidgetValueType.FONT_SIZE, WidgetValueType.FONT_WEIGHT,
                WidgetValueType.LINE_HEIGHT -> EtsTypes.NUMBER
        }
        expect(value.value, target, "Widget value $expected", value.source)
        return value.value
    }

    private fun expect(value: EtsExpression, type: EtsType, property: String, at: SourceSpan) {
        require(value.type == type) { "$property requires $type at $at; got ${value.type}" }
    }

    private fun call(name: String, arguments: List<EtsExpression>, at: SourceSpan): EtsCall = EtsCall(
        EtsReference(EtsSymbol("arkui:$name", name, EtsFunctionType(arguments.map { it.type }, EtsTypes.VOID), at, true)),
        arguments, EtsTypes.VOID, at)

    private fun enumValue(type: String, name: String, at: SourceSpan): EtsExpression =
        EtsMember(EtsReference(EtsSymbol("arkui:$type", type, EtsNamedType(type), at, true)), name, EtsNamedType(type), at)

    private fun stackOptions(at: SourceSpan): EtsExpression = EtsObject(
        mapOf("alignContent" to enumValue("Alignment", "TopStart", at)),
        EtsRecordType("StackOptions", mapOf("alignContent" to EtsNamedType("Alignment"))), at)

    private companion object {
        val resourceType = EtsNamedType("Resource", external = true)
    }
}
