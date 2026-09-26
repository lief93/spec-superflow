@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.cli.common.CommonCompilerPerformanceManager
import org.jetbrains.kotlin.cli.common.arguments.*
import org.jetbrains.kotlin.cli.common.fir.FirDiagnosticsCompilerResultsReporter
import org.jetbrains.kotlin.cli.common.messages.*
import org.jetbrains.kotlin.cli.pipeline.ArgumentsPipelineArtifact
import org.jetbrains.kotlin.cli.pipeline.jvm.*
import org.jetbrains.kotlin.com.intellij.openapi.util.Disposer
import org.jetbrains.kotlin.config.Services
import org.jetbrains.kotlin.ir.declarations.IrModuleFragment
import org.jetbrains.kotlin.ir.declarations.IrFunction
import org.jetbrains.kotlin.ir.expressions.IrBody
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.symbols.IrFunctionSymbol
import org.jetbrains.kotlin.ir.types.IrSimpleType
import org.jetbrains.kotlin.ir.types.IrTypeProjection
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.IrTypeSystemContext
import org.jetbrains.kotlin.ir.types.IrTypeSystemContextImpl
import org.jetbrains.kotlin.ir.util.fileOrNull
import org.jetbrains.kotlin.ir.util.isSubtypeOf
import org.jetbrains.kotlin.types.model.CaptureStatus
import org.jetbrains.kotlin.types.Variance

sealed interface FunctionBody {
    data class Available(val declaration: IrFunction, val body: IrBody, val source: SourceSpan,
        val origin: Origin) : FunctionBody
    data class Unavailable(val reason: Reason) : FunctionBody
    sealed interface Origin {
        data object Source : Origin
        data class SerializedJvmIr(val binaryLocation: String) : Origin
        data class SerializedKlibIr(val libraryLocation: String, val moduleName: String) : Origin
    }
    enum class Reason(val evidence: String) {
        UNBOUND_SYMBOL("The function symbol is unbound."),
        EXTERNAL_DECLARATION("The declaration is external and has no source implementation."),
        OUTSIDE_MODULE("The declaration is outside the source module."),
        NO_BODY("The source declaration has no function body."),
        NON_INLINE_BINARY("Loading non-inline JVM binary bodies is not supported."),
        NO_BINARY_METADATA("JVM binary metadata is unavailable for this declaration."),
        NO_SERIALIZED_IR("JVM binary metadata contains no serialized IR."),
        NON_TRANSLATED_KLIB("The linked KLIB is dependency-only; its body was not selected for reuse.")
    }
}

fun interface FunctionBodies {
    fun resolve(symbol: IrFunctionSymbol): FunctionBody
}

interface SourceTypes {
    fun capture(type: IrSimpleType): IrSimpleType
    fun isSubtypeOf(actual: IrType, expected: IrType): Boolean
    fun callCaptures(call: IrCall): Map<Int, SourceCapture>
}

/** Borrowed official IR, valid only inside withKotlinFrontend. No serialized IR interchange. */
class KotlinFrontendSession internal constructor(private val fragment: IrModuleFragment, private val binaryBodies: FunctionBodies,
    private val typeSystem: IrTypeSystemContext, private val callCaptures: CallCaptures) {
    private var active = true
    private val files = fragment.files.toSet()
    private fun checkActive() = check(active) { "Kotlin frontend session is closed" }
    val module: IrModuleFragment get() { checkActive(); return fragment }
    private val typeQueries = object : SourceTypes {
        override fun capture(type: IrSimpleType): IrSimpleType {
            checkActive()
            // Capturing is unnecessary for invariant arguments. Relocated inner owners
            // no longer satisfy extractTypeParameters' original nesting prerequisite.
            if (type.arguments.all { it is IrTypeProjection && it.variance == Variance.INVARIANT }) return type
            return typeSystem.captureFromArguments(type, CaptureStatus.FOR_SUBTYPING) ?: type
        }
        override fun isSubtypeOf(actual: IrType, expected: IrType): Boolean {
            checkActive()
            return actual.isSubtypeOf(expected, typeSystem)
        }
        override fun callCaptures(call: IrCall): Map<Int, SourceCapture> {
            checkActive()
            return callCaptures.arguments(call)
        }
    }
    val types: SourceTypes get() { checkActive(); return typeQueries }
    private val resolver = FunctionBodies { symbol ->
        checkActive()
        when {
            !symbol.isBound -> FunctionBody.Unavailable(FunctionBody.Reason.UNBOUND_SYMBOL)
            symbol.owner.isExternal -> FunctionBody.Unavailable(FunctionBody.Reason.EXTERNAL_DECLARATION)
            symbol.owner.fileOrNull !in files -> binaryBodies.resolve(symbol)
            else -> {
                val declaration = symbol.owner
                declaration.body?.let { body -> FunctionBody.Available(declaration, body,
                    SourceSpan(declaration.fileOrNull!!.fileEntry.name, declaration.startOffset, declaration.endOffset),
                    FunctionBody.Origin.Source)
                } ?: FunctionBody.Unavailable(FunctionBody.Reason.NO_BODY)
            }
        }
    }
    val bodies: FunctionBodies get() { checkActive(); return resolver }
    internal fun rebindInlinedCaptures() { checkActive(); callCaptures.rebindInlined(fragment) }
    internal fun close() { active = false }
}

/** Keep resolved compiler objects alive through target emission; never round-trip through JSON. */
fun <T> withKotlinModule(arguments: List<String>, emit: (IrModuleFragment) -> T): T {
    return withKotlinFrontend(arguments) { emit(it.module) }
}

fun <T> withKotlinFrontend(arguments: List<String>, entry: String? = null,
    runEtsLowerings: Boolean = true,
    prepareModule: (IrModuleFragment) -> Unit = {},
    prepareDeclaration: (org.jetbrains.kotlin.ir.declarations.IrDeclaration) -> Unit = {},
    externalSourceType: (org.jetbrains.kotlin.ir.types.IrType) -> Boolean = { false },
    externalSourceCall: (org.jetbrains.kotlin.ir.declarations.IrSimpleFunction) -> Boolean = { false },
    targetOwnsSourceArgument: (org.jetbrains.kotlin.ir.expressions.IrCall, Int) -> Boolean = { _, _ -> false },
    retainSourceDefault: (org.jetbrains.kotlin.ir.declarations.IrValueParameter) -> Boolean = { true },
    retainUnreferencedFileInitializer: (org.jetbrains.kotlin.ir.declarations.IrProperty) -> Boolean = { true },
    omitUnreferencedFileInitializer: (org.jetbrains.kotlin.ir.declarations.IrProperty) -> Unit = {},
    emit: (KotlinFrontendSession) -> T): T {
    val disposable = Disposer.newDisposable()
    var session: KotlinFrontendSession? = null
    val messages = GroupingMessageCollector(PrintingMessageCollector(System.err,
        MessageRenderer.PLAIN_FULL_PATHS, false), false, false)
    try {
        val options = K2JVMCompilerArguments()
        parseCommandLineArguments(arguments, options)
        val input = ArgumentsPipelineArtifact(options, Services.EMPTY, disposable, messages,
            object : CommonCompilerPerformanceManager("kotlin-ets") {})
        val configured = JvmConfigurationPipelinePhase.executePhase(input)
            ?: error("Kotlin configuration failed")
        val analyzed = JvmFrontendPipelinePhase.executePhase(configured)
            ?: error("Kotlin frontend failed")
        FirDiagnosticsCompilerResultsReporter.reportToMessageCollector(analyzed.diagnosticCollector, messages, true)
        check(!analyzed.diagnosticCollector.hasErrors && !messages.hasErrors()) {
            "Kotlin resolution failed; no target output"
        }
        val translated = JvmFir2IrPipelinePhase.executePhase(analyzed)
            ?: error("Kotlin FIR2IR failed")
        check(!translated.diagnosticCollector.hasErrors && !messages.hasErrors()) {
            "Kotlin FIR2IR diagnostics prohibit target output"
        }
        val frontend = KotlinFrontendSession(translated.result.irModuleFragment, BinaryBodies(translated),
            IrTypeSystemContextImpl(translated.result.irBuiltIns), CallCaptures(analyzed.result, translated.result))
        session = frontend
        prepareModule(frontend.module)
        entry?.let { System.err.println(selectSourceDeclarations(frontend.module, it, prepareDeclaration,
            externalSourceType = externalSourceType, externalSourceCall = externalSourceCall,
            targetOwnsSourceArgument = targetOwnsSourceArgument,
            retainUnreferencedFileInitializer = retainUnreferencedFileInitializer,
            omitUnreferencedFileInitializer = omitUnreferencedFileInitializer).report) }
        val lowering = if (runEtsLowerings) {
            EtsLoweringPhases.run(translated, frontend.bodies, frontend::rebindInlinedCaptures,
                retainSourceDefault)
        } else null
        check(!translated.diagnosticCollector.hasErrors && !messages.hasErrors()) {
            "Kotlin lowering diagnostics prohibit target output"
        }
        return try {
            emit(frontend)
        } catch (failure: Unsupported) {
            throw lowering?.let { explainUnavailableInlineBody(failure, it.unavailableInlineBodies) } ?: failure
        }
    } finally {
        session?.close()
        messages.flush()
        Disposer.dispose(disposable)
    }
}
