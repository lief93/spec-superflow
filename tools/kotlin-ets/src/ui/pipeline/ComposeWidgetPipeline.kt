package dev.ets.pipeline

import dev.ets.*
import dev.ets.compose.ComposeWidgetAdapter
import dev.ets.harmony.HarmonyWidgetBackend
import org.jetbrains.kotlin.ir.declarations.IrFile
import org.jetbrains.kotlin.ir.declarations.IrModuleFragment
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
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

        val scope = Scope()
        val parameters = backend.parameters(entry, scope)
        val model = ComposeWidgetAdapter(backend.language, backend.diagnostics).lower(entry, scope)
        val body = HarmonyWidgetBackend().lower(model)
        val source = backend.language.source(entry)
        val path = source.file ?: backend.diagnostics.unsupported(entry, "Widget pipeline entry requires a source file")
        val builder = EtsFunction(entry.name.asString(), parameters, EtsTypes.VOID, body, source,
            exported = true, builder = true)
        val program = backend.link(EtsProgram(listOf(EtsFile(path, listOf(builder)))))
        EtsValidator().validate(program)
        return emitEtsProgram(program, runtime)
    }
}
