package dev.ets.harmony

import dev.ets.*
import dev.ets.widgets.*

/** Only this module selects native controls and interprets ordered widget modifiers. */
class HarmonyWidgetBackend {
    private var pageIndices: EtsFunction? = null

    fun supportDeclarations(): List<EtsDeclaration> = listOfNotNull(pageIndices)

    fun entryContainer(content: EtsCall, at: SourceSpan): EtsUiElement {
        expect(content, EtsTypes.VOID, "Entry.content", at)
        return EtsUiElement(call("Stack", listOf(stackOptions(at)), at),
            listOf(EtsUiElement(content)), listOf(
                call("width", listOf(EtsLiteral("100%", EtsTypes.STRING, at)), at),
                call("height", listOf(EtsLiteral("100%", EtsTypes.STRING, at)), at)))
    }

    fun lower(children: Children<EtsExpression, SourceSpan>,
        parent: WidgetLayoutScope? = null): List<EtsStatement> = children.widgets.flatMap { widget ->
        if (widget is Widget.Group) lower(widget.children, parent) else listOf(lowerStatement(widget, parent))
    }

    private fun lowerStatement(widget: Widget<EtsExpression, SourceSpan>,
        parent: WidgetLayoutScope?): EtsStatement {
        val conditionalIndex = widget.modifiers.indexOfFirst { it is WidgetModifier.Conditional }
        if (conditionalIndex >= 0) {
            val conditional = widget.modifiers[conditionalIndex] as WidgetModifier.Conditional
            val prefix = widget.modifiers.take(conditionalIndex)
            val suffix = widget.modifiers.drop(conditionalIndex + 1)
            return EtsIf(conditional.branches.map { branch ->
                branch.condition?.let { expect(it, EtsTypes.BOOLEAN, "Modifier.condition", branch.source) }
                val expanded = withModifiers(widget, prefix + branch.modifiers + suffix)
                EtsBranch(branch.condition, listOf(lowerStatement(expanded, parent)))
            }, conditional.source)
        }
        return when (widget) {
        is Widget.Conditional -> EtsIf(widget.branches.map { branch ->
            branch.condition?.let { expect(it, EtsTypes.BOOLEAN, "Conditional.condition", branch.source) }
            EtsBranch(branch.condition, lower(branch.children, parent))
        }, widget.source)
        is Widget.ForEach -> {
            val item = widget.item as? EtsReference ?: throw IllegalArgumentException(
                "ForEach.item requires a target binding at ${widget.source}")
            val items = when (val data = widget.data) {
                is WidgetIterationData.Values -> {
                    val array = data.values.type as? EtsNamedType
                    require(array?.name == "Array" && array.arguments.singleOrNull() == item.type) {
                        "ForEach.values requires Array<${item.type}> at ${widget.source}; got ${data.values.type}"
                    }
                    data.values
                }
                is WidgetIterationData.Count -> {
                    expect(data.count, EtsTypes.NUMBER, "ForEach.count", widget.source)
                    require(item.type == EtsTypes.NUMBER) {
                        "ForEach count item requires number at ${widget.source}; got ${item.type}"
                    }
                    EtsCall(EtsReference(EtsSymbol("stdlib:__etsRepeatIndices", "__etsRepeatIndices",
                        EtsFunctionType(listOf(EtsTypes.NUMBER),
                            EtsNamedType("Array", listOf(EtsTypes.NUMBER))), widget.source, true)),
                        listOf(data.count), EtsNamedType("Array", listOf(EtsTypes.NUMBER)), widget.source)
                }
            }
            EtsUiForEach(items, EtsParameter(item.symbol), lower(widget.children, parent), widget.source)
        }
        is Widget.ValueScope -> {
            val reference = widget.reference as? EtsReference ?: throw IllegalArgumentException(
                "ValueScope.reference requires a target binding at ${widget.source}")
            require(reference.type == widget.value.type) {
                "ValueScope type mismatch at ${widget.source}: ${reference.type} and ${widget.value.type}"
            }
            EtsUiForEach(EtsArray(listOf(widget.value), widget.value.type, widget.source),
                EtsParameter(reference.symbol), lower(widget.children, parent), widget.source)
        }
        is Widget.ThemeProvider -> {
            val reference = widget.reference as? EtsReference ?: throw IllegalArgumentException(
                "ThemeProvider.reference requires a target binding at ${widget.source}")
            require(reference.type == widget.theme.type) {
                "ThemeProvider type mismatch at ${widget.source}: ${reference.type} and ${widget.theme.type}"
            }
            EtsUiForEach(EtsArray(listOf(widget.theme), widget.theme.type, widget.source),
                EtsParameter(reference.symbol), lower(widget.children, parent), widget.source)
        }
        else -> preserveSourceArgumentEvaluation(lower(widget, parent), widget.source,
            widget.sourceEvaluations)
        }
    }

    /**
     * ArkUI prints container options and chained attributes in target order, which
     * is not necessarily the source call-argument order.  Evaluate source calls
     * before entering the element's child builder, then let the native surface
     * consume stable references.  This is target lowering, not Compose API
     * matching: every widget receives the same ordering rule.
     */
    private fun preserveSourceArgumentEvaluation(element: EtsUiElement,
        source: SourceSpan, sourceEvaluations: List<EtsExpression>): EtsStatement {
        val explicit = sourceEvaluations.filterNot { staticTargetEvaluation(it).canReorder }
        val explicitReplacements = evaluationReferences(explicit)
        val rewritten = rewriteProjectionElement(element, source, explicitReplacements)
        var statement = preserveProjectedArgumentEvaluation(rewritten, source)
        explicit.asReversed().forEach { value ->
            val reference = explicitReplacements.getValue(value)
            statement = EtsUiForEach(EtsArray(listOf(value), value.type, value.source),
                EtsParameter(reference.symbol), listOf(statement), value.source,
                kind = EtsUiForEachKind.SOURCE_EVALUATION)
        }
        return statement
    }

    private fun preserveProjectedArgumentEvaluation(element: EtsUiElement,
        source: SourceSpan): EtsStatement {
        val occurrences = mutableListOf<Pair<EtsExpression, Boolean>>()
        fun collect(value: EtsExpression, delayedByChildren: Boolean) {
            when (value) {
                is EtsArray -> value.elements.forEach { collect(it, delayedByChildren) }
                is EtsObject -> value.fields.values.forEach { collect(it, delayedByChildren) }
                else -> if (!staticTargetEvaluation(value).canReorder)
                    occurrences += value to delayedByChildren
            }
        }
        fun collectProjection(statement: EtsStatement, root: Boolean = false) {
            val current = statement as? EtsUiElement ?: return
            if (!root && current.source != source) return
            current.call.arguments.forEach { collect(it, delayedByChildren = false) }
            current.children.orEmpty().forEach { collectProjection(it) }
            val delayed = !current.children.isNullOrEmpty()
            current.attributes.forEach { attribute ->
                attribute.arguments.forEach { collect(it, delayedByChildren = delayed) }
            }
        }
        collectProjection(element, root = true)
        if (occurrences.isEmpty()) return element
        val targetOrder = occurrences.map { it.first }.distinct()
        val sourceOrder = targetOrder.withIndex().sortedWith(
            compareBy<IndexedValue<EtsExpression>>(
                { it.value.source.file ?: source.file ?: "" },
                { it.value.source.start },
                { it.index })).map { it.value }
        val reordered = targetOrder != sourceOrder
        val selected = if (reordered) sourceOrder else occurrences
            .filter { it.second }.map { it.first }.distinct()
        if (selected.isEmpty()) return element

        val replacements = evaluationReferences(selected)
        var statement: EtsStatement = rewriteProjectionElement(element, source, replacements)
        selected.asReversed().forEach { value ->
            val reference = replacements.getValue(value)
            statement = EtsUiForEach(EtsArray(listOf(value), value.type, value.source),
                EtsParameter(reference.symbol), listOf(statement), value.source,
                kind = EtsUiForEachKind.SOURCE_EVALUATION)
        }
        return statement
    }

    private fun evaluationReferences(values: List<EtsExpression>): Map<EtsExpression, EtsReference> =
        linkedMapOf<EtsExpression, EtsReference>().also { replacements ->
        values.forEachIndexed { index, value ->
            val symbol = EtsSymbol(
                "widget-argument:${value.source.file}:${value.source.start}:${value.source.end}:$index",
                "__etsUiArg${value.source.start}_$index", value.type, value.source)
            replacements[value] = EtsReference(symbol)
        }
    }

    private fun rewriteProjectionElement(element: EtsUiElement, source: SourceSpan,
        replacements: Map<EtsExpression, EtsReference>): EtsUiElement = element.copy(
        call = rewriteExpression(element.call, replacements) as EtsCall,
        children = element.children?.map { child ->
            if (child is EtsUiElement && child.source == source)
                rewriteProjectionElement(child, source, replacements)
            else child
        },
        attributes = element.attributes.map { rewriteExpression(it, replacements) as EtsCall })

    private fun rewriteExpression(value: EtsExpression,
        replacements: Map<EtsExpression, EtsReference>): EtsExpression {
        replacements[value]?.let { return it }
        return when (value) {
            is EtsMember -> value.copy(receiver = rewriteExpression(value.receiver, replacements))
            is EtsCall -> value.copy(callee = rewriteExpression(value.callee, replacements),
                arguments = value.arguments.map { rewriteExpression(it, replacements) })
            is EtsNew -> value.copy(arguments = value.arguments.map { rewriteExpression(it, replacements) })
            is EtsBinary -> value.copy(left = rewriteExpression(value.left, replacements),
                right = rewriteExpression(value.right, replacements))
            is EtsUnary -> value.copy(operand = rewriteExpression(value.operand, replacements))
            is EtsConditional -> value.copy(
                condition = rewriteExpression(value.condition, replacements),
                whenTrue = rewriteExpression(value.whenTrue, replacements),
                whenFalse = rewriteExpression(value.whenFalse, replacements))
            is EtsAssignment -> value.copy(target = rewriteExpression(value.target, replacements),
                value = rewriteExpression(value.value, replacements))
            is EtsCast -> value.copy(value = rewriteExpression(value.value, replacements))
            is EtsArray -> value.copy(elements = value.elements.map { rewriteExpression(it, replacements) })
            is EtsObject -> value.copy(fields = value.fields.mapValues { rewriteExpression(it.value, replacements) })
            is EtsLambda, is EtsLiteral, is EtsUndefined, is EtsReference, is EtsSuper -> value
        }
    }

    private fun withModifiers(widget: Widget<EtsExpression, SourceSpan>,
        modifiers: List<WidgetModifier<EtsExpression, SourceSpan>>): Widget<EtsExpression, SourceSpan> = when (widget) {
        is Widget.Text -> widget.copy(modifiers = modifiers)
        is Widget.Image -> widget.copy(modifiers = modifiers)
        is Widget.Button -> widget.copy(modifiers = modifiers)
        is Widget.TextField -> widget.copy(modifiers = modifiers)
        is Widget.Row -> widget.copy(modifiers = modifiers)
        is Widget.Column -> widget.copy(modifiers = modifiers)
        is Widget.Box -> widget.copy(modifiers = modifiers)
        is Widget.Surface -> widget.copy(modifiers = modifiers)
        is Widget.Spacer -> widget.copy(modifiers = modifiers)
        is Widget.Pager -> widget.copy(modifiers = modifiers)
        is Widget.LazyList -> widget.copy(modifiers = modifiers)
        is Widget.TopAppBar -> widget.copy(modifiers = modifiers)
        is Widget.Scaffold -> widget.copy(modifiers = modifiers)
        is Widget.SnackbarHost -> widget.copy(modifiers = modifiers)
        is Widget.Group, is Widget.ValueScope, is Widget.ThemeProvider,
        is Widget.Conditional, is Widget.ForEach,
        is Widget.BuilderCall -> throw IllegalArgumentException(
            "${widget.javaClass.simpleName} cannot own conditional modifiers at ${widget.source}")
    }

    fun lower(widget: Widget<EtsExpression, SourceSpan>): EtsUiElement = lower(widget, null)
    private fun lower(widget: Widget<EtsExpression, SourceSpan>, parent: WidgetLayoutScope?): EtsUiElement {
        val at = widget.source
        val replaceableNativeDefaults = mutableSetOf<String>()
        fun native(name: String, arguments: List<EtsExpression> = emptyList(), children: List<EtsStatement>? = null) =
            EtsUiElement(call(name, arguments, at), children)
        val element = when (widget) {
            is Widget.Group -> throw IllegalArgumentException(
                "Group widgets require a children boundary at $at")
            is Widget.ValueScope -> throw IllegalArgumentException(
                "Value scopes require a children boundary at $at")
            is Widget.ThemeProvider -> throw IllegalArgumentException(
                "Theme providers require a children boundary at $at")
            is Widget.Text -> {
                val text = consume(widget.text, WidgetValueType.STRING)
                val inherited = widget.style.inheritedStyle
                val attributes = if (inherited == null) listOfNotNull(
                    widget.style.color?.let { call("fontColor", listOf(consume(it, WidgetValueType.COLOR)), it.source) },
                    widget.style.fontSize?.let { call("fontSize", listOf(consume(it, WidgetValueType.FONT_SIZE)), it.source) },
                    widget.style.fontWeight?.let { call("fontWeight", listOf(consume(it, WidgetValueType.FONT_WEIGHT)), it.source) },
                    widget.style.fontFamily?.let { call("fontFamily", listOf(consume(it, WidgetValueType.FONT_FAMILY)), it.source) },
                    widget.style.lineHeight?.let { call("lineHeight", listOf(consume(it, WidgetValueType.LINE_HEIGHT)), it.source) })
                else {
                    expect(inherited, etsTextStyleType, "Text.inheritedStyle", at)
                    val nil = EtsLiteral(null, EtsTypes.NULL, at)
                    val overflow = widget.style.overflow ?: enumValue("TextOverflow", "Clip", at)
                    val maxLines = widget.style.maxLines ?: EtsLiteral(Int.MAX_VALUE, EtsTypes.NUMBER, at)
                    val values = etsTextStyleArgumentOrder.map { name -> when (name) {
                        "color" -> widget.style.color?.let { consume(it, WidgetValueType.COLOR) } ?: nil
                        "fontSize" -> widget.style.fontSize?.let { consume(it, WidgetValueType.FONT_SIZE) } ?: nil
                        "fontStyle" -> widget.style.fontStyle ?: nil
                        "fontWeight" -> widget.style.fontWeight?.let { consume(it, WidgetValueType.FONT_WEIGHT) } ?: nil
                        "fontFamily" -> widget.style.fontFamily?.let { consume(it, WidgetValueType.FONT_FAMILY) } ?: nil
                        "letterSpacing" -> widget.style.letterSpacing ?: nil
                        "textDecoration" -> widget.style.textDecoration ?: nil
                        "textAlign" -> widget.style.textAlign ?: nil
                        "lineHeight" -> widget.style.lineHeight?.let { consume(it, WidgetValueType.LINE_HEIGHT) } ?: nil
                        "overflow" -> overflow
                        "maxLines" -> maxLines
                        "style" -> inherited
                        else -> error("Unsupported text style field: $name")
                    } }
                    val fallback = widget.style.fallbackColor?.let { consume(it, WidgetValueType.COLOR) }
                        ?: EtsLiteral(0xFF000000L, EtsTypes.NUMBER, at)
                    listOf(call("attributeModifier", listOf(etsTextStyleModifier(values + fallback, at)), at))
                }
                native("Text", listOf(text)).copy(attributes = listOf(
                    call("align", listOf(enumValue("Alignment", "TopStart", at)), at)) + attributes)
            }
            is Widget.Image -> {
                val accessibility = when (widget.contentDescription.type) {
                    EtsTypes.STRING -> call("accessibilityText", listOf(widget.contentDescription), at)
                    EtsTypes.NULL -> call("accessibilityLevel",
                        listOf(EtsLiteral("no", EtsTypes.STRING, at)), at)
                    else -> throw IllegalArgumentException(
                        "Image.contentDescription requires string or null at $at; got ${widget.contentDescription.type}")
                }
                when (val source = widget.image) {
                    is ImageSource.Resource -> {
                        expect(source.value, resourceType, "Image.resource", source.source)
                        require(widget.tint == null) { "Resource image tint requires an explicit backend capability at $at" }
                        native("Image", listOf(source.value)).copy(attributes = listOf(
                            call("objectFit", listOf(enumValue("ImageFit", "Contain", at)), at), accessibility))
                    }
                    is ImageSource.Url -> {
                        expect(source.value, EtsTypes.STRING, "Image.url", source.source)
                        require(widget.tint == null) { "URL image tint requires an explicit backend capability at $at" }
                        native("Image", listOf(source.value)).copy(attributes = listOf(
                            call("objectFit", listOf(enumValue("ImageFit", "Contain", at)), at), accessibility))
                    }
                    is ImageSource.Vector -> {
                        expect(source.value, etsImageVectorType, "Image.vector", source.source)
                        val resource = EtsMember(source.value, "resource",
                            etsImageVectorResourceType, source.source)
                        val tint = widget.tint?.let { consume(it, WidgetValueType.COLOR) }
                        native("SymbolGlyph", listOf(resource)).copy(attributes = listOf(
                            call("fontSize", listOf(EtsLiteral(24, EtsTypes.NUMBER, at)), at),
                            call("width", listOf(EtsLiteral(24, EtsTypes.NUMBER, at)), at),
                            call("height", listOf(EtsLiteral(24, EtsTypes.NUMBER, at)), at),
                            accessibility) + listOfNotNull(tint?.let { color -> call("fontColor",
                                listOf(EtsArray(listOf(color), EtsTypes.NUMBER, at)), at) }))
                    }
                }
            }
            is Widget.Button -> {
                val enabled = widget.enabled ?: EtsLiteral(true, EtsTypes.BOOLEAN, at)
                expect(enabled, EtsTypes.BOOLEAN, "Button.enabled", at)
                expect(widget.onClick, EtsFunctionType(emptyList(), EtsTypes.VOID), "Button.onClick", at)
                val content = native("Row", children = lower(widget.content, WidgetLayoutScope.ROW)).copy(attributes = listOf(
                    call("alignItems", listOf(enumValue("VerticalAlign", "Center", at)), at),
                    call("justifyContent", listOf(enumValue("FlexAlign", "Center", at)), at)))
                val attributes = if (widget.role == WidgetButtonRole.ICON) listOf(
                    call("onClick", listOf(widget.onClick), at),
                    call("type", listOf(enumValue("ButtonType", "Circle", at)), at),
                    call("backgroundColor", listOf(EtsLiteral(0, EtsTypes.NUMBER, at)), at),
                    call("width", listOf(EtsLiteral(48, EtsTypes.NUMBER, at)), at),
                    call("height", listOf(EtsLiteral(48, EtsTypes.NUMBER, at)), at),
                ) + if (widget.enabled == null) emptyList() else listOf(call("enabled", listOf(enabled), at))
                else buildList {
                    add(call("enabled", listOf(enabled), at))
                    add(call("onClick", listOf(widget.onClick), at))
                    widget.style?.let { style ->
                        style.containerColor?.let { add(call("backgroundColor",
                            listOf(consume(it, WidgetValueType.COLOR)), it.source)) }
                        style.contentPadding?.let {
                            expect(it, paddingType, "Button.contentPadding", style.source)
                            add(call("padding", listOf(it), style.source))
                        }
                        style.borderRadius?.let {
                            add(call("borderRadius", listOf(it), style.source))
                            add(call("clip", listOf(EtsLiteral(true, EtsTypes.BOOLEAN, style.source)), style.source))
                        }
                        style.border?.let { border ->
                            expect(border, borderStrokeType, "Button.border", style.source)
                            val borderFields = (border as? EtsObject)?.fields
                            val fields = linkedMapOf<String, EtsExpression>(
                                "width" to (borderFields?.get("width")
                                    ?: EtsMember(border, "width", EtsTypes.NUMBER, style.source)),
                                "color" to (borderFields?.get("color")
                                    ?: EtsMember(border, "color", EtsTypes.NUMBER, style.source)))
                            style.borderRadius?.let { fields["radius"] = it }
                            add(call("border", listOf(EtsObject(fields,
                                EtsRecordType("BorderOptions", fields.mapValues { it.value.type }), style.source)),
                                style.source))
                        }
                        val constraints = linkedMapOf<String, EtsExpression>()
                        style.minWidth?.let {
                            expect(it, EtsTypes.NUMBER, "Button.minWidth", style.source)
                            constraints["minWidth"] = it
                        }
                        style.minHeight?.let {
                            expect(it, EtsTypes.NUMBER, "Button.minHeight", style.source)
                            constraints["minHeight"] = it
                        }
                        if (constraints.isNotEmpty()) add(call("constraintSize", listOf(EtsObject(constraints,
                            EtsRecordType("ConstraintSizeOptions", constraints.mapValues { it.value.type }), style.source)),
                            style.source))
                        replaceableNativeDefaults += "height"
                        add(call("height", listOf(EtsLiteral("auto", EtsTypes.STRING, style.source)), style.source))
                    }
                }
                native("Button", children = listOf(content)).copy(attributes = attributes)
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
            is Widget.Row -> {
                val touchAttributes = widget.touchGroup?.let { group ->
                    expect(group.inset, EtsTypes.NUMBER, "TouchGroup.inset", group.source)
                    expect(group.targetWidth, EtsTypes.NUMBER, "TouchGroup.targetWidth", group.source)
                    expect(group.targetHeight, EtsTypes.NUMBER, "TouchGroup.targetHeight", group.source)
                    val itemType = EtsNamedType("TouchTestInfo")
                    val itemsType = EtsNamedType("Array", listOf(itemType))
                    val items = EtsSymbol("harmony-touch:${group.source.file}:${group.source.start}:items",
                        "items", itemsType, group.source)
                    val resultType = EtsNamedType("TouchResult")
                    val dispatch = EtsCall(EtsReference(EtsSymbol("compose:nearestTouch", "__etsNearestTouch",
                        EtsFunctionType(listOf(itemsType, EtsTypes.NUMBER, EtsTypes.NUMBER,
                            EtsTypes.NUMBER), resultType), group.source, true)),
                        listOf(EtsReference(items), group.inset, group.targetWidth, group.targetHeight),
                        resultType, group.source)
                    listOf(
                        call("responseRegion", listOf(rectangle(group.responseRegion)), group.source),
                        call("onChildTouchTest", listOf(EtsLambda(listOf(EtsParameter(items)),
                            listOf(EtsReturn(dispatch, group.source)), resultType, group.source)), group.source))
                }.orEmpty()
                val alignment = widget.verticalAlignment ?: enumValue("VerticalAlign", "Top", at)
                expect(alignment, EtsNamedType("VerticalAlign"), "Row.verticalAlignment", at)
                native("Row", layoutArguments("Row", widget.horizontalArrangement, at),
                    lower(widget.children, WidgetLayoutScope.ROW)).copy(attributes = listOf(
                    call("alignItems", listOf(alignment), at)) +
                    alignmentAttribute(widget.horizontalArrangement, at) + touchAttributes)
            }
            is Widget.Column -> {
                val alignment = widget.horizontalAlignment ?: enumValue("HorizontalAlign", "Start", at)
                expect(alignment, EtsNamedType("HorizontalAlign"), "Column.horizontalAlignment", at)
                native("Column", layoutArguments("Column", widget.verticalArrangement, at),
                    lower(widget.children, WidgetLayoutScope.COLUMN)).copy(attributes = listOf(
                    call("alignItems", listOf(alignment), at)) +
                    alignmentAttribute(widget.verticalArrangement, at))
            }
            is Widget.Box -> {
                widget.contentAlignment?.let {
                    expect(it, EtsNamedType("Alignment"), "Box.contentAlignment", at)
                }
                native("Stack", listOf(stackOptions(at, widget.contentAlignment)),
                    lower(widget.children, WidgetLayoutScope.BOX))
            }
            is Widget.Surface -> native("Stack", listOf(stackOptions(at)),
                lower(widget.children, WidgetLayoutScope.BOX)).copy(attributes = listOf(
                call("backgroundColor", listOf(consume(widget.background, WidgetValueType.COLOR)), at),
                call("clip", listOf(EtsLiteral(true, EtsTypes.BOOLEAN, at)), at)))
            is Widget.Spacer -> native("Blank")
            is Widget.Pager -> {
                expect(widget.currentPage, EtsTypes.NUMBER, "Pager.currentPage", at)
                expect(widget.pageCount, EtsTypes.NUMBER, "Pager.pageCount", at)
                expect(widget.controller, EtsNamedType("SwiperController"), "Pager.controller", at)
                expect(widget.enabled, EtsTypes.BOOLEAN, "Pager.enabled", at)
                expect(widget.onPageChange, EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.VOID),
                    "Pager.onPageChange", at)
                expect(widget.pageContent.index, EtsTypes.NUMBER, "Pager.pageContent.index", widget.pageContent.source)
                val index = widget.pageContent.index as? EtsReference
                    ?: throw IllegalArgumentException("Pager.pageContent.index requires a target binding at ${widget.pageContent.source}")
                val count = (widget.pageCount as? EtsLiteral)?.value as? Number
                val pages = if (count == null) {
                    val helper = pageIndices ?: pageIndicesFunction().also { pageIndices = it }
                    EtsCall(EtsReference(helper.symbol, at), listOf(widget.pageCount),
                        helper.returnType, at)
                } else {
                    require(count.toDouble().isFinite() && count.toDouble() % 1.0 == 0.0 && count.toInt() > 0) {
                        "Pager.pageCount requires a positive integer at $at"
                    }
                    EtsArray((0 until count.toInt()).map { EtsLiteral(it, EtsTypes.NUMBER, at) },
                        EtsTypes.NUMBER, at)
                }
                replaceableNativeDefaults += "width"
                native("Swiper", listOf(widget.controller), listOf(EtsUiForEach(pages,
                    EtsParameter(index.symbol), lower(widget.pageContent.children, null), widget.pageContent.source)))
                    .copy(attributes = listOf(
                        call("width", listOf(EtsLiteral("100%", EtsTypes.STRING, at)), at),
                        call("index", listOf(widget.currentPage), at),
                        call("loop", listOf(EtsLiteral(false, EtsTypes.BOOLEAN, at)), at),
                        call("indicator", listOf(EtsLiteral(false, EtsTypes.BOOLEAN, at)), at),
                        call("disableSwipe", listOf(EtsUnary("!", widget.enabled,
                            EtsTypes.BOOLEAN, at)), at),
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
            is Widget.TopAppBar -> {
                expect(widget.height, EtsTypes.NUMBER, "TopAppBar.height", at)
                val children = buildList {
                    widget.navigationIcon?.let { navigation ->
                        add(native("Row", children = lower(navigation, WidgetLayoutScope.ROW)).copy(attributes = listOf(
                            call("alignItems", listOf(enumValue("VerticalAlign", "Center", at)), at))))
                    }
                    add(native("Stack", listOf(stackOptions(at)), lower(widget.title, WidgetLayoutScope.BOX)).copy(
                        attributes = listOf(
                            call("layoutWeight", listOf(EtsLiteral(1, EtsTypes.NUMBER, at)), at),
                            call("height", listOf(widget.height), at),
                            call("alignContent", listOf(enumValue("Alignment", "CenterStart", at)), at))))
                    widget.actions?.let { actions ->
                        add(native("Row", children = lower(actions, WidgetLayoutScope.ROW)).copy(attributes = listOf(
                            call("alignItems", listOf(enumValue("VerticalAlign", "Center", at)), at))))
                    }
                }
                native("Row", children = children).copy(attributes = listOf(
                    call("height", listOf(widget.height), at),
                    call("alignItems", listOf(enumValue("VerticalAlign", "Center", at)), at),
                    call("backgroundColor", listOf(consume(widget.background, WidgetValueType.COLOR)), at)))
            }
            is Widget.Scaffold -> {
                val page = native("Stack", listOf(stackOptions(at)),
                    lower(widget.content, WidgetLayoutScope.BOX)).copy(attributes = listOf(
                    call("width", listOf(EtsLiteral("100%", EtsTypes.STRING, at)), at),
                    call("height", listOf(EtsLiteral("100%", EtsTypes.STRING, at)), at)))
                val layers = buildList {
                    add(page)
                    widget.topBar?.let { addAll(lower(it, WidgetLayoutScope.BOX)) }
                    widget.snackbarHost?.let { addAll(lower(it, WidgetLayoutScope.BOX)) }
                }
                native("Stack", listOf(stackOptions(at)), layers).copy(attributes = listOf(
                    call("backgroundColor", listOf(consume(widget.background, WidgetValueType.COLOR)), at)))
            }
            is Widget.SnackbarHost -> {
                expect(widget.state, snackbarHostStateType, "SnackbarHost.state", at)
                native("Stack", listOf(stackOptions(at)), emptyList())
            }
            is Widget.Conditional -> throw IllegalArgumentException(
                "Conditional widgets require a children boundary at $at")
            is Widget.ForEach -> throw IllegalArgumentException(
                "ForEach widgets require a children boundary at $at")
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
        data class ModifierLayer(val source: SourceSpan, val attributes: List<EtsCall> = emptyList(),
            val scroll: WidgetModifier.Scroll<EtsExpression, SourceSpan>? = null)
        val layers = mutableListOf<ModifierLayer>()
        var layerSource: SourceSpan? = null
        val layerAttributes = mutableListOf<EtsCall>()
        val seen = mutableSetOf<String>()
        var widthConstrained = false
        var heightConstrained = false
        fun flushLayer() {
            if (layerAttributes.isNotEmpty()) {
                layers += ModifierLayer(requireNotNull(layerSource), layerAttributes.toList())
                layerAttributes.clear()
                seen.clear()
                layerSource = null
            }
        }
        ordinary.forEach { modifier ->
            val source = modifier.source
            if (modifier is WidgetModifier.Scroll) {
                flushLayer()
                layers += ModifierLayer(source, scroll = modifier)
                return@forEach
            }
            val attributes = when (modifier) {
                is WidgetModifier.Size -> {
                    expect(modifier.width, EtsTypes.NUMBER, "Size.width", source)
                    expect(modifier.height, EtsTypes.NUMBER, "Size.height", source)
                    buildList {
                        if (!widthConstrained || !staticTargetEvaluation(modifier.width).canDiscard)
                            add(call("width", listOf(modifier.width), source))
                        if (!heightConstrained || !staticTargetEvaluation(modifier.height).canDiscard)
                            add(call("height", listOf(modifier.height), source))
                        widthConstrained = true
                        heightConstrained = true
                    }
                }
                is WidgetModifier.Width -> {
                    expect(modifier.value, EtsTypes.NUMBER, "Width.value", source)
                    buildList {
                        if (!widthConstrained || !staticTargetEvaluation(modifier.value).canDiscard)
                            add(call("width", listOf(modifier.value), source))
                        widthConstrained = true
                    }
                }
                is WidgetModifier.Height -> {
                    expect(modifier.value, EtsTypes.NUMBER, "Height.value", source)
                    buildList {
                        if (!heightConstrained || !staticTargetEvaluation(modifier.value).canDiscard)
                            add(call("height", listOf(modifier.value), source))
                        heightConstrained = true
                    }
                }
                is WidgetModifier.Padding -> {
                    val sides = linkedMapOf("left" to modifier.start, "top" to modifier.top,
                        "right" to modifier.end, "bottom" to modifier.bottom)
                    sides.forEach { (side, value) -> expect(value, EtsTypes.NUMBER, "Padding.$side", source) }
                    listOf(call("padding", listOf(EtsObject(sides,
                        EtsRecordType("Padding", sides.mapValues { EtsTypes.NUMBER }), source)), source))
                }
                is WidgetModifier.PaddingValues -> {
                    expect(modifier.value, paddingType, "PaddingValues.value", source)
                    listOf(call("padding", listOf(modifier.value), source))
                }
                is WidgetModifier.Fill -> {
                    expect(modifier.fraction, EtsTypes.NUMBER, "Fill.fraction", source)
                    val constant = (modifier.fraction as? EtsLiteral)?.value as? Number
                    require(constant == null || constant.toDouble().isFinite() && constant.toDouble() in 0.0..1.0) {
                        "Fill.fraction must be finite and between zero and one at $source"
                    }
                    val length = percentage(modifier.fraction, source)
                    buildList {
                        require(modifier.width || modifier.height) { "Fill requires at least one axis at $source" }
                        if (modifier.width && (!widthConstrained ||
                                !staticTargetEvaluation(modifier.fraction).canDiscard))
                            add(call("width", listOf(length), source))
                        if (modifier.height && (!heightConstrained ||
                                !staticTargetEvaluation(modifier.fraction).canDiscard))
                            add(call("height", listOf(length), source))
                        widthConstrained = widthConstrained || modifier.width
                        heightConstrained = heightConstrained || modifier.height
                    }
                }
                is WidgetModifier.Weight -> {
                    error("Scoped modifier remained in ordinary widget modifiers")
                }
                is WidgetModifier.Align -> {
                    error("Scoped modifier remained in ordinary widget modifiers")
                }
                is WidgetModifier.Background -> {
                    val color = consume(modifier.color, WidgetValueType.COLOR)
                    listOf(call("backgroundColor", listOf(color), source)) + modifier.borderRadius?.let {
                        listOf(call("borderRadius", listOf(it), source))
                    }.orEmpty()
                }
                is WidgetModifier.Clip -> {
                    listOf(call("borderRadius", listOf(modifier.borderRadius), source),
                        call("clip", listOf(EtsLiteral(true, EtsTypes.BOOLEAN, source)), source))
                }
                is WidgetModifier.Tag -> {
                    expect(modifier.value, EtsTypes.STRING, "Tag.value", source)
                    listOf(call("id", listOf(modifier.value), source))
                }
                is WidgetModifier.Click -> {
                    expect(modifier.onClick, EtsFunctionType(emptyList(), EtsTypes.VOID), "Click.onClick", source)
                    val enabled = modifier.enabled ?: EtsLiteral(true, EtsTypes.BOOLEAN, source)
                    expect(enabled, EtsTypes.BOOLEAN, "Click.enabled", source)
                    listOf(call("enabled", listOf(enabled), source),
                        call("onClick", listOf(modifier.onClick), source)) + modifier.touchTarget?.let { target ->
                        expect(target.id, EtsTypes.STRING, "TouchTarget.id", target.source)
                        listOf(call("id", listOf(target.id), target.source),
                            call("responseRegion", listOf(rectangle(target.responseRegion)), target.source),
                            call("mouseResponseRegion", listOf(rectangle(target.mouseResponseRegion)), target.source))
                    }.orEmpty()
                }
                is WidgetModifier.Scroll -> error("Scroll modifier bypassed its native wrapper")
                is WidgetModifier.Conditional -> error("Conditional modifier bypassed its statement boundary")
            }
            if (attributes.isEmpty()) return@forEach
            val keys = attributes.map { (it.callee as EtsReference).symbol.name }.toSet()
            if ("padding" in seen || keys.any { it in seen } ||
                modifier is WidgetModifier.Clip && "backgroundColor" in seen) flushLayer()
            if (layerSource == null) layerSource = source
            layerAttributes += attributes
            seen += keys
        }
        flushLayer()
        val wrapped = layers.asReversed().foldIndexed(element) { index, child, layer ->
            layer.scroll?.let { modifier ->
                val source = modifier.source
                expect(modifier.offset, EtsTypes.NUMBER, "Scroll.offset", source)
                expect(modifier.enabled, EtsTypes.BOOLEAN, "Scroll.enabled", source)
                modifier.onScroll?.let { onScroll -> expect(onScroll,
                    EtsFunctionType(listOf(EtsTypes.NUMBER, EtsTypes.NUMBER), EtsTypes.VOID),
                    "Scroll.onScroll", source) }
                val zero = EtsLiteral(0, EtsTypes.NUMBER, source)
                val offsets = if (modifier.axis == WidgetScrollAxis.VERTICAL)
                    linkedMapOf("xOffset" to zero, "yOffset" to modifier.offset)
                else linkedMapOf("xOffset" to modifier.offset, "yOffset" to zero)
                val attributes = mutableListOf(
                    call("scrollable", listOf(enumValue("ScrollDirection",
                        if (modifier.axis == WidgetScrollAxis.VERTICAL) "Vertical" else "Horizontal", source)), source),
                    call("initialOffset", listOf(EtsObject(offsets,
                        EtsRecordType("OffsetOptions", offsets.mapValues { EtsTypes.NUMBER }), source)), source),
                    call("scrollBar", listOf(enumValue("BarState", "Off", source)), source),
                    call("enableScrollInteraction", listOf(modifier.enabled), source),
                    call("align", listOf(enumValue("Alignment", "TopStart", source)), source))
                modifier.onScroll?.let { attributes += call("onScroll", listOf(it), source) }
                return@foldIndexed EtsUiElement(call("Scroll", emptyList(), source), listOf(child), attributes)
            }
            val existing = child.attributes.mapNotNull { (it.callee as? EtsReference)?.symbol?.name }.toSet()
            val incoming = layer.attributes.map { (it.callee as EtsReference).symbol.name }.toSet()
            val conflicts = existing intersect incoming
            if (index == 0 && conflicts.all { it in replaceableNativeDefaults }) {
                child.copy(attributes = child.attributes.filterNot {
                    (it.callee as? EtsReference)?.symbol?.name in conflicts
                } + layer.attributes)
            } else EtsUiElement(call("Stack", listOf(stackOptions(layer.source)), layer.source),
                listOf(child), layer.attributes)
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

    private fun rectangle(value: WidgetRectangle<EtsExpression, SourceSpan>): EtsObject {
        val fields = linkedMapOf("x" to value.x, "y" to value.y,
            "width" to value.width, "height" to value.height)
        return EtsObject(fields, EtsRecordType("Rectangle", fields.mapValues { it.value.type }), value.source)
    }

    private fun pageIndicesFunction(): EtsFunction {
        val at = SourceSpan("EtsComposePagerSupport.kt", 0, 0)
        val arrayType = EtsNamedType("Array", listOf(EtsTypes.NUMBER))
        fun symbol(name: String, type: EtsType) = EtsSymbol("compose-pager:$name", name, type, at)
        fun number(value: Int) = EtsLiteral(value, EtsTypes.NUMBER, at)
        val count = EtsParameter(symbol("count", EtsTypes.NUMBER))
        val values = symbol("values", arrayType)
        val index = symbol("index", EtsTypes.NUMBER)
        val valuesRef = EtsReference(values)
        val indexRef = EtsReference(index)
        val positive = EtsBinary("<=", EtsReference(count.symbol), number(0), EtsTypes.BOOLEAN, at)
        val error = EtsNew(EtsNamedType("Error", symbolId = "native:Error", external = true),
            listOf(EtsLiteral("Pager pageCount must be positive", EtsTypes.STRING, at)), at)
        val push = EtsCall(EtsMember(valuesRef, "push",
            EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.NUMBER), at),
            listOf(indexRef), EtsTypes.NUMBER, at)
        val increment = EtsAssignment(indexRef,
            EtsBinary("+", indexRef, number(1), EtsTypes.NUMBER, at), at)
        return EtsFunction("__etsPageIndices", listOf(count), arrayType, listOf(
            EtsIf(listOf(EtsBranch(positive, listOf(EtsThrow(error, at)))), at),
            EtsVariable(values, EtsArray(emptyList(), EtsTypes.NUMBER, at), mutable = false),
            EtsVariable(index, number(0), mutable = true),
            EtsLoop("pageIndices", EtsBinary("<", indexRef, EtsReference(count.symbol),
                EtsTypes.BOOLEAN, at), listOf(EtsExpressionStatement(push),
                EtsExpressionStatement(increment)), doWhile = false, at),
            EtsReturn(valuesRef, at)), at, exported = true)
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
        etsStableMember(EtsReference(EtsSymbol("arkui:$type", type, EtsNamedType(type), at, true)),
            name, EtsNamedType(type), at)

    private fun layoutArguments(control: String,
        arrangement: WidgetMainAxisArrangement<EtsExpression, SourceSpan>?, at: SourceSpan): List<EtsExpression> =
        if (arrangement !is WidgetMainAxisArrangement.Spacing) emptyList() else {
            expect(arrangement.value, EtsTypes.NUMBER, "${control}.spacing", arrangement.source)
            listOf(EtsObject(mapOf("space" to arrangement.value),
                EtsRecordType("${control}Options", mapOf("space" to EtsTypes.NUMBER)), at))
        }

    private fun alignmentAttribute(arrangement: WidgetMainAxisArrangement<EtsExpression, SourceSpan>?,
        at: SourceSpan): List<EtsCall> = if (arrangement !is WidgetMainAxisArrangement.Alignment) emptyList() else {
        val name = when (arrangement.alignment) {
            WidgetMainAxisAlignment.START -> "Start"
            WidgetMainAxisAlignment.CENTER -> "Center"
            WidgetMainAxisAlignment.END -> "End"
            WidgetMainAxisAlignment.SPACE_BETWEEN -> "SpaceBetween"
            WidgetMainAxisAlignment.SPACE_AROUND -> "SpaceAround"
            WidgetMainAxisAlignment.SPACE_EVENLY -> "SpaceEvenly"
        }
        listOf(call("justifyContent", listOf(enumValue("FlexAlign", name, at)), at))
    }

    private fun stackOptions(at: SourceSpan, alignment: EtsExpression? = null): EtsExpression = EtsObject(
        mapOf("alignContent" to (alignment ?: enumValue("Alignment", "TopStart", at))),
        EtsRecordType("StackOptions", mapOf("alignContent" to EtsNamedType("Alignment"))), at)

    private companion object {
        val resourceType = EtsNamedType("Resource", external = true)
    }
}
