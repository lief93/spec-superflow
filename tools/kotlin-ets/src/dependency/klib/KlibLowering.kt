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
import org.jetbrains.kotlin.ir.symbols.IrClassSymbol
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

/** Canonical dependency symbols that a typed rule owns as primitive boundaries. */
interface KlibPrimitiveBoundary {
    val klibPrimitiveSymbols: Set<IrFunctionSymbol>
}

/** Dependency calls that a typed rule may replace only when their common body cannot be reused. */
interface KlibAdapterFallback {
    val klibAdapterFallbackSymbols: Set<IrFunctionSymbol>
}

private data class DependencyBodyRejection(val symbol: IrFunctionSymbol, val reason: String)
private data class DependencyBodyClosure(
    val admitted: LinkedHashMap<IrFunctionSymbol, FunctionBody.Available>,
    val rejected: Map<IrFunctionSymbol, DependencyBodyRejection>,
)

/**
 * Consumes selected modules and the satisfiable dependency-body closure in one official symbol session.
 * No JS lowering pipeline or JS runtime emission. A session must be lowered only once.
 */
fun KlibSession.lowerToEts(
    rules: List<CallRule>,
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
    val provider = bodies()
    val context = JsIrBackendContext(loaded.module.descriptor, loaded.bultins, symbolTable,
        emptySet(), emptySet(), configuration, null)
    ExternalDependenciesGenerator(symbolTable, listOf(linker)).generateUnboundSymbolsAsDependencies()
    // Official jsCompiler.kt completes fake overrides after context-driven loading.
    linker.postProcess(inOrAfterLinkageStep = true)
    linker.checkNoUnboundSymbols(symbolTable, "before KLIB common inlining")
    val closure = dependencyBodyClosure(modules, provider, libraryLocations.keys, loaded.bultins.unitClass,
        rules.filterIsInstance<KlibPrimitiveBoundary>().flatMapTo(linkedSetOf()) { it.klibPrimitiveSymbols },
        rules.filterIsInstance<KlibAdapterFallback>().flatMapTo(linkedSetOf()) { it.klibAdapterFallbackSymbols })
    val candidateBodies = closure.admitted
    val recordedBodies = FunctionBodies { symbol ->
        val body = if (symbol.owner.fileOrNull?.module in modules || symbol in candidateBodies) provider.resolve(symbol)
            else FunctionBody.Unavailable(FunctionBody.Reason.NON_TRANSLATED_KLIB)
        body.also {
            if (it is FunctionBody.Available) record(KlibDependencyDecision.Kind.REUSABLE_BODY, symbol, null,
                "Official serialized KLIB body: ${it.origin}")
        }
    }
    // Include non-inline translated bodies in the audit as well as inliner requests.
    modules.forEach { module -> module.acceptChildrenVoid(object : org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid {
        override fun visitElement(element: org.jetbrains.kotlin.ir.IrElement) {
            if (element is org.jetbrains.kotlin.ir.declarations.IrFunction) recordedBodies.resolve(element.symbol)
            element.acceptChildrenVoid(this)
        }
    }) }
    candidateBodies.keys.forEach(recordedBodies::resolve)
    val ordinaryBodies = candidateBodies.values
        .map { it.declaration }.filterNot { it.isInline }
    val loweringModules = modules + materializeOrdinaryBodies(ordinaryBodies)
    inlineAvailableFunctions(context, loweringModules, recordedBodies)
    loweringModules.forEach {
        it.transformChildrenVoid(ReturnableBlockTransformer(context))
        it.patchDeclarationParents()
    }
    val observedRules = rules.map { rule -> object : CallRule by rule {
        override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? =
            if (call.symbol in candidateBodies) null else rule.lower(call, language, scope)?.also {
                record(KlibDependencyDecision.Kind.TARGET_REPLACEMENT, call.symbol, language.source(call),
                    "Typed target value supplied by ${rule.javaClass.name}")
            }
        override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? =
            rule.lowerConstructor(call, language, scope)?.also {
                record(KlibDependencyDecision.Kind.TARGET_REPLACEMENT, call.symbol, language.source(call),
                    "Typed target constructor supplied by ${rule.javaClass.name}")
            }
        override fun lowerStatement(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? =
            if (call.symbol in candidateBodies) null else rule.lowerStatement(call, language, scope)?.also {
                record(KlibDependencyDecision.Kind.TARGET_REPLACEMENT, call.symbol, language.source(call),
                    "Target statements supplied by ${rule.javaClass.name}")
            }
    } }
    fun guard(call: IrFunctionAccessExpression, language: Language) {
        val owner = call.symbol.owner
        val module = owner.fileOrNull?.module
        if (!owner.isExternal && (module == null || module in loweringModules)) return
        val resolution = provider.resolve(call.symbol)
        val closureFailure = closure.rejected[call.symbol]
        val reason = when {
            closureFailure != null && closureFailure.symbol != call.symbol ->
                "The dependency body closure is blocked by a transitive declaration"
            closureFailure != null -> closureFailure.reason
            else -> (resolution as? FunctionBody.Unavailable)?.reason?.evidence
                ?: "The dependency call remains after common inlining and is not selected for emission."
        }
        val blocked = closureFailure?.takeIf { it.symbol != call.symbol }?.let { failure ->
            val declaration = failure.symbol.owner
            val file = declaration.fileOrNull
            " Transitive dependency ${failure.symbol.signature ?: symbolName(declaration)} at " +
                "${libraryLocations[file?.module] ?: "<unknown-library>"}; declaration " +
                "${file?.fileEntry?.name ?: "<no-file>"}:${declaration.startOffset}..${declaration.endOffset}: ${failure.reason}."
        } ?: ""
        val detail = (if (reason.endsWith('.')) reason else "$reason.") +
            "$blocked Fallback decision: no declared typed adapter accepted the call."
        record(KlibDependencyDecision.Kind.REJECTED, call.symbol, language.source(call), detail)
        report(decisions.last())
        throw Unsupported(Diagnostic("UNSUPPORTED_KLIB_DEPENDENCY",
            "KLIB dependency ${call.symbol.signature ?: symbolName(owner)} at " +
                "${libraryLocations[module] ?: "<unknown-library>"}; declaration " +
                "${owner.fileOrNull?.fileEntry?.name ?: "<no-file>"}:${owner.startOffset}..${owner.endOffset}: " +
                detail, language.source(call)))
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

private fun dependencyBodyClosure(
    modules: List<IrModuleFragment>,
    bodies: FunctionBodies,
    linkedModules: Set<IrModuleFragment>,
    unitClass: IrClassSymbol,
    primitiveSymbols: Set<IrFunctionSymbol>,
    adapterFallbackSymbols: Set<IrFunctionSymbol>,
): DependencyBodyClosure {
    val translated = modules.toSet()
    val discovered = linkedMapOf<IrFunctionSymbol, FunctionBody.Available>()
    val dependencies = linkedMapOf<IrFunctionSymbol, MutableList<IrFunctionSymbol>>()
    val rejected = linkedMapOf<IrFunctionSymbol, DependencyBodyRejection>()
    val roots = mutableListOf<IrFunctionSymbol>()
    fun dependency(symbol: IrFunctionSymbol): Boolean {
        val module = symbol.owner.fileOrNull?.module
        return module in linkedModules && module !in translated && symbol !in primitiveSymbols
    }
    lateinit var discover: (IrFunctionSymbol) -> Unit
    discover = fun(symbol: IrFunctionSymbol) {
        if (!dependency(symbol) || symbol in discovered || symbol in rejected) return
        val body = bodies.resolve(symbol) as? FunctionBody.Available
        if (body == null) {
            // A missing body is itself the evidence that a typed adapter may be consulted.
            // The final boundary still rejects the call when no rule accepts it.
            return
        }
        if (!body.isLoadableCommonBody(unitClass)) {
            if (symbol !in adapterFallbackSymbols) rejected[symbol] = DependencyBodyRejection(symbol,
                "The dependency body is incompatible with ETS common-body reuse")
            return
        }
        discovered[symbol] = body
        val children = dependencies.getOrPut(symbol) { mutableListOf() }
        body.body.acceptChildrenVoid(object : org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid {
            override fun visitElement(element: org.jetbrains.kotlin.ir.IrElement) {
                if (element is IrFunctionAccessExpression && dependency(element.symbol)) {
                    children += element.symbol
                    discover(element.symbol)
                }
                element.acceptChildrenVoid(this)
            }
        })
    }
    val rootVisitor = object : org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid {
        override fun visitElement(element: org.jetbrains.kotlin.ir.IrElement) {
            if (element is IrFunctionAccessExpression && dependency(element.symbol)) {
                roots += element.symbol
                discover(element.symbol)
            }
            element.acceptChildrenVoid(this)
        }
    }
    modules.forEach { it.acceptChildrenVoid(rootVisitor) }
    var changed: Boolean
    do {
        changed = false
        dependencies.forEach { (symbol, children) ->
            val cause = children.firstNotNullOfOrNull(rejected::get)
            if (symbol !in rejected && cause != null) {
                rejected[symbol] = cause
                changed = true
            }
        }
    } while (changed)
    val admitted = linkedMapOf<IrFunctionSymbol, FunctionBody.Available>()
    fun admit(symbol: IrFunctionSymbol) {
        val body = discovered[symbol] ?: return
        if (symbol in rejected || admitted.putIfAbsent(symbol, body) != null) return
        dependencies[symbol].orEmpty().forEach(::admit)
    }
    roots.forEach(::admit)
    return DependencyBodyClosure(admitted, rejected)
}

private fun FunctionBody.Available.isLoadableCommonBody(unitClass: IrClassSymbol): Boolean {
    if (declaration.valueParameters.any { it.varargElementType != null || it.defaultValue != null ||
            !isTargetIdentifier(it.name.asString()) } ||
        !(declaration.isInline || declaration is IrSimpleFunction && declaration.parent is IrFile)) return false
    var loadable = true
    body.acceptChildrenVoid(object : org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid {
        override fun visitElement(element: org.jetbrains.kotlin.ir.IrElement) {
            if (element is IrGetObjectValue) {
                val owner = element.symbol.owner
                if (element.symbol !== unitClass && sourceFile(owner) != null) loadable = false
            }
            if (loadable) element.acceptChildrenVoid(this)
        }
    })
    return loadable
}

private fun materializeOrdinaryBodies(declarations: List<org.jetbrains.kotlin.ir.declarations.IrFunction>):
    List<IrModuleFragment> {
    val functions = declarations.map { declaration ->
        require(declaration is IrSimpleFunction && declaration.parent is IrFile) {
            "Ordinary KLIB body reuse currently requires a top-level simple function: ${symbolName(declaration)}"
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
                check(sourceFile.declarations.remove(function)) { "Admitted KLIB function is not owned by its source file" }
                function.parent = targetFile
                targetFile.declarations += function
            }
        }
        targetModule
    }
}
