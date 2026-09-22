@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.widgettest

import dev.ets.*
import dev.ets.compose.ComposeStateLowering
import dev.ets.compose.ComposeWidgetAdapter
import dev.ets.harmony.HarmonyWidgetBackend
import dev.ets.pipeline.ComposeWidgetPipeline
import dev.ets.widgets.*
import java.io.File
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid

fun main(args: Array<String>) {
    val output = File(args[1]).apply { mkdirs() }
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(2)) { module ->
        val functions = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
        val entry = functions.single { it.fqNameWhenAvailable?.asString() == "widgetscroll.ScrollProfile" }
        val sink = DiagnosticSink()
        val backend = EtsBackend(sink, listOf(StandardLibraryRules()))
        val plan = ComposeStateLowering(backend.language, sink).lower(entry, Scope(), "ScrollProfile")
        check(plan.fields.map { it.symbol.name to it.symbol.type } == listOf(
            "vertical_offset" to EtsTypes.NUMBER, "horizontal_offset" to EtsTypes.NUMBER))
        check(plan.fields.all { it.state && it.visibility == EtsVisibility.PRIVATE })
        check(plan.fields.map { (it.initializer as EtsLiteral).value } == listOf(12, 7))
        check(plan.scrolls.size == 2)

        val model = ComposeWidgetAdapter(backend.language, sink, plan.pagers, plan.scrolls)
            .lower(entry, plan.scope, plan.handledStatements)
        val root = model.widgets.single() as Widget.Column<EtsExpression, SourceSpan>
        val vertical = root.children.widgets[0] as Widget.Column<EtsExpression, SourceSpan>
        val horizontal = root.children.widgets[1] as Widget.Row<EtsExpression, SourceSpan>
        check(vertical.modifiers.map { it::class.simpleName } == listOf("Fill", "Scroll", "Fill"))
        check(horizontal.modifiers.map { it::class.simpleName } == listOf("Fill", "Scroll", "Fill"))
        val verticalScroll = vertical.modifiers[1] as WidgetModifier.Scroll<EtsExpression, SourceSpan>
        val horizontalScroll = horizontal.modifiers[1] as WidgetModifier.Scroll<EtsExpression, SourceSpan>
        check(verticalScroll.axis == WidgetScrollAxis.VERTICAL)
        check(horizontalScroll.axis == WidgetScrollAxis.HORIZONTAL)
        check((verticalScroll.enabled as EtsLiteral).value == true)
        check((horizontalScroll.enabled as EtsLiteral).value == false)
        check((verticalScroll.offset as EtsMember).name == "vertical_offset")
        check((horizontalScroll.offset as EtsMember).name == "horizontal_offset")
        fun assignment(scroll: WidgetModifier.Scroll<EtsExpression, SourceSpan>): Pair<EtsLambda, EtsAssignment> {
            val lambda = scroll.onScroll as EtsLambda
            val update = (lambda.body.single() as EtsExpressionStatement).expression as EtsAssignment
            return lambda to update
        }
        val (verticalCallback, verticalUpdate) = assignment(verticalScroll)
        val (horizontalCallback, horizontalUpdate) = assignment(horizontalScroll)
        check((verticalUpdate.value as EtsReference).symbol == verticalCallback.parameters[1].symbol)
        check((horizontalUpdate.value as EtsReference).symbol == horizontalCallback.parameters[0].symbol)
        val textNodes = mutableListOf<EtsNode>()
        walkEts((vertical.children.widgets[0] as Widget.Text<EtsExpression, SourceSpan>).text.value, textNodes::add)
        walkEts((horizontal.children.widgets[0] as Widget.Text<EtsExpression, SourceSpan>).text.value, textNodes::add)
        check(textNodes.filterIsInstance<EtsMember>().map { it.name }.containsAll(
            listOf("vertical_offset", "horizontal_offset")))

        fun callName(element: EtsUiElement) = (element.call.callee as EtsReference).symbol.name
        fun attributeNames(element: EtsUiElement) =
            element.attributes.map { (it.callee as EtsReference).symbol.name }
        val verticalLayer = HarmonyWidgetBackend().lower(vertical)
        check(callName(verticalLayer) == "Stack" && attributeNames(verticalLayer) == listOf("height"))
        val verticalNative = verticalLayer.children!!.single() as EtsUiElement
        check(callName(verticalNative) == "Scroll")
        check(attributeNames(verticalNative) == listOf(
            "scrollable", "initialOffset", "scrollBar", "enableScrollInteraction", "align", "onScroll"))
        val verticalFill = verticalNative.children!!.single() as EtsUiElement
        check(callName(verticalFill) == "Stack" && attributeNames(verticalFill) == listOf("width"))
        val horizontalLayer = HarmonyWidgetBackend().lower(horizontal)
        val horizontalNative = horizontalLayer.children!!.single() as EtsUiElement
        check(callName(horizontalNative) == "Scroll")
        val directions = listOf(verticalNative, horizontalNative).map { scroll ->
            val direction = scroll.attributes.first().arguments.single() as EtsMember
            direction.name
        }
        check(directions == listOf("Vertical", "Horizontal"))

        val code = ComposeWidgetPipeline(backend, StandardLibraryRuntime)
            .compile(module, "widgetscroll.ScrollProfile")
        File(output, "ScrollProfile.ets").writeText(code)
        check("@State private vertical_offset: number = 12;" in code)
        check("@State private horizontal_offset: number = 7;" in code)
        check("Scroll()" in code)
        check(".scrollable(ScrollDirection.Vertical)" in code)
        check(".scrollable(ScrollDirection.Horizontal)" in code)
        check(".initialOffset({ xOffset: 0, yOffset: this.vertical_offset })" in code)
        check(".initialOffset({ xOffset: this.horizontal_offset, yOffset: 0 })" in code)
        check(".enableScrollInteraction(true)" in code && ".enableScrollInteraction(false)" in code)
        check("this.vertical_offset = yOffset;" in code)
        check("this.horizontal_offset = xOffset;" in code)
        check("Text(\"\" + \"Vertical \" + this.vertical_offset)" in code)
        check("Text(\"\" + \"Horizontal \" + this.horizontal_offset)" in code)
        check(listOf("onboarding", "animateScrollTo(", "scrollTo(").none(code::contains))

        val expected = linkedMapOf(
            "NegativeScrollInitial" to "must be non-negative",
            "DynamicScrollInitial" to "requires an integer literal",
            "ReverseScroll" to "reverseScrolling",
            "FlingScroll" to "flingBehavior",
            "Overscroll" to "overscrollEffect",
            "InlineScrollState" to "source remembered ScrollState",
        )
        val diagnostics = expected.map { (name, message) ->
            val failure = try {
                ComposeWidgetPipeline(EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())), StandardLibraryRuntime)
                    .compile(module, "widgetscroll.$name")
                error("Accepted unsupported scroll fixture $name")
            } catch (error: Unsupported) { error.diagnostic }
            check(message in failure.message) { "$name: ${failure.message}" }
            check(failure.source.file!!.endsWith("/ScrollUnsupported.kt"))
            check(failure.source.start >= 0 && failure.source.end > failure.source.start)
            "$name\t${failure.code}\t${failure.source}\t${failure.message}"
        }.toMutableList()
        val programmatic = functions.single {
            it.fqNameWhenAvailable?.asString() == "widgetscroll.ProgrammaticScroll" }
        val programmaticBackend = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules()))
        val programmaticPlan = ComposeStateLowering(programmaticBackend.language,
            programmaticBackend.diagnostics).lower(programmatic, Scope(), "ProgrammaticScroll")
        var animate: IrCall? = null
        programmatic.acceptChildrenVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
            override fun visitCall(expression: IrCall) {
                if (symbolName(expression.symbol.owner) ==
                    "androidx.compose.foundation.ScrollState.animateScrollTo") animate = expression
                expression.acceptChildrenVoid(this)
            }
        })
        val programmaticFailure = try {
            programmaticBackend.language.expression(checkNotNull(animate), programmaticPlan.scope)
            error("Accepted programmatic ScrollState animateScrollTo")
        } catch (error: Unsupported) { error.diagnostic }
        check("Programmatic ScrollState scrollTo/animateScrollTo is not supported" in programmaticFailure.message)
        check(programmaticFailure.source.file!!.endsWith("/ScrollUnsupported.kt"))
        diagnostics += "ProgrammaticScroll\t${programmaticFailure.code}\t${programmaticFailure.source}\t${programmaticFailure.message}"
        File(output, "scroll-diagnostics.tsv").writeText(diagnostics.joinToString("\n"))
    }
    println("PASS official scroll modifiers -> ordered neutral Scroll -> interactive typed Harmony Scroll")
}
