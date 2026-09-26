package dev.ets

import org.jetbrains.kotlin.descriptors.DescriptorVisibilities
import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.declarations.IrDeclaration
import org.jetbrains.kotlin.ir.declarations.IrFile
import org.jetbrains.kotlin.ir.declarations.IrModuleFragment
import org.jetbrains.kotlin.ir.declarations.IrProperty
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.expressions.IrBody
import org.jetbrains.kotlin.ir.expressions.IrExpression
import org.jetbrains.kotlin.ir.types.IrType

/**
 * IR → `EtsProgram` seam. High-level Kotlin semantic lowering belongs in
 * `EtsLoweringPhases`. This layer maps already-lowered official IR through
 * `Language` / `CallRule` and must not rewrite operators, defaults, or
 * inheritance on its own.
 */
object IrToEts {
    fun program(modules: List<IrModuleFragment>, language: Language, diagnostics: DiagnosticSink): EtsProgram {
        val program = linkAdapterDeclarations(EtsProgram(modules.flatMap { module ->
            IrModuleToEts.lower(module, language, diagnostics)
        }, externalClasses = exceptionTargetContracts()), language.callRules)
        EtsValidator().validate(program, perFileNames = true)
        return program
    }
}

object IrModuleToEts {
    fun lower(module: IrModuleFragment, language: Language, diagnostics: DiagnosticSink): List<EtsFile> =
        module.files.map { file ->
            diagnostics.currentFile = file.fileEntry.name
            IrFileToEts.lower(file, language, diagnostics)
        }
}

object IrFileToEts {
    fun lower(file: IrFile, language: Language, diagnostics: DiagnosticSink): EtsFile =
        EtsFile(file.fileEntry.name, file.declarations.flatMap { declaration ->
            IrDeclarationToEts.lower(declaration, language, diagnostics)
        } + initialization(file, language))

    /** Shared file-initialization lowering for language and UI entry pipelines. */
    fun initialization(file: IrFile, language: Language,
        selectedProperties: Set<IrProperty>? = null): List<EtsDeclaration> =
        lowerFileInitialization(file, language, selectedProperties)
}

object IrDeclarationToEts {
    fun lower(declaration: IrDeclaration, language: Language, diagnostics: DiagnosticSink): List<EtsDeclaration> =
        when (declaration) {
            is IrSimpleFunction -> listOf(IrFunctionToEts.lower(declaration, language).copy(
                exported = !DescriptorVisibilities.isPrivate(declaration.visibility)))
            is IrClass -> listOf(IrClassToEts.lower(declaration, language).copy(
                exported = sourceClassIsExported(declaration))) + language.interfaceDefaults(declaration)
            is IrProperty -> lowerTopLevelProperty(declaration, language)
            else -> diagnostics.unsupported(declaration, "Unsupported top-level declaration")
        }
}

object IrClassToEts {
    fun lower(declaration: IrClass, language: Language): EtsClass = language.clazz(declaration)
}

object IrFunctionToEts {
    fun lower(function: IrSimpleFunction, language: Language, scope: Scope = Scope(),
        semantics: FunctionTargetSemantics = FunctionTargetSemantics()): EtsFunction =
        language.function(function, scope, semantics)
}

object IrStatementToEts {
    fun lower(body: IrBody, language: Language, scope: Scope): List<EtsStatement> = language.statements(body, scope)
}

object IrExpressionToEts {
    fun lower(expression: IrExpression, language: Language, scope: Scope): EtsExpression =
        language.expression(expression, scope)
}

object IrTypeToEts {
    fun lower(type: IrType, language: Language): EtsType = language.type(type)
}
