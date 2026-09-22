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
    val invalid = Widget.Text<EtsExpression, SourceSpan>(number(1), emptyList(), source)
    check(runCatching { backend.lower(invalid) }.exceptionOrNull() is IllegalArgumentException)
    val invalidButton = Widget.Button<EtsExpression, SourceSpan>(number(1), null, Children(emptyList()), emptyList(), source)
    check(runCatching { backend.lower(invalidButton) }.exceptionOrNull() is IllegalArgumentException)
    val fn = EtsFunction("view", emptyList(), EtsTypes.VOID, listOf(element), source, builder = true)
    EtsValidator().validate(EtsProgram(listOf(EtsFile("model-only", listOf(fn)))))
    println("PASS backend without compiler/Compose; direct model, ordered duplicate modifiers, typed rejection")
}
