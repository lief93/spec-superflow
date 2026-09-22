package dev.ets.harmony

import dev.ets.*
import dev.ets.widgets.*

/** Only this module selects native controls and interprets ordered widget modifiers. */
class HarmonyWidgetBackend {
    fun lower(children: Children<EtsExpression, SourceSpan>): List<EtsStatement> = lower(children, null)

    private fun lower(children: Children<EtsExpression, SourceSpan>,
        parent: WidgetLayoutScope?): List<EtsStatement> = children.widgets.map { lowerStatement(it, parent) }

    private fun lowerStatement(widget: Widget<EtsExpression, SourceSpan>,
        parent: WidgetLayoutScope?): EtsStatement = when (widget) {
        is Widget.Conditional -> EtsIf(widget.branches.map { branch ->
            branch.condition?.let { expect(it, EtsTypes.BOOLEAN, "Conditional.condition", branch.source) }
            EtsBranch(branch.condition, lower(branch.children, parent))
        }, widget.source)
        else -> lower(widget, parent)
    }

    fun lower(widget: Widget<EtsExpression, SourceSpan>): EtsUiElement = lower(widget, null)
    private fun lower(widget: Widget<EtsExpression, SourceSpan>, parent: WidgetLayoutScope?): EtsUiElement {
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
                val content = native("Row", children = lower(widget.content, WidgetLayoutScope.ROW)).copy(attributes = listOf(
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
            is Widget.Row -> native("Row", children = lower(widget.children, WidgetLayoutScope.ROW)).copy(attributes = listOf(
                call("alignItems", listOf(enumValue("VerticalAlign", "Top", at)), at)))
            is Widget.Column -> native("Column", children = lower(widget.children, WidgetLayoutScope.COLUMN)).copy(attributes = listOf(
                call("alignItems", listOf(enumValue("HorizontalAlign", "Start", at)), at)))
            is Widget.Box -> native("Stack", listOf(stackOptions(at)), lower(widget.children, WidgetLayoutScope.BOX))
            is Widget.Pager -> {
                expect(widget.currentPage, EtsTypes.NUMBER, "Pager.currentPage", at)
                expect(widget.pageCount, EtsTypes.NUMBER, "Pager.pageCount", at)
                expect(widget.controller, EtsNamedType("SwiperController"), "Pager.controller", at)
                expect(widget.onPageChange, EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.VOID),
                    "Pager.onPageChange", at)
                expect(widget.pageContent.index, EtsTypes.NUMBER, "Pager.pageContent.index", widget.pageContent.source)
                val index = widget.pageContent.index as? EtsReference
                    ?: throw IllegalArgumentException("Pager.pageContent.index requires a target binding at ${widget.pageContent.source}")
                val count = (widget.pageCount as? EtsLiteral)?.value as? Number
                require(count != null && count.toDouble().isFinite() && count.toDouble() % 1.0 == 0.0 && count.toInt() > 0) {
                    "Pager.pageCount requires a positive integer literal at $at"
                }
                val pages = EtsArray((0 until count.toInt()).map { EtsLiteral(it, EtsTypes.NUMBER, at) },
                    EtsTypes.NUMBER, at)
                native("Swiper", listOf(widget.controller), listOf(EtsUiForEach(pages,
                    EtsParameter(index.symbol), lower(widget.pageContent.children, null), widget.pageContent.source)))
                    .copy(attributes = listOf(
                        call("index", listOf(widget.currentPage), at),
                        call("loop", listOf(EtsLiteral(false, EtsTypes.BOOLEAN, at)), at),
                        call("indicator", listOf(EtsLiteral(false, EtsTypes.BOOLEAN, at)), at),
                        call("onChange", listOf(widget.onPageChange), at)))
            }
            is Widget.LazyList -> {
                expect(widget.enabled, EtsTypes.BOOLEAN, "LazyList.enabled", at)
                val stateArguments = widget.state?.let { state ->
                    expect(state.initialIndex, EtsTypes.NUMBER, "LazyList.state.initialIndex", state.source)
                    expect(state.initialOffset, EtsTypes.NUMBER, "LazyList.state.initialOffset", state.source)
                    expect(state.firstVisibleIndex, EtsTypes.NUMBER,
                        "LazyList.state.firstVisibleIndex", state.source)
                    expect(state.controller, EtsNamedType("Scroller"),
                        "LazyList.state.controller", state.source)
                    listOf(EtsObject(linkedMapOf("initialIndex" to state.initialIndex,
                        "scroller" to state.controller), EtsRecordType("ListOptions", linkedMapOf(
                        "initialIndex" to EtsTypes.NUMBER, "scroller" to EtsNamedType("Scroller"))), state.source))
                } ?: emptyList()
                fun stringKey(value: EtsExpression, source: SourceSpan): EtsExpression = when (value.type) {
                    EtsTypes.STRING -> value
                    EtsTypes.NUMBER -> EtsCall(EtsMember(value, "toString",
                        EtsFunctionType(emptyList(), EtsTypes.STRING), source),
                        emptyList(), EtsTypes.STRING, source)
                    else -> throw IllegalArgumentException(
                        "LazyList key requires string or number at $source; got ${value.type}")
                }
                val slots = widget.slots.map { slot -> when (slot) {
                    is LazyListSlot.Item -> native("ListItem", children = lower(slot.content, null)).let { item ->
                        slot.key?.let { key -> item.copy(attributes = listOf(
                            call("id", listOf(stringKey(key, slot.source)), slot.source))) } ?: item
                    }
                    is LazyListSlot.Items -> {
                        val item = slot.item as? EtsReference ?: throw IllegalArgumentException(
                            "LazyList item requires a target binding at ${slot.source}")
                        val index = slot.index as? EtsReference ?: throw IllegalArgumentException(
                            "LazyList index requires a target binding at ${slot.source}")
                        expect(index, EtsTypes.NUMBER, "LazyList.index", slot.source)
                        val values = when (val data = slot.data) {
                            is LazyListData.Values -> {
                                val array = data.values.type as? EtsNamedType
                                require(array?.name == "Array" && array.arguments.singleOrNull() == item.type) {
                                    "LazyList values require Array<${item.type}> at ${slot.source}; got ${data.values.type}"
                                }
                                data.values
                            }
                            is LazyListData.Count -> {
                                expect(data.count, EtsTypes.NUMBER, "LazyList.count", slot.source)
                                require(item.type == EtsTypes.NUMBER) {
                                    "LazyList count item requires number at ${slot.source}; got ${item.type}"
                                }
                                EtsCall(EtsReference(EtsSymbol("stdlib:__etsLazyIndices", "__etsLazyIndices",
                                    EtsFunctionType(listOf(EtsTypes.NUMBER),
                                        EtsNamedType("Array", listOf(EtsTypes.NUMBER))), slot.source, true)),
                                    listOf(data.count), EtsNamedType("Array", listOf(EtsTypes.NUMBER)), slot.source)
                            }
                        }
                        val dataSourceType = EtsNamedType("__etsLazyArrayDataSource", listOf(item.type),
                            "stdlib:__etsLazyArrayDataSource", external = true)
                        val dataSource = EtsNew(dataSourceType, listOf(values), slot.source)
                        val key = slot.key?.let { value -> EtsLambda(
                            listOf(EtsParameter(item.symbol), EtsParameter(index.symbol)),
                            listOf(EtsReturn(stringKey(value, slot.source), slot.source)),
                            EtsTypes.STRING, slot.source)
                        }
                        EtsUiLazyForEach(dataSource, EtsParameter(item.symbol), EtsParameter(index.symbol),
                            listOf(native("ListItem", children = lower(slot.content, null))), key, slot.source)
                    }
                } }
                val stateAttributes = widget.state?.let { state -> buildList {
                    state.initialOffsetApplied?.let { applied ->
                        expect(applied, EtsTypes.BOOLEAN,
                            "LazyList.state.initialOffsetApplied", state.source)
                        val converted = EtsCall(EtsReference(EtsSymbol("arkui:px2vp", "px2vp",
                            EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.NUMBER), state.source, true)),
                            listOf(state.initialOffset), EtsTypes.NUMBER, state.source)
                        val zero = EtsLiteral(0, EtsTypes.NUMBER, state.source)
                        val scroll = EtsCall(EtsMember(state.controller, "scrollBy",
                            EtsFunctionType(listOf(EtsTypes.NUMBER, EtsTypes.NUMBER), EtsTypes.VOID),
                            state.source), if (widget.axis == WidgetScrollAxis.VERTICAL)
                            listOf(zero, converted) else listOf(converted, zero), EtsTypes.VOID, state.source)
                        val initialize = EtsLambda(emptyList(), listOf(EtsIf(listOf(EtsBranch(
                            EtsUnary("!", applied, EtsTypes.BOOLEAN, state.source), listOf(
                                EtsExpressionStatement(scroll),
                                EtsExpressionStatement(EtsAssignment(applied,
                                    EtsLiteral(true, EtsTypes.BOOLEAN, state.source), state.source))))),
                            state.source)), EtsTypes.VOID, state.source)
                        add(call("onAppear", listOf(initialize), state.source))
                    }
                    val start = EtsParameter(EtsSymbol(
                        "harmony-lazy:${state.source.file}:${state.source.start}:start",
                        "start", EtsTypes.NUMBER, state.source))
                    val end = EtsParameter(EtsSymbol(
                        "harmony-lazy:${state.source.file}:${state.source.start}:end",
                        "end", EtsTypes.NUMBER, state.source))
                    val center = EtsParameter(EtsSymbol(
                        "harmony-lazy:${state.source.file}:${state.source.start}:center",
                        "center", EtsTypes.NUMBER, state.source))
                    val onIndex = EtsLambda(listOf(start, end, center), listOf(EtsExpressionStatement(
                        EtsAssignment(state.firstVisibleIndex, EtsReference(start.symbol), state.source))),
                        EtsTypes.VOID, state.source)
                    add(call("onScrollIndex", listOf(onIndex), state.source))
                } } ?: emptyList()
                native("List", stateArguments, slots).copy(attributes = listOf(
                    call("listDirection", listOf(enumValue("Axis",
                        if (widget.axis == WidgetScrollAxis.VERTICAL) "Vertical" else "Horizontal", at)), at),
                    call("scrollBar", listOf(enumValue("BarState", "Off", at)), at),
                    call("enableScrollInteraction", listOf(widget.enabled), at)) + stateAttributes)
            }
            is Widget.Conditional -> throw IllegalArgumentException(
                "Conditional widgets require a children boundary at $at")
            is Widget.BuilderCall -> {
                val call = widget.call as? EtsCall
                    ?: throw IllegalArgumentException("Builder call requires a typed target call at $at")
                expect(call, EtsTypes.VOID, "BuilderCall.call", at)
                EtsUiElement(call)
            }
        }
        // Ordinary operations retain their positions and duplicates. Parent-data
        // operations are hoisted afterward so Row/Column/Box sees them on its
        // direct child, while their neutral-model order remains intact.
        val ordinary = widget.modifiers.filterNot { it is WidgetModifier.Weight || it is WidgetModifier.Align }
        val wrapped = ordinary.asReversed().fold(element) { child, modifier ->
            val source = modifier.source
            if (modifier is WidgetModifier.Scroll) {
                expect(modifier.offset, EtsTypes.NUMBER, "Scroll.offset", source)
                expect(modifier.enabled, EtsTypes.BOOLEAN, "Scroll.enabled", source)
                expect(modifier.onScroll,
                    EtsFunctionType(listOf(EtsTypes.NUMBER, EtsTypes.NUMBER), EtsTypes.VOID),
                    "Scroll.onScroll", source)
                val zero = EtsLiteral(0, EtsTypes.NUMBER, source)
                val offsets = if (modifier.axis == WidgetScrollAxis.VERTICAL)
                    linkedMapOf("xOffset" to zero, "yOffset" to modifier.offset)
                else linkedMapOf("xOffset" to modifier.offset, "yOffset" to zero)
                return@fold EtsUiElement(call("Scroll", emptyList(), source), listOf(child), listOf(
                    call("scrollable", listOf(enumValue("ScrollDirection",
                        if (modifier.axis == WidgetScrollAxis.VERTICAL) "Vertical" else "Horizontal", source)), source),
                    call("initialOffset", listOf(EtsObject(offsets,
                        EtsRecordType("OffsetOptions", offsets.mapValues { EtsTypes.NUMBER }), source)), source),
                    call("scrollBar", listOf(enumValue("BarState", "Off", source)), source),
                    call("enableScrollInteraction", listOf(modifier.enabled), source),
                    call("align", listOf(enumValue("Alignment", "TopStart", source)), source),
                    call("onScroll", listOf(modifier.onScroll), source)))
            }
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
                is WidgetModifier.Fill -> {
                    expect(modifier.fraction, EtsTypes.NUMBER, "Fill.fraction", source)
                    val constant = (modifier.fraction as? EtsLiteral)?.value as? Number
                    require(constant == null || constant.toDouble().isFinite() && constant.toDouble() in 0.0..1.0) {
                        "Fill.fraction must be finite and between zero and one at $source"
                    }
                    val length = percentage(modifier.fraction, source)
                    buildList {
                        if (modifier.width) add(call("width", listOf(length), source))
                        if (modifier.height) add(call("height", listOf(length), source))
                    }.also { require(it.isNotEmpty()) { "Fill requires at least one axis at $source" } }
                }
                is WidgetModifier.Weight -> {
                    error("Scoped modifier remained in ordinary widget modifiers")
                }
                is WidgetModifier.Align -> {
                    error("Scoped modifier remained in ordinary widget modifiers")
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
                is WidgetModifier.Scroll -> error("Scroll modifier bypassed its native wrapper")
            }
            EtsUiElement(call("Stack", listOf(stackOptions(source)), source), listOf(child), attributes)
        }
        return widget.modifiers.filter { it is WidgetModifier.Weight || it is WidgetModifier.Align }
            .asReversed().fold(wrapped) { child, modifier ->
                val source = modifier.source
                val attributes = when (modifier) {
                    is WidgetModifier.Weight -> {
                        require(modifier.parent == parent && parent in setOf(WidgetLayoutScope.ROW, WidgetLayoutScope.COLUMN)) {
                            "Weight requires its recorded Row or Column parent at $source; got $parent"
                        }
                        expect(modifier.value, EtsTypes.NUMBER, "Weight.value", source)
                        val constant = (modifier.value as? EtsLiteral)?.value as? Number
                        require(constant == null || constant.toDouble().isFinite() && constant.toDouble() > 0.0) {
                            "Weight.value must be finite and positive at $source"
                        }
                        listOf(call("layoutWeight", listOf(modifier.value), source))
                    }
                    is WidgetModifier.Align -> {
                        require(modifier.parent == WidgetLayoutScope.BOX && parent == WidgetLayoutScope.BOX) {
                            "Align requires its recorded Box parent at $source; got $parent"
                        }
                        expect(modifier.value, EtsNamedType("Alignment"), "Align.value", source)
                        listOf(call("align", listOf(modifier.value), source))
                    }
                    else -> error("Ordinary modifier entered scoped widget modifiers")
                }
                EtsUiElement(call("Stack", listOf(stackOptions(source)), source), listOf(child), attributes)
            }
    }

    private fun percentage(fraction: EtsExpression, at: SourceSpan): EtsExpression {
        val constant = (fraction as? EtsLiteral)?.value as? Number
        if (constant != null) return EtsLiteral("${constant.toDouble() * 100}%", EtsTypes.STRING, at)
        return EtsBinary("+", EtsBinary("*", fraction, EtsLiteral(100, EtsTypes.NUMBER, at),
            EtsTypes.NUMBER, at), EtsLiteral("%", EtsTypes.STRING, at), EtsTypes.STRING, at)
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
