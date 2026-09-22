@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.dependency.klib

import dev.ets.*
import org.jetbrains.kotlin.backend.common.linkage.issues.checkNoUnboundSymbols
import org.jetbrains.kotlin.backend.common.lower.ReturnableBlockTransformer
import org.jetbrains.kotlin.ir.backend.js.JsIrBackendContext
import org.jetbrains.kotlin.ir.declarations.IrFile
import org.jetbrains.kotlin.ir.declarations.IrModuleFragment
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.declarations.impl.IrFileImpl
import org.jetbrains.kotlin.ir.declarations.impl.IrModuleFragmentImpl
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.impl.IrFileSymbolImpl
import org.jetbrains.kotlin.ir.symbols.IrFunctionSymbol
import org.jetbrains.kotlin.ir.util.ExternalDependenciesGenerator
import org.jetbrains.kotlin.ir.util.fileOrNull
import org.jetbrains.kotlin.ir.util.patchDeclarationParents
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid
import org.jetbrains.kotlin.ir.visitors.transformChildrenVoid

/** Evidence describes actual body availability or a successful typed replacement, never name guesses. */
data class KlibDependencyDecision(
    val kind: Kind,
    val signature: String,
    val declaration: SourceSpan,
    val library: String?,
    val callSite: SourceSpan?,
    val detail: String,
) {
    enum class Kind { REUSABLE_BODY, TARGET_REPLACEMENT, REJECTED }
}

data class KlibLoweringResult(
    val program: EtsProgram,
    val decisions: List<KlibDependencyDecision>,
    val runtimeSymbols: Set<String>,
)

/**
 * Consumes selected modules and explicitly approved dependency bodies in one official symbol session.
 * No JS lowering pipeline or JS runtime emission. A session must be lowered only once.
 */
fun KlibSession.lowerToEts(
    rules: List<CallRule>,
    approvedBodies: Set<IrFunctionSymbol> = emptySet(),
    report: (KlibDependencyDecision) -> Unit = {},
): KlibLoweringResult {
    beginLowering()
    val modules = linkedModules()
    val decisions = linkedSetOf<KlibDependencyDecision>()
    fun record(kind: KlibDependencyDecision.Kind, symbol: IrFunctionSymbol, callSite: SourceSpan?, detail: String) {
        val owner = symbol.owner
        val file = owner.fileOrNull
        val decision = KlibDependencyDecision(kind, symbol.signature?.toString() ?: symbolName(owner),
            SourceSpan(file?.fileEntry?.name ?: "<compiler-builtins>", owner.startOffset, owner.endOffset),
            libraryLocations[file?.module], callSite, detail)
        decisions.add(decision)
    }
    val provider = bodies(approvedBodies)
    val selectedBodies = approvedBodies.associateWith(provider::resolve)
    val recordedBodies = FunctionBodies { symbol ->
        (selectedBodies[symbol] ?: provider.resolve(symbol)).also { body ->
            if (body is FunctionBody.Available) record(KlibDependencyDecision.Kind.REUSABLE_BODY, symbol, null,
                "Official serialized KLIB body: ${body.origin}")
        }
    }
    // Include non-inline translated bodies in the audit as well as inliner requests.
    modules.forEach { module -> module.acceptChildrenVoid(object : org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid {
        override fun visitElement(element: org.jetbrains.kotlin.ir.IrElement) {
            if (element is org.jetbrains.kotlin.ir.declarations.IrFunction) recordedBodies.resolve(element.symbol)
            element.acceptChildrenVoid(this)
        }
    }) }
    val context = JsIrBackendContext(loaded.module.descriptor, loaded.bultins, symbolTable,
        emptySet(), emptySet(), configuration, null)
    ExternalDependenciesGenerator(symbolTable, listOf(linker)).generateUnboundSymbolsAsDependencies()
    // Official jsCompiler.kt completes fake overrides after context-driven loading.
    linker.postProcess(inOrAfterLinkageStep = true)
    linker.checkNoUnboundSymbols(symbolTable, "before KLIB common inlining")
    approvedBodies.forEach(recordedBodies::resolve)
    val ordinaryBodies = selectedBodies.values.filterIsInstance<FunctionBody.Available>()
        .map { it.declaration }.filterNot { it.isInline }
    val loweringModules = modules + materializeOrdinaryBodies(ordinaryBodies)
    inlineAvailableFunctions(context, loweringModules, recordedBodies)
    loweringModules.forEach {
        it.transformChildrenVoid(ReturnableBlockTransformer(context))
        it.patchDeclarationParents()
    }
    val observedRules = rules.map { rule -> object : CallRule by rule {
        override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? =
            if (call.symbol in approvedBodies) null else rule.lower(call, language, scope)?.also {
                record(KlibDependencyDecision.Kind.TARGET_REPLACEMENT, call.symbol, language.source(call),
                    "Typed target value supplied by ${rule.javaClass.name}")
            }
        override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? =
            rule.lowerConstructor(call, language, scope)?.also {
                record(KlibDependencyDecision.Kind.TARGET_REPLACEMENT, call.symbol, language.source(call),
                    "Typed target constructor supplied by ${rule.javaClass.name}")
            }
        override fun lowerStatement(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? =
            if (call.symbol in approvedBodies) null else rule.lowerStatement(call, language, scope)?.also {
                record(KlibDependencyDecision.Kind.TARGET_REPLACEMENT, call.symbol, language.source(call),
                    "Target statements supplied by ${rule.javaClass.name}")
            }
    } }
    fun guard(call: IrFunctionAccessExpression, language: Language) {
        val owner = call.symbol.owner
        val module = owner.fileOrNull?.module
        if (!owner.isExternal && (module == null || module in loweringModules)) return
        val resolution = provider.resolve(call.symbol)
        val reason = (resolution as? FunctionBody.Unavailable)?.reason?.evidence
            ?: "The dependency call remains after common inlining and is not selected for emission."
        record(KlibDependencyDecision.Kind.REJECTED, call.symbol, language.source(call), reason)
        report(decisions.last())
        throw Unsupported(Diagnostic("UNSUPPORTED_KLIB_DEPENDENCY",
            "KLIB dependency ${call.symbol.signature ?: symbolName(owner)} at " +
                "${libraryLocations[module] ?: "<unknown-library>"}; declaration " +
                "${owner.fileOrNull?.fileEntry?.name ?: "<no-file>"}:${owner.startOffset}..${owner.endOffset}: " +
                "$reason No target replacement accepted this call.", language.source(call)))
    }
    val boundary = object : CallRule {
        override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
            guard(call, language)
            return null
        }
        override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? {
            guard(call, language)
            return null
        }
    }
    val program = EtsBackend(DiagnosticSink(), observedRules + boundary).lower(loweringModules)
    decisions.forEach(report)
    return KlibLoweringResult(program, decisions.toList(), standardLibraryRuntimeSymbols(program))
}

private fun materializeOrdinaryBodies(declarations: List<org.jetbrains.kotlin.ir.declarations.IrFunction>):
    List<IrModuleFragment> {
    val functions = declarations.map { declaration ->
        require(declaration is IrSimpleFunction && declaration.parent is IrFile) {
            "Ordinary KLIB body reuse currently requires a top-level simple function"
        }
        declaration
    }
    return functions.groupBy { (it.parent as IrFile).module }.map { (sourceModule, moduleFunctions) ->
        val targetModule = IrModuleFragmentImpl(sourceModule.descriptor)
        moduleFunctions.groupBy { it.parent as IrFile }.forEach { (sourceFile, fileFunctions) ->
            val targetFile = IrFileImpl(sourceFile.fileEntry, IrFileSymbolImpl(), sourceFile.packageFqName)
            targetFile.module = targetModule
            targetModule.files += targetFile
            fileFunctions.forEach { function ->
                check(sourceFile.declarations.remove(function)) { "Selected KLIB function is not owned by its source file" }
                function.parent = targetFile
                targetFile.declarations += function
            }
        }
        targetModule
    }
}
