package dev.ets.pipeline

import dev.ets.*
import dev.ets.compose.ComposeInputContracts
import dev.ets.compose.ComposeHelperLowering
import dev.ets.compose.ComposeStateLowering
import dev.ets.compose.ComposeWidgetAdapter
import dev.ets.harmony.HarmonyWidgetBackend
import org.jetbrains.kotlin.ir.declarations.IrFile
import org.jetbrains.kotlin.ir.declarations.IrModuleFragment
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.types.classFqName
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable

/** Production boundary from resolved Compose IR through the neutral widget model to emitted ETS. */
class ComposeWidgetPipeline(
    private val backend: EtsBackend,
    private val runtime: EtsRuntimeSupport,
) {
    fun compile(module: IrModuleFragment, entryFqName: String): String {
        backend.validateSource(module)
        val matches = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
            .filter { it.fqNameWhenAvailable?.asString() == entryFqName }
        require(matches.size == 1) { "Expected one top-level widget entry $entryFqName; found ${matches.size}" }
        val entry = matches.single()
        if (entry.parent !is IrFile || entry.extensionReceiverParameter != null || entry.typeParameters.isNotEmpty()) {
            backend.diagnostics.unsupported(entry, "Widget pipeline entry must be a non-generic top-level function without a receiver")
        }
        entry.valueParameters.firstOrNull {
            it.type.classFqName?.asString() == "androidx.compose.foundation.lazy.LazyListState"
        }?.let { backend.diagnostics.unsupported(it,
            "Observed or shared LazyListState parameters require target state ownership and are not supported") }

        val scope = Scope()
        val parameters = backend.parameters(entry, scope)
        val state = ComposeStateLowering(backend.language, backend.diagnostics)
            .lower(entry, scope, entry.name.asString())
        if (state.fields.isNotEmpty() && parameters.isNotEmpty()) {
            backend.diagnostics.unsupported(entry.valueParameters.first(),
                "Stateful widget entries do not yet support parameters")
        }
        val helpers = ComposeHelperLowering(backend, backend.diagnostics,
            state.pagers, state.scrolls, state.lazyLists)
        val model = helpers.lowerEntry(entry, state.scope, state.handledStatements)
        val widgetBackend = HarmonyWidgetBackend()
        val body = widgetBackend.lower(model)
        val source = backend.language.source(entry)
        val path = source.file ?: backend.diagnostics.unsupported(entry, "Widget pipeline entry requires a source file")
        val declaration: EtsDeclaration = if (state.fields.isEmpty()) {
            EtsFunction(entry.name.asString(), parameters, EtsTypes.VOID, body, source,
                exported = true, builder = true)
        } else {
            val build = EtsFunction("build", emptyList(), EtsTypes.VOID, body, source,
                kind = EtsFunctionKind.METHOD, build = true)
            EtsClass(entry.name.asString(), state.fields + build, source,
                exported = true, component = true, entry = true)
        }
        val files = linkedMapOf<String, MutableList<EtsDeclaration>>()
        ComposeInputContracts(backend.language, backend.diagnostics).lower(entry).forEach { (contractPath, contract) ->
            files.getOrPut(contractPath) { mutableListOf() } += contract
        }
        helpers.plans().forEach { plan ->
            files.getOrPut(plan.sourcePath) { mutableListOf() } +=
                plan.signature.copy(body = widgetBackend.lower(plan.model))
        }
        files.getOrPut(path) { mutableListOf() } += declaration
        val program = backend.link(EtsProgram(files.map { (sourcePath, declarations) ->
            EtsFile(sourcePath, declarations)
        }, imports = state.imports))
        EtsValidator().validate(program)
        return emitEtsProgram(program, runtime)
    }
}
