package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.visitors.*

/** Official IR stays alive only while lowering. The returned program is compiler-independent. */
class EtsBackend(val diagnostics: DiagnosticSink, private val rules: List<CallRule>, sourceTypes: SourceTypes? = null) {
    private val lowering = LanguageLowering(diagnostics, rules, sourceTypes)
    val language: Language = lowering

    /** Bind a production entry signature with the same naming and type rules as ordinary functions. */
    fun parameters(function: IrFunction, scope: Scope): List<EtsParameter> = lowering.parameters(function, scope)

    /** Link declarations contributed by the configured call rules. */
    fun link(program: EtsProgram): EtsProgram = linkAdapterDeclarations(program, rules)

    fun validateSource(module: IrModuleFragment) {
        module.files.forEach { file ->
            diagnostics.currentFile = file.fileEntry.name
            file.acceptChildrenVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) {
                    if (element is IrDeclarationWithName && element.name.asString().startsWith("__ets") &&
                        element.origin !== ETS_SHARED_VARIABLE_CELL && element.origin !== ETS_BOUND_CONSTRAINT) {
                        diagnostics.unsupported(element, "Source name collides with reserved __ets target helpers")
                    }
                    element.acceptChildrenVoid(this)
                }
            })
        }
    }

    fun lower(module: IrModuleFragment): EtsProgram = lower(listOf(module))

    /** Modules selected for translation share symbol identity; their IR ownership stays intact. */
    fun lower(modules: List<IrModuleFragment>): EtsProgram {
        modules.forEach(::validateSource)
        return IrToEts.program(modules, language, diagnostics)
    }
}
