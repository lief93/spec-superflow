@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.widgettest

import dev.ets.*
import dev.ets.compose.ComposeWidgetAdapter
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
        val entry = functions.single { it.fqNameWhenAvailable?.asString() == "widgetstateinput.InputStateProfile" }
        val sink = DiagnosticSink()
        val backend = EtsBackend(sink, listOf(StandardLibraryRules()))
        val scope = Scope()
        val parameters = backend.parameters(entry, scope)
        val model = ComposeWidgetAdapter(backend.language, sink).lower(entry, scope)
        val conditional = model.widgets.single() as Widget.Conditional
        check(conditional.branches.size == 3 && conditional.branches.last().condition == null)
        check(conditional.branches.all { it.children.widgets.size == 1 })
        val body = HarmonyWidgetBackend().lower(model)
        val branch = body.single() as EtsIf
        check(branch.branches.size == 3 && branch.branches.last().condition == null)
        val nodes = mutableListOf<EtsNode>()
        walkEts(branch, nodes::add)
        val properties = nodes.filterIsInstance<EtsMember>().map { it.name }.toSet()
        check(properties.containsAll(setOf("loading", "error", "content")))
        val dispatch = parameters.single { it.symbol.name == "dispatch" }.symbol
        val effects = nodes.filterIsInstance<EtsCall>().filter { (it.callee as? EtsReference)?.symbol == dispatch }
        check(effects.map { (it.arguments.single() as EtsLiteral).value } == listOf("retry", "refresh"))
        check(effects.all { it.type == EtsTypes.VOID })
        check(nodes.filterIsInstance<EtsLambda>().count { it.returnType == EtsTypes.VOID } == 2)

        val code = ComposeWidgetPipeline(backend, StandardLibraryRuntime)
            .compile(module, "widgetstateinput.InputStateProfile")
        File(output, "InputStateProfile.ets").writeText(code)
        check("export interface UiState" in code)
        check("readonly loading: boolean;" in code && "readonly error: string | null;" in code &&
            "readonly content: string;" in code)
        check("export function InputStateProfile(state: UiState, dispatch: ((arg0: string) => void))" in code)
        check("if ((state as UiState).loading)" in code &&
            "else if (! ((state as UiState).error === null))" in code)
        check("dispatch(\"retry\");" in code && "dispatch(\"refresh\");" in code)
        fun hasBoundContent(source: String) = Regex(
            """ForEach\(\[\(state as UiState\)\.content\] as Array<string>, \((__etsUiArg\d+_\d+): string\) => \{\s*Text\(\1\)""")
            .containsMatchIn(source)
        check(hasBoundContent(code))
        check(listOf("redux", "flow", "network").none { token -> code.lowercase().contains(token) })

        val ifCode = ComposeWidgetPipeline(
            EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())), StandardLibraryRuntime)
            .compile(module, "widgetstateinput.InputStateIfProfile")
        check("if ((state as UiState).loading)" in ifCode && "else {" in ifCode)
        check("dispatch(\"open\");" in ifCode && hasBoundContent(ifCode))

        val failure = try {
            ComposeWidgetPipeline(EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())), StandardLibraryRuntime)
                .compile(module, "widgetstateinput.UnsupportedInputStateBranch")
            error("Accepted unsupported conditional branch body")
        } catch (error: Unsupported) { error.diagnostic }
        check("Unsupported widget children statement" in failure.message)
        check(failure.source.file!!.endsWith("/InputStateUnsupported.kt"))
        check(failure.source.start >= 0 && failure.source.end > failure.source.start)
        File(output, "input-state-diagnostic.tsv").writeText(
            "${failure.code}\t${failure.source}\t${failure.message}\n")
    }
    println("PASS typed object state reads, dispatch effects and runtime conditional widget branches")
}
