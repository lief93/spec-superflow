package dev.ets.widgettest

import dev.ets.*
import dev.ets.harmony.HarmonyWidgetBackend
import dev.ets.widgets.*

fun main() {
    // Runs with only model, target, backend and Kotlin stdlib: no compiler or Compose.
    val source = SourceSpan("model-only", 1, 2)
    fun number(value: Int) = EtsLiteral(value, EtsTypes.NUMBER, source)
    check(staticTargetEvaluation(number(1)).canDiscard)
    val runtimeOwner = EtsReference(EtsSymbol("test:runtime", "runtime", EtsTypes.OBJECT, source))
    val mutableReference = EtsReference(EtsSymbol("test:mutable", "mutable", EtsTypes.STRING, source,
        evaluation = EtsEvaluationSemantics(EtsObservableEffect.READS_RUNTIME)))
    check(staticTargetEvaluation(mutableReference).effect == EtsObservableEffect.READS_RUNTIME)
    check(staticTargetEvaluation(EtsMember(runtimeOwner, "value", EtsTypes.NUMBER, source)).effect ==
        EtsObservableEffect.READS_RUNTIME)
    check(!staticTargetEvaluation(EtsArray(listOf(number(1)), EtsTypes.NUMBER, source)).canDuplicate)
    check(staticTargetEvaluation(EtsAssignment(runtimeOwner, runtimeOwner, source)).effect ==
        EtsObservableEffect.WRITES_RUNTIME)
    fun string(value: String, provenance: WidgetValueProvenance = WidgetValueProvenance.Literal) =
        WidgetValue<EtsExpression, SourceSpan>(WidgetValueType.STRING,
            EtsLiteral(value, EtsTypes.STRING, source), provenance, source)
    fun color(value: Int, provenance: WidgetValueProvenance = WidgetValueProvenance.Literal) =
        WidgetValue<EtsExpression, SourceSpan>(WidgetValueType.COLOR, number(value), provenance, source)
    val noStyle = WidgetTextStyle<EtsExpression, SourceSpan>(null, null, null, null)
    val text = Widget.Text<EtsExpression, SourceSpan>(string("direct"), noStyle, listOf(
        WidgetModifier.Width(number(100), source),
        WidgetModifier.Padding(number(1), number(2), number(3), number(4), source),
        WidgetModifier.Width(number(40), source)), source)
    val backend = HarmonyWidgetBackend()
    val element = backend.lower(text)
    fun name(element: EtsUiElement) = (element.call.callee as EtsReference).symbol.name
    fun attribute(element: EtsUiElement) = (element.attributes.single().callee as EtsReference).symbol.name
    check(name(element) == "Text")
    check(element.attributes.map { (it.callee as EtsReference).symbol.name } == listOf("align", "width", "padding"))
    check((element.attributes.single { (it.callee as EtsReference).symbol.name == "width" }
        .arguments.single() as EtsLiteral).value == 100)
    val sides = element.attributes.single { (it.callee as EtsReference).symbol.name == "padding" }
        .arguments.single() as EtsObject
    check(sides.fields.mapValues { (it.value as EtsLiteral).value } == mapOf("left" to 1, "top" to 2, "right" to 3, "bottom" to 4))
    val alignmentType = EtsNamedType("Alignment")
    val alignment = etsStableMember(EtsReference(EtsSymbol("arkui:Alignment", "Alignment", alignmentType,
        source, external = true)), "BottomEnd", alignmentType, source)
    check(staticTargetEvaluation(alignment).canReorder)
    val readSource = SourceSpan("model-only", 10, 11)
    val effectSource = SourceSpan("model-only", 20, 21)
    val runtimeText = EtsMember(runtimeOwner, "text", EtsTypes.STRING, readSource)
    val effectSize = EtsCall(EtsReference(EtsSymbol("test:effectSize", "effectSize",
        EtsFunctionType(emptyList(), EtsTypes.NUMBER), effectSource, external = true)),
        emptyList(), EtsTypes.NUMBER, effectSource)
    val orderedText = Widget.Text(
        WidgetValue(WidgetValueType.STRING, runtimeText, WidgetValueProvenance.Expression("runtime.text"), readSource),
        WidgetTextStyle(WidgetValue(WidgetValueType.FONT_SIZE, effectSize,
            WidgetValueProvenance.Expression("effectSize()"), effectSource), null, null, null),
        emptyList(), source, sourceEvaluations = listOf(runtimeText, effectSize))
    val textRead = backend.lower(Children(listOf(orderedText))).single() as EtsUiForEach
    check(textRead.kind == EtsUiForEachKind.SOURCE_EVALUATION)
    check((textRead.items as EtsArray).elements.single() == runtimeText)
    val sizeEffect = textRead.body.single() as EtsUiForEach
    check(sizeEffect.kind == EtsUiForEachKind.SOURCE_EVALUATION)
    check((sizeEffect.items as EtsArray).elements.single() == effectSize)
    val orderedTarget = sizeEffect.body.single() as EtsUiElement
    check(orderedTarget.call.arguments.single() == EtsReference(textRead.item.symbol))
    check(orderedTarget.attributes.single { (it.callee as EtsReference).symbol.name == "fontSize" }
        .arguments.single() == EtsReference(sizeEffect.item.symbol))
    val mutableText = Widget.Text(
        WidgetValue(WidgetValueType.STRING, mutableReference,
            WidgetValueProvenance.Expression("mutable"), source), noStyle,
        emptyList(), source, sourceEvaluations = listOf(mutableReference))
    val mutableRead = backend.lower(Children(listOf(mutableText))).single()
    check(mutableRead is EtsUiForEach && mutableRead.kind == EtsUiForEachKind.SOURCE_EVALUATION)
    val simplifiedMutableRead = simplifyPureUiEvaluationBindings(EtsProgram(listOf(EtsFile("model-only", listOf(
        EtsFunction("MutableRead", emptyList(), EtsTypes.VOID, listOf(mutableRead), source, builder = true))))))
        .files.single().declarations.single() as EtsFunction
    check(simplifiedMutableRead.body.single() is EtsUiForEach)
    val firstRead = mutableReference.copy(source = SourceSpan("model-only", 30, 31))
    val middleEffect = effectSize.copy(source = SourceSpan("model-only", 40, 41))
    val secondRead = mutableReference.copy(source = SourceSpan("model-only", 50, 51))
    val rereadText = Widget.Text(
        WidgetValue(WidgetValueType.STRING, firstRead,
            WidgetValueProvenance.Expression("mutable"), firstRead.source),
        WidgetTextStyle(WidgetValue(WidgetValueType.FONT_SIZE, middleEffect,
            WidgetValueProvenance.Expression("effectSize()"), middleEffect.source), null,
            WidgetValue(WidgetValueType.FONT_FAMILY, secondRead,
                WidgetValueProvenance.Expression("mutable"), secondRead.source), null),
        emptyList(), source, sourceEvaluations = listOf(firstRead, middleEffect, secondRead))
    val firstReadBinding = backend.lower(Children(listOf(rereadText))).single() as EtsUiForEach
    val middleEffectBinding = firstReadBinding.body.single() as EtsUiForEach
    val secondReadBinding = middleEffectBinding.body.single() as EtsUiForEach
    check(listOf(firstReadBinding, middleEffectBinding, secondReadBinding).map {
        ((it.items as EtsArray).elements.single()).source.start
    } == listOf(30, 40, 50))
    val rereadTarget = secondReadBinding.body.single() as EtsUiElement
    check(rereadTarget.call.arguments.single() == EtsReference(firstReadBinding.item.symbol))
    check(rereadTarget.attributes.single { (it.callee as EtsReference).symbol.name == "fontSize" }
        .arguments.single() == EtsReference(middleEffectBinding.item.symbol))
    check(rereadTarget.attributes.single { (it.callee as EtsReference).symbol.name == "fontFamily" }
        .arguments.single() == EtsReference(secondReadBinding.item.symbol))
    val rowChild = Widget.Text(string("row child"), noStyle, listOf(
        WidgetModifier.Fill<EtsExpression, SourceSpan>(true, false, EtsLiteral(0.5, EtsTypes.NUMBER, source), source),
        WidgetModifier.Weight(number(2), WidgetLayoutScope.ROW, source)), source)
    val rowLayout = backend.lower(Widget.Row(Children(listOf(rowChild)), emptyList(), source))
    val weightLayer = rowLayout.children!!.single() as EtsUiElement
    check(attribute(weightLayer) == "layoutWeight")
    val fillLayer = weightLayer.children!!.single() as EtsUiElement
    check(fillLayer.attributes.map { (it.callee as EtsReference).symbol.name } == listOf("align", "width"))
    check((fillLayer.attributes.single { (it.callee as EtsReference).symbol.name == "width" }
        .arguments.single() as EtsLiteral).value == "50.0%")
    val centeredColumn = backend.lower(Widget.Column(Children(emptyList()), emptyList(), source,
        WidgetMainAxisArrangement.Alignment(WidgetMainAxisAlignment.CENTER, source),
        EtsMember(EtsReference(EtsSymbol("arkui:HorizontalAlign", "HorizontalAlign",
            EtsNamedType("HorizontalAlign"), source, true)), "Center", EtsNamedType("HorizontalAlign"), source)))
    check(centeredColumn.attributes.map { (it.callee as EtsReference).symbol.name } ==
        listOf("alignItems", "justifyContent"))
    check((centeredColumn.attributes.last().arguments.single() as EtsMember).name == "Center")
    val boxChild = Widget.Text(string("box child"), noStyle, listOf(
        WidgetModifier.Align<EtsExpression, SourceSpan>(alignment, WidgetLayoutScope.BOX, source),
        WidgetModifier.Fill(true, true, number(1), source)), source)
    val boxLayout = backend.lower(Widget.Box(Children(listOf(boxChild)), emptyList(), source))
    val alignLayer = boxLayout.children!!.single() as EtsUiElement
    check(attribute(alignLayer) == "align" && alignLayer.attributes.single().arguments.single() == alignment)
    check((alignLayer.children!!.single() as EtsUiElement).attributes.map {
        (it.callee as EtsReference).symbol.name } == listOf("align", "width", "height"))
    val wrongParent = Widget.Column(Children(listOf(rowChild)), emptyList(), source)
    check(runCatching { backend.lower(wrongParent) }.exceptionOrNull() is IllegalArgumentException)
    val invalidFill = Widget.Text(string("bad fill"), noStyle, listOf(
        WidgetModifier.Fill<EtsExpression, SourceSpan>(true, false,
            EtsLiteral("bad", EtsTypes.STRING, source), source)), source)
    check(runCatching { backend.lower(invalidFill) }.exceptionOrNull() is IllegalArgumentException)
    val invalidFraction = Widget.Text(string("bad fraction"), noStyle, listOf(
        WidgetModifier.Fill<EtsExpression, SourceSpan>(true, false,
            EtsLiteral(2.0, EtsTypes.NUMBER, source), source)), source)
    check(runCatching { backend.lower(invalidFraction) }.exceptionOrNull() is IllegalArgumentException)
    val invalidWeight = Widget.Row(Children(listOf(Widget.Text(string("bad weight"), noStyle,
        listOf(WidgetModifier.Weight<EtsExpression, SourceSpan>(
            EtsLiteral(-1, EtsTypes.NUMBER, source), WidgetLayoutScope.ROW, source)), source))), emptyList(), source)
    check(runCatching { backend.lower(invalidWeight) }.exceptionOrNull() is IllegalArgumentException)
    val click = EtsLambda(emptyList(), emptyList(), EtsTypes.VOID, source)
    val sharedColor = color(7, WidgetValueProvenance.ThemeToken("sample.brand"))
    val shared: List<WidgetModifier<EtsExpression, SourceSpan>> = listOf(
        WidgetModifier.Size(number(48), number(32), source),
        WidgetModifier.Background(sharedColor, source),
        WidgetModifier.Click(click, EtsLiteral(false, EtsTypes.BOOLEAN, source), source),
        WidgetModifier.Padding(number(1), number(1), number(1), number(1), source))
    val sharedText = string("styled", WidgetValueProvenance.Resource("sample.R.string.styled"))
    val sharedStyle = WidgetTextStyle<EtsExpression, SourceSpan>(
        WidgetValue(WidgetValueType.FONT_SIZE, number(18), WidgetValueProvenance.Literal, source),
        WidgetValue(WidgetValueType.FONT_WEIGHT, number(700),
            WidgetValueProvenance.Resource("FontWeight.Bold"), source),
        WidgetValue(WidgetValueType.FONT_FAMILY, EtsLiteral("monospace", EtsTypes.STRING, source),
            WidgetValueProvenance.Resource("FontFamily.Monospace"), source),
        WidgetValue(WidgetValueType.LINE_HEIGHT, number(24), WidgetValueProvenance.Expression("lineHeight"), source))
    val styledText = backend.lower(Widget.Text(sharedText, sharedStyle, shared, source))
    val button = Widget.Button<EtsExpression, SourceSpan>(click, null,
        Children(listOf(Widget.Text(sharedText, sharedStyle, emptyList(), source))),
        listOf(WidgetModifier.Background(sharedColor, source)), source)
    val styledButton = backend.lower(button)
    check(styledButton.attributes.single { (it.callee as EtsReference).symbol.name == "backgroundColor" }
        .arguments.single() == sharedColor.value)
    val buttonRow = styledButton.children!!.single() as EtsUiElement
    val buttonText = buttonRow.children!!.single() as EtsUiElement
    check(buttonText.call.arguments.single() == sharedText.value)
    check(buttonText.attributes.map { (it.callee as EtsReference).symbol.name } ==
        listOf("align", "fontSize", "fontWeight", "fontFamily", "lineHeight"))
    val explicitlySizedButton = backend.lower(Widget.Button(click, null, Children(emptyList()), listOf(
        WidgetModifier.Width<EtsExpression, SourceSpan>(number(100), source),
        WidgetModifier.Height<EtsExpression, SourceSpan>(number(48), source)), source,
        style = WidgetButtonStyle(null, null, null, null, null, null, textual = false, source = source)))
    check(name(explicitlySizedButton) == "Button")
    check(explicitlySizedButton.attributes.map { (it.callee as EtsReference).symbol.name }
        .takeLast(2) == listOf("width", "height"))
    check((explicitlySizedButton.attributes.last().arguments.single() as EtsLiteral).value == 48)
    val invalid = Widget.Text<EtsExpression, SourceSpan>(
        WidgetValue(WidgetValueType.STRING, number(1), WidgetValueProvenance.Expression(null), source), noStyle,
        emptyList(), source)
    check(runCatching { backend.lower(invalid) }.exceptionOrNull() is IllegalArgumentException)
    val invalidSemantic = Widget.Text<EtsExpression, SourceSpan>(
        WidgetValue(WidgetValueType.COLOR, EtsLiteral("bad", EtsTypes.STRING, source),
            WidgetValueProvenance.Literal, source), noStyle, emptyList(), source)
    check(runCatching { backend.lower(invalidSemantic) }.exceptionOrNull() is IllegalArgumentException)
    val invalidStyle = Widget.Text(string("bad style"), WidgetTextStyle(
        null, null, WidgetValue(WidgetValueType.FONT_FAMILY, number(1),
            WidgetValueProvenance.Expression(null), source), null), emptyList(), source)
    check(runCatching { backend.lower(invalidStyle) }.exceptionOrNull() is IllegalArgumentException)
    val invalidStyleSemantic = Widget.Text(string("bad style semantic"), WidgetTextStyle(
        WidgetValue(WidgetValueType.FONT_WEIGHT, number(18), WidgetValueProvenance.Literal, source),
        null, null, null), emptyList(), source)
    check(runCatching { backend.lower(invalidStyleSemantic) }.exceptionOrNull() is IllegalArgumentException)
    val invalidButton = Widget.Button<EtsExpression, SourceSpan>(number(1), null, Children(emptyList()), emptyList(), source)
    check(runCatching { backend.lower(invalidButton) }.exceptionOrNull() is IllegalArgumentException)
    val resource = EtsReference(EtsSymbol("test:resource", "resource",
        EtsNamedType("Resource", external = true), source, external = true))
    val styledImage = backend.lower(Widget.Image(ImageSource.Resource(resource, source),
        EtsLiteral("Styled", EtsTypes.STRING, source), shared, source))
    fun attributes(element: EtsUiElement) = element.attributes.map { (it.callee as EtsReference).symbol.name }
    for (styled in listOf(styledText, styledImage)) {
        check(attributes(styled).takeLast(6) == listOf(
            "width", "height", "backgroundColor", "enabled", "onClick", "padding"))
        check(styled.attributes.single { (it.callee as EtsReference).symbol.name == "onClick" }
            .arguments.single() == click)
    }
    check(name(styledText) == "Text")
    check(name(styledImage) == "Image")
    val resourceImage = backend.lower(Widget.Image(ImageSource.Resource(resource, source),
        EtsLiteral("Local", EtsTypes.STRING, source), emptyList(), source))
    val urlImage = backend.lower(Widget.Image(ImageSource.Url(EtsLiteral("https://example.invalid/a.png",
        EtsTypes.STRING, source), source), EtsLiteral(null, EtsTypes.NULL, source), emptyList(), source))
    check((resourceImage.call.callee as EtsReference).symbol.name == "Image")
    check(resourceImage.call.arguments.single() == resource)
    check((urlImage.attributes.single { (it.callee as EtsReference).symbol.name == "accessibilityLevel" }
        .arguments.single() as EtsLiteral).value == "no")
    val changed = EtsParameter(EtsSymbol("test:changed", "changed", EtsTypes.STRING, source))
    val onChange = EtsLambda(listOf(changed), emptyList(), EtsTypes.VOID, source)
    val textField = backend.lower(Widget.TextField(EtsLiteral("value", EtsTypes.STRING, source),
        onChange, EtsLiteral(false, EtsTypes.BOOLEAN, source), emptyList(), source))
    check((textField.call.callee as EtsReference).symbol.name == "TextInput")
    check((textField.call.arguments.single() as EtsObject).fields["text"] == EtsLiteral("value", EtsTypes.STRING, source))
    check(textField.attributes.single { (it.callee as EtsReference).symbol.name == "onChange" }
        .arguments.single() == onChange)
    val currentPage = EtsReference(EtsSymbol("test:currentPage", "currentPage", EtsTypes.NUMBER,
        source, external = true))
    val controllerType = EtsNamedType("SwiperController")
    val controller = EtsReference(EtsSymbol("test:controller", "controller", controllerType,
        source, external = true))
    val page = EtsReference(EtsSymbol("test:page", "page", EtsTypes.NUMBER, source))
    val changedPage = EtsParameter(EtsSymbol("test:changedPage", "index", EtsTypes.NUMBER, source))
    val pageChanged = EtsLambda(listOf(changedPage), listOf(EtsExpressionStatement(
        EtsAssignment(currentPage, EtsReference(changedPage.symbol), source))), EtsTypes.VOID, source)
    val pagerWidget = Widget.Pager(currentPage, number(3), controller,
        EtsLiteral(true, EtsTypes.BOOLEAN, source), pageChanged,
        IndexedChildren(page, Children(listOf(Widget.Text(string("page"), noStyle, emptyList(), source))), source),
        emptyList(), source)
    val pager = backend.lower(pagerWidget)
    check(name(pager) == "Swiper")
    check(pager.attributes.map { (it.callee as EtsReference).symbol.name } ==
        listOf("width", "index", "loop", "indicator", "disableSwipe", "onChange"))
    val pageLoop = pager.children!!.single() as EtsUiForEach
    check((pageLoop.items as EtsArray).elements.map { (it as EtsLiteral).value } == listOf(0, 1, 2))
    check(pageLoop.item.symbol == page.symbol)
    val sizedPager = backend.lower(pagerWidget.copy(modifiers = listOf(
        WidgetModifier.Fill<EtsExpression, SourceSpan>(true, false, number(1), source))))
    check(name(sizedPager) == "Swiper")
    check(attributes(sizedPager).count { it == "width" } == 1)
    val scrollOffset = EtsReference(EtsSymbol("test:scrollOffset", "scrollOffset", EtsTypes.NUMBER,
        source, external = true))
    val xOffset = EtsParameter(EtsSymbol("test:xOffset", "xOffset", EtsTypes.NUMBER, source))
    val yOffset = EtsParameter(EtsSymbol("test:yOffset", "yOffset", EtsTypes.NUMBER, source))
    val onScroll = EtsLambda(listOf(xOffset, yOffset), listOf(EtsExpressionStatement(
        EtsAssignment(scrollOffset, EtsReference(yOffset.symbol), source))), EtsTypes.VOID, source)
    val scroll = backend.lower(Widget.Text(string("scroll"), noStyle,
        listOf(WidgetModifier.Scroll(WidgetScrollAxis.VERTICAL, scrollOffset, onScroll,
            EtsLiteral(true, EtsTypes.BOOLEAN, source), source)), source))
    check(name(scroll) == "Scroll")
    check(scroll.children!!.single() is EtsUiElement)
    check(attributes(scroll) ==
        listOf("scrollable", "initialOffset", "scrollBar", "enableScrollInteraction", "align", "onScroll"))
    val initialOffset = scroll.attributes.single { (it.callee as EtsReference).symbol.name == "initialOffset" }
        .arguments.single() as EtsObject
    check(initialOffset.fields == mapOf("xOffset" to number(0), "yOffset" to scrollOffset))
    val invalidUrl = Widget.Image<EtsExpression, SourceSpan>(ImageSource.Url(number(1), source),
        EtsLiteral(null, EtsTypes.NULL, source), emptyList(), source)
    check(runCatching { backend.lower(invalidUrl) }.exceptionOrNull() is IllegalArgumentException)
    val invalidDescription = Widget.Image(ImageSource.Resource(resource, source), number(1), emptyList(), source)
    check(runCatching { backend.lower(invalidDescription) }.exceptionOrNull() is IllegalArgumentException)
    val invalidField = Widget.TextField<EtsExpression, SourceSpan>(EtsLiteral("value", EtsTypes.STRING, source), number(1),
        null, emptyList(), source)
    check(runCatching { backend.lower(invalidField) }.exceptionOrNull() is IllegalArgumentException)
    val invalidSize = Widget.Text(string("x"), noStyle,
        listOf(WidgetModifier.Size<EtsExpression, SourceSpan>(number(1),
            EtsLiteral("bad", EtsTypes.STRING, source), source)), source)
    check(runCatching { backend.lower(invalidSize) }.exceptionOrNull() is IllegalArgumentException)
    val invalidBackground = Widget.Text(string("x"), noStyle,
        listOf(WidgetModifier.Background<EtsExpression, SourceSpan>(
            WidgetValue(WidgetValueType.COLOR, EtsLiteral("bad", EtsTypes.STRING, source),
                WidgetValueProvenance.Expression(null), source), source)), source)
    check(runCatching { backend.lower(invalidBackground) }.exceptionOrNull() is IllegalArgumentException)
    val invalidClick = Widget.Text(string("x"), noStyle,
        listOf(WidgetModifier.Click<EtsExpression, SourceSpan>(number(1), null, source)), source)
    check(runCatching { backend.lower(invalidClick) }.exceptionOrNull() is IllegalArgumentException)
    val conditional = backend.lower(Children(listOf(Widget.Conditional(listOf(
        WidgetBranch(EtsLiteral(true, EtsTypes.BOOLEAN, source),
            Children(listOf(Widget.Text(string("yes"), noStyle, emptyList(), source))), source),
        WidgetBranch(null,
            Children(listOf(Widget.Text(string("no"), noStyle, emptyList(), source))), source),
    ), source)))).single() as EtsIf
    check(conditional.branches.size == 2 && conditional.branches.last().condition == null)
    check(conditional.branches.all { it.body.single() is EtsUiElement })
    val invalidConditional: Children<EtsExpression, SourceSpan> = Children(listOf(Widget.Conditional(listOf(
        WidgetBranch(number(1), Children(emptyList()), source)), source)))
    check(runCatching { backend.lower(invalidConditional) }.exceptionOrNull() is IllegalArgumentException)
    val themeType = EtsNamedType("ThemeContext")
    val themeReference = EtsReference(EtsSymbol("test:theme-context", "themeContext",
        themeType, source))
    val theme = EtsReference(EtsSymbol("test:theme", "theme", themeType, source, true))
    val themeBoundary = backend.lower(Children(listOf(Widget.ThemeProvider(themeReference, theme,
        Children(listOf(Widget.Text(string("themed"), noStyle, emptyList(), source))), source)))).single()
        as EtsUiForEach
    check(themeBoundary.item.symbol == themeReference.symbol)
    val themeArray = themeBoundary.items as EtsArray
    check(themeArray.elements.single() == theme)
    check((themeBoundary.body.single() as EtsUiElement).call.arguments.single() ==
        EtsLiteral("themed", EtsTypes.STRING, source))
    val fn = EtsFunction("view", emptyList(), EtsTypes.VOID,
        listOf(element, rowLayout, boxLayout, styledText, styledButton, styledImage,
            resourceImage, urlImage, textField, pager, scroll, conditional, themeBoundary),
        source, builder = true)
    EtsValidator().validate(EtsProgram(listOf(EtsFile("model-only", listOf(fn)))))
    println("PASS backend without compiler/Compose; shared values, scoped layout modifiers, runtime branches and typed rejection")
}
