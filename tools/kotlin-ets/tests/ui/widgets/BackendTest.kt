package dev.ets.widgettest

import dev.ets.*
import dev.ets.harmony.HarmonyWidgetBackend
import dev.ets.widgets.*

fun main() {
    // Runs with only model, target, backend and Kotlin stdlib: no compiler or Compose.
    val source = SourceSpan("model-only", 1, 2)
    fun number(value: Int) = EtsLiteral(value, EtsTypes.NUMBER, source)
    val text = Widget.Text<EtsExpression, SourceSpan>(EtsLiteral("direct", EtsTypes.STRING, source), listOf(
        WidgetModifier.Width(number(100), source),
        WidgetModifier.Padding(number(1), number(2), number(3), number(4), source),
        WidgetModifier.Width(number(40), source)), source)
    val backend = HarmonyWidgetBackend()
    val element = backend.lower(text)
    fun name(element: EtsUiElement) = (element.call.callee as EtsReference).symbol.name
    fun attribute(element: EtsUiElement) = (element.attributes.single().callee as EtsReference).symbol.name
    check(name(element) == "Stack" && attribute(element) == "width")
    val padding = element.children!!.single() as EtsUiElement
    check(attribute(padding) == "padding")
    val sides = padding.attributes.single().arguments.single() as EtsObject
    check(sides.fields.mapValues { (it.value as EtsLiteral).value } == mapOf("left" to 1, "top" to 2, "right" to 3, "bottom" to 4))
    val inner = padding.children!!.single() as EtsUiElement
    check(attribute(inner) == "width")
    check(name(inner.children!!.single() as EtsUiElement) == "Text")
    val click = EtsLambda(emptyList(), emptyList(), EtsTypes.VOID, source)
    val shared: List<WidgetModifier<EtsExpression, SourceSpan>> = listOf(
        WidgetModifier.Size(number(48), number(32), source),
        WidgetModifier.Background(number(7), source),
        WidgetModifier.Click(click, EtsLiteral(false, EtsTypes.BOOLEAN, source), source),
        WidgetModifier.Padding(number(1), number(1), number(1), number(1), source))
    val styledText = backend.lower(Widget.Text(EtsLiteral("styled", EtsTypes.STRING, source), shared, source))
    val invalid = Widget.Text<EtsExpression, SourceSpan>(number(1), emptyList(), source)
    check(runCatching { backend.lower(invalid) }.exceptionOrNull() is IllegalArgumentException)
    val invalidButton = Widget.Button<EtsExpression, SourceSpan>(number(1), null, Children(emptyList()), emptyList(), source)
    check(runCatching { backend.lower(invalidButton) }.exceptionOrNull() is IllegalArgumentException)
    val resource = EtsReference(EtsSymbol("test:resource", "resource",
        EtsNamedType("Resource", external = true), source, external = true))
    val styledImage = backend.lower(Widget.Image(ImageSource.Resource(resource, source),
        EtsLiteral("Styled", EtsTypes.STRING, source), shared, source))
    fun layers(root: EtsUiElement, count: Int): List<EtsUiElement> {
        val result = mutableListOf<EtsUiElement>()
        var current = root
        repeat(count) {
            result += current
            current = current.children!!.single() as EtsUiElement
        }
        return result
    }
    fun attributes(element: EtsUiElement) = element.attributes.map { (it.callee as EtsReference).symbol.name }
    for (styled in listOf(styledText, styledImage)) {
        val ordered = layers(styled, shared.size)
        check(ordered.map(::attributes) == listOf(
            listOf("width", "height"), listOf("backgroundColor"),
            listOf("enabled", "onClick"), listOf("padding")))
        check(ordered[2].attributes.single { (it.callee as EtsReference).symbol.name == "onClick" }
            .arguments.single() == click)
    }
    check(name(layers(styledText, shared.size).last().children!!.single() as EtsUiElement) == "Text")
    check(name(layers(styledImage, shared.size).last().children!!.single() as EtsUiElement) == "Image")
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
    val invalidUrl = Widget.Image<EtsExpression, SourceSpan>(ImageSource.Url(number(1), source),
        EtsLiteral(null, EtsTypes.NULL, source), emptyList(), source)
    check(runCatching { backend.lower(invalidUrl) }.exceptionOrNull() is IllegalArgumentException)
    val invalidDescription = Widget.Image(ImageSource.Resource(resource, source), number(1), emptyList(), source)
    check(runCatching { backend.lower(invalidDescription) }.exceptionOrNull() is IllegalArgumentException)
    val invalidField = Widget.TextField<EtsExpression, SourceSpan>(EtsLiteral("value", EtsTypes.STRING, source), number(1),
        null, emptyList(), source)
    check(runCatching { backend.lower(invalidField) }.exceptionOrNull() is IllegalArgumentException)
    val invalidSize = Widget.Text(EtsLiteral("x", EtsTypes.STRING, source),
        listOf(WidgetModifier.Size<EtsExpression, SourceSpan>(number(1),
            EtsLiteral("bad", EtsTypes.STRING, source), source)), source)
    check(runCatching { backend.lower(invalidSize) }.exceptionOrNull() is IllegalArgumentException)
    val invalidBackground = Widget.Text(EtsLiteral("x", EtsTypes.STRING, source),
        listOf(WidgetModifier.Background<EtsExpression, SourceSpan>(
            EtsLiteral("bad", EtsTypes.STRING, source), source)), source)
    check(runCatching { backend.lower(invalidBackground) }.exceptionOrNull() is IllegalArgumentException)
    val invalidClick = Widget.Text(EtsLiteral("x", EtsTypes.STRING, source),
        listOf(WidgetModifier.Click<EtsExpression, SourceSpan>(number(1), null, source)), source)
    check(runCatching { backend.lower(invalidClick) }.exceptionOrNull() is IllegalArgumentException)
    val fn = EtsFunction("view", emptyList(), EtsTypes.VOID,
        listOf(element, styledText, styledImage, resourceImage, urlImage, textField), source, builder = true)
    EtsValidator().validate(EtsProgram(listOf(EtsFile("model-only", listOf(fn)))))
    println("PASS backend without compiler/Compose; shared ordered size/background/click/padding modifiers and typed rejection")
}
