@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.widgettest

import dev.ets.*
import dev.ets.compose.ComposeWidgetAdapter
import dev.ets.harmony.HarmonyWidgetBackend
import dev.ets.widgets.*
import java.io.File
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable

fun main(args: Array<String>) {
    val output = File(args[1]).apply { mkdirs() }
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(2)) { module ->
        val sink = DiagnosticSink()
        val language = EtsBackend(sink, listOf(StandardLibraryRules(), ComposeDimensionRule())).language
        val functions = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
        val page = functions.single { it.fqNameWhenAvailable?.asString() == "widgetsfixture.Page" }
        val scope = Scope()
        val parameters = page.valueParameters.map { parameter ->
            val symbol = EtsSymbol("widget-input:${parameter.name}", parameter.name.asString(), language.type(parameter.type), language.source(parameter))
            scope.bindings[parameter.symbol] = EtsReference(symbol)
            EtsParameter(symbol)
        }
        val adapter = ComposeWidgetAdapter(language, sink)
        val model = adapter.lower(page, scope)
        val column = model.widgets.single() as Widget.Column
        check(column.modifiers.map { it.javaClass.simpleName } == listOf("Width", "Padding", "Width"))
        check((column.modifiers[0] as WidgetModifier.Width).value.let { it as EtsLiteral }.value == 120.0)
        check((column.modifiers[2] as WidgetModifier.Width).value.let { it as EtsLiteral }.value == 80.0)
        check(column.children.widgets.size == 6)
        val title = column.children.widgets[0] as Widget.Text
        check((title.text as EtsReference).symbol == parameters[0].symbol)
        val button = column.children.widgets[1] as Widget.Button
        check((button.onClick as EtsReference).symbol == parameters[2].symbol)
        check((button.enabled as EtsReference).symbol == parameters[1].symbol)
        check(button.modifiers.map { it.javaClass.simpleName } == listOf("Padding", "Height"))
        val row = button.content.widgets.single() as Widget.Row
        check(row.children.widgets.size == 2)
        val box = row.children.widgets[1] as Widget.Box
        check(box.children.widgets.single() is Widget.Text)
        check(box.modifiers.map { it.javaClass.simpleName } == listOf("Height", "Width"))
        check(((column.children.widgets[2] as Widget.Text).text as EtsLiteral).value == "after")
        check((column.children.widgets[3] as Widget.Row).modifiers.map { it.javaClass.simpleName } == listOf("Padding", "Width"))
        check((column.children.widgets[4] as Widget.Box).children.widgets.isEmpty())
        check(column.source.file!!.endsWith("/Page.kt") && column.source.start >= 0 && column.source.end > column.source.start)
        File(output, "model.txt").writeText(model.toString())
        val children = HarmonyWidgetBackend().lower(model)
        val at = language.source(page)
        val builder = EtsFunction("Page", parameters, EtsTypes.VOID, children, at, exported = true, builder = true)
        val content = EtsUiElement(EtsCall(EtsReference(builder.symbol), listOf(
            EtsLiteral("resolved", EtsTypes.STRING, at), EtsLiteral(true, EtsTypes.BOOLEAN, at),
            EtsLambda(emptyList(), emptyList(), EtsTypes.VOID, at)), EtsTypes.VOID, at))
        // The SDK requires an entry container. It is itself a semantic Box.
        val shell = HarmonyWidgetBackend().lower(Widget.Box(Children(emptyList()), emptyList(), at)).copy(children = listOf(content))
        val entry = EtsClass("WidgetPage", listOf(EtsFunction("build", emptyList(), EtsTypes.VOID,
            listOf(shell), at, kind = EtsFunctionKind.METHOD, build = true)), at, exported = true, component = true, entry = true)
        val program = EtsProgram(listOf(EtsFile(at.file!!, listOf(builder, entry))))
        EtsValidator().validate(program)
        File(output, "WidgetPage.ets").writeText(emitEtsProgram(program, StandardLibraryRuntime))
        val tree = mutableListOf<EtsNode>()
        walkEts(builder, tree::add)
        val elements = tree.filterIsInstance<EtsUiElement>()
        check(elements.any { (it.call.callee as? EtsReference)?.symbol?.name == "Stack" })
        check(elements.count { (it.call.callee as? EtsReference)?.symbol?.name == "Text" } == 6)
        val nativeButton = elements.single { (it.call.callee as? EtsReference)?.symbol?.name == "Button" }
        check(nativeButton.children?.single() is EtsUiElement)
        check(nativeButton.attributes.single { (it.callee as EtsReference).symbol.name == "onClick" }.arguments.single() == button.onClick)
        val expected = linkedMapOf(
            "UnknownWidget" to "Unsupported resolved widget API", "UnknownModifier" to "Unsupported resolved widget Modifier API",
            "UnknownArgument" to "widget argument: fontSize", "Conditional" to "Unsupported widget children statement",
            "Helper" to "Unsupported resolved widget API", "EffectfulValue" to "stable scalars",
            "CallbackFactory" to "callback requires a lambda", "NegativePadding" to "finite and non-negative",
            "MutableLocal" to "Mutable widget local", "EarlyReturn" to "Widget return")
        val diagnostics = expected.map { (name, message) ->
            val function = functions.single { it.name.asString() == name }
            val failure = try { adapter.lower(function); error("Accepted unsupported fixture $name") } catch (error: Unsupported) { error.diagnostic }
            check(message in failure.message) { "$name: ${failure.message}" }
            check(failure.source.file!!.endsWith("/Unsupported.kt"))
            check(failure.source.start >= 0 && failure.source.end > failure.source.start)
            "$name\t${failure.code}\t${failure.source}\t${failure.message}"
        }
        File(output, "diagnostics.tsv").writeText(diagnostics.joinToString("\n"))
        println("PASS resolved Compose -> neutral structure -> typed ETS; ${expected.size} source-linked rejections")
    }
}
