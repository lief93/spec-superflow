@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.widgettest

import dev.ets.*
import dev.ets.compose.ComposeHelperLowering
import dev.ets.compose.ComposeStateLowering
import dev.ets.harmony.HarmonyWidgetBackend
import dev.ets.pipeline.ComposeWidgetPipeline
import dev.ets.widgets.Widget
import java.io.File
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable

fun main(args: Array<String>) {
    val output = File(args[1]).apply { mkdirs() }
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(2)) { module ->
        val functions = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
        val entry = functions.single { it.fqNameWhenAvailable?.asString() == "widgethelpers.HelperEntry" }
        val sink = DiagnosticSink()
        val backend = EtsBackend(sink, listOf(StandardLibraryRules()))
        val scope = Scope()
        val entryParameters = backend.parameters(entry, scope)
        val state = ComposeStateLowering(backend.language, sink).lower(entry, scope, "HelperEntry")
        val helpers = ComposeHelperLowering(backend, sink)
        val model = helpers.lowerEntry(entry, state.scope, state.handledStatements)
        val call = (model.widgets.single() as Widget.BuilderCall).call as EtsCall
        val plans = helpers.plans()
        val helper = plans.single { it.signature.name == "ActionCard" }
        val slot = plans.single { it.signature.name == "HelperEntry_content" }
        check(helper.signature.parameters.map { it.symbol.name } == listOf("title", "enabled", "onAction", "content"))
        check((helper.signature.parameters[1].defaultValue as EtsLiteral).value == true)
        check((call.callee as EtsReference).symbol == helper.signature.symbol)
        check((call.arguments[0] as EtsReference).symbol == entryParameters[0].symbol)
        check(call.arguments[1] is EtsUndefined)
        check((call.arguments[2] as EtsReference).symbol == entryParameters[2].symbol)
        check((call.arguments[3] as EtsNew).classType.name == "WrappedBuilder")
        check(slot.signature.parameters.map { it.symbol.name } == listOf("label"))
        val target = HarmonyWidgetBackend()
        val helperNodes = mutableListOf<EtsNode>()
        target.lower(helper.model).forEach { walkEts(it, helperNodes::add) }
        val callback = helper.signature.parameters.single { it.symbol.name == "onAction" }.symbol
        check(helperNodes.filterIsInstance<EtsReference>().any { it.symbol == callback })
        check(helperNodes.filterIsInstance<EtsMember>().any { it.name == "builder" })
        val slotNodes = mutableListOf<EtsNode>()
        target.lower(slot.model).forEach { walkEts(it, slotNodes::add) }
        val label = slot.signature.parameters.single().symbol
        check(slotNodes.filterIsInstance<EtsReference>().any { it.symbol == label })

        val code = ComposeWidgetPipeline(backend, StandardLibraryRuntime)
            .compile(module, "widgethelpers.HelperEntry")
        File(output, "HelperEntry.ets").writeText(code)
        check("function ActionCard(title: string, enabled: boolean = true, onAction: (() => void), content: WrappedBuilder<[]>)" in code)
        check("function HelperEntry_content(label: string)" in code)
        check("content.builder()" in code)
        check(".onClick(onAction)" in code)
        check("ActionCard(title, undefined, onAction, new WrappedBuilder<[]>((): void =>" in code)
        check("HelperEntry_content(label);" in code)
        check(!Regex("(?:ActionCard|HelperEntry_content)_\\d+").containsMatchIn(code))

        val expected = linkedMapOf(
            "RecursiveEntry" to "Recursive source composable calls",
            "GenericEntry" to "Generic source composables",
            "DefaultContentEntry" to "content defaults cannot replace",
        )
        val diagnostics = expected.map { (name, message) ->
            val failure = try {
                ComposeWidgetPipeline(EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())), StandardLibraryRuntime)
                    .compile(module, "widgethelpers.$name")
                error("Accepted unsupported helper fixture $name")
            } catch (error: Unsupported) { error.diagnostic }
            check(message in failure.message) { "$name: ${failure.message}" }
            check(failure.source.file!!.endsWith("/HelperUnsupported.kt"))
            check(failure.source.start >= 0 && failure.source.end > failure.source.start)
            "$name\t${failure.code}\t${failure.source}\t${failure.message}"
        }
        File(output, "helper-diagnostics.tsv").writeText(diagnostics.joinToString("\n"))
    }
    println("PASS cross-file named composable helper, typed/default arguments, callback and structured content slot")
}
