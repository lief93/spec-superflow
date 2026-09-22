@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.widgettest

import dev.ets.*
import dev.ets.compose.ComposeStateLowering
import dev.ets.compose.ComposeWidgetAdapter
import dev.ets.harmony.HarmonyWidgetBackend
import dev.ets.pipeline.ComposeWidgetPipeline
import java.io.File
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable

fun main(args: Array<String>) {
    val output = File(args[1]).apply { mkdirs() }
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(2)) { module ->
        val functions = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
        val entry = functions.single { it.fqNameWhenAvailable?.asString() == "widgetsstate.StateProfile" }
        val sink = DiagnosticSink()
        val backend = EtsBackend(sink, listOf(StandardLibraryRules()))
        val plan = ComposeStateLowering(backend.language, sink).lower(entry, Scope(), "StateProfile")
        check(plan.fields.map { it.symbol.name to it.symbol.type } == listOf(
            "__etsState_enabled" to EtsTypes.BOOLEAN, "__etsState_count" to EtsTypes.NUMBER,
            "__etsState_label" to EtsTypes.STRING))
        check(plan.fields.all { it.state && it.initializer != null && it.visibility == EtsVisibility.PRIVATE })
        val model = ComposeWidgetAdapter(backend.language, sink).lower(entry, plan.scope, plan.handledStatements)
        val body = HarmonyWidgetBackend().lower(model)
        val nodes = mutableListOf<EtsNode>()
        body.forEach { walkEts(it, nodes::add) }
        val assignments = nodes.filterIsInstance<EtsAssignment>()
        check(assignments.map { (it.target as EtsMember).name } ==
            listOf("__etsState_enabled", "__etsState_count", "__etsState_label"))
        check(assignments.all { assignment ->
            val target = assignment.target as EtsMember
            plan.fields.single { it.symbol.name == target.name }.symbol.id == target.symbolId
        })
        val conditional = nodes.filterIsInstance<EtsConditional>()
            .single { it.type == EtsTypes.STRING && (it.whenFalse as? EtsLiteral)?.value == "disabled" }
        check((conditional.condition as EtsMember).name == "__etsState_enabled")
        check((conditional.whenTrue as EtsMember).name == "__etsState_label")

        val code = ComposeWidgetPipeline(backend, StandardLibraryRuntime)
            .compile(module, "widgetsstate.StateProfile")
        File(output, "StateProfile.ets").writeText(code)
        check("@Entry" in code && "@Component" in code && "export struct StateProfile" in code)
        check("@State private __etsState_enabled: boolean = false;" in code)
        check("@State private __etsState_count: number = 0;" in code)
        check("@State private __etsState_label: string = \"ready\";" in code)
        check("this.__etsState_enabled = ! this.__etsState_enabled;" in code)
        check("this.__etsState_count = this.__etsState_count + 1 | 0;" in code)
        check("this.__etsState_label = this.__etsState_enabled ? \"on\" : \"off\";" in code)
        check("Text(this.__etsState_enabled ? this.__etsState_label : \"disabled\")" in code)
        check(listOf("remember", "mutableStateOf", "androidx.compose.runtime").none(code::contains))
        val expected = linkedMapOf(
            "SaveableState" to "rememberSaveable is outside",
            "DerivedState" to "supports only mutableStateOf",
            "UnsupportedStateType" to "only direct Boolean, Int, and String",
            "IndirectStateInitializer" to "only direct Boolean, Int, and String",
        )
        val diagnostics = expected.map { (name, message) ->
            val failure = try {
                ComposeWidgetPipeline(EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())), StandardLibraryRuntime)
                    .compile(module, "widgetsstate.$name")
                error("Accepted unsupported state fixture $name")
            } catch (error: Unsupported) { error.diagnostic }
            check(message in failure.message) { "$name: ${failure.message}" }
            check(failure.source.file!!.endsWith("/UnsupportedState.kt"))
            check(failure.source.start >= 0 && failure.source.end > failure.source.start)
            "$name\t${failure.code}\t${failure.source}\t${failure.message}"
        }
        File(output, "state-diagnostics.tsv").writeText(diagnostics.joinToString("\n"))
    }
    println("PASS official Compose state -> owned typed fields, typed callback assignments and runtime conditional")
}
