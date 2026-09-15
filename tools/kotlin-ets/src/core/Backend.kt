package dev.ets

import org.jetbrains.kotlin.descriptors.DescriptorVisibilities
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.visitors.*

/** Official IR stays alive only while lowering. The returned program is compiler-independent. */
class EtsBackend(val diagnostics: DiagnosticSink, rules: List<CallRule>, sourceTypes: SourceTypes? = null) {
    val language: Language = LanguageLowering(diagnostics, rules, sourceTypes)

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
        val program = EtsProgram(modules.flatMap { it.files }.map { file ->
            diagnostics.currentFile = file.fileEntry.name
            EtsFile(file.fileEntry.name, file.declarations.flatMap { declaration -> when (declaration) {
                is IrSimpleFunction -> listOf(language.function(declaration).copy(
                    exported = !DescriptorVisibilities.isPrivate(declaration.visibility)))
                is IrClass -> listOf(language.clazz(declaration).copy(
                    exported = sourceClassIsExported(declaration)))
                is IrProperty -> lowerTopLevelProperty(declaration, language)
                else -> diagnostics.unsupported(declaration, "Unsupported top-level declaration")
            } } + lowerFileInitialization(file, language))
        })
        EtsValidator().validate(program, perFileNames = true)
        return program
    }
}
