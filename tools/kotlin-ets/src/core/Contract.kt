package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrValueSymbol
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.isUnit
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable
import org.jetbrains.kotlin.load.kotlin.JvmPackagePartSource
import org.jetbrains.kotlin.load.kotlin.KotlinJvmBinarySourceElement

data class Diagnostic(val code: String, val message: String, val source: SourceSpan)
class Unsupported(val diagnostic: Diagnostic) : RuntimeException(diagnostic.message)

fun sourceFile(declaration: IrDeclaration): IrFile? {
    var current = declaration
    while (true) {
        // A deserialized owner's provenance file is not an input source module.
        if (current is IrClass && (current.source is KotlinJvmBinarySourceElement || current.source is JvmPackagePartSource)) return null
        val parent = current.parent
        if (parent !is IrDeclaration) return parent as? IrFile
        current = parent
    }
}
fun symbolName(declaration: IrDeclarationWithName): String =
    declaration.fqNameWhenAvailable?.asString() ?: declaration.name.asString()

data class UiDegradation(val diagnostic: Diagnostic, val capability: String, val action: String, val impact: String)

class DiagnosticSink(var currentFile: String? = null, var reportUiDegradation: Boolean = false) {
    val degradations = linkedSetOf<UiDegradation>()
    internal val omittedUiElements = java.util.Collections.newSetFromMap(java.util.IdentityHashMap<IrElement, Boolean>())
    fun unsupported(element: IrElement, message: String): Nothing = throw Unsupported(
        Diagnostic("UNSUPPORTED", message, sourceSpan(element, this)))

    fun omitUi(element: IrElement, message: String, capability: String, action: String, impact: String,
        discarded: List<IrElement> = listOf(element)) {
        // Reporting is not permission to discard UI or business behavior. Only
        // explicit framework projections approved for this migration may omit IR.
        if (!reportUiDegradation || action !in setOf("static_animation_value", "omitted_animation_effect",
                "omitted_animation_modifier", "project_theme_replacement", "omitted_theme_effect",
                "omitted_private_modifier")) unsupported(element, message)
        omittedUiElements.addAll(discarded)
        degradations += UiDegradation(Diagnostic("UNSUPPORTED", message, sourceSpan(element, this)), capability, action, impact)
    }

    fun verifyNoSilentFallback(program: EtsProgram) {
        if (omittedUiElements.isNotEmpty() && degradations.isEmpty()) {
            unsupported(omittedUiElements.first(), "Omitted UI requires an explicit degradation record")
        }
        fun explicitlyRecorded(function: EtsFunction) = degradations.any { degradation ->
            val source = degradation.diagnostic.source
            source.file == function.source.file && source.start >= function.source.start && source.end <= function.source.end
        }
        val declarations = program.files.flatMap { it.declarations }
        (declarations.filterIsInstance<EtsFunction>() + declarations.filterIsInstance<EtsClass>()
            .flatMap { it.members }.filterIsInstance<EtsFunction>())
            .firstOrNull { (it.builder || it.build) && it.body.isEmpty() && !explicitlyRecorded(it) }?.let {
                throw Unsupported(Diagnostic("UNSUPPORTED",
                    "Empty UI builder requires an explicit degradation or unsupported record", it.source))
            }
    }
}

class Scope(
    val bindings: MutableMap<IrValueSymbol, EtsExpression> = linkedMapOf(),
    val aliases: MutableMap<IrValueSymbol, IrExpression> = linkedMapOf(),
    var callRule: CallRule? = null,
    val callRules: List<CallRule> = emptyList(),
    val ambientValues: MutableMap<String, EtsExpression> = linkedMapOf(),
) {
    fun fork() = Scope(LinkedHashMap(bindings), LinkedHashMap(aliases), callRule, callRules, LinkedHashMap(ambientValues))
}

interface Language {
    val callRules: List<CallRule> get() = emptyList()
    val diagnostics: DiagnosticSink? get() = null
    fun source(element: IrElement): SourceSpan
    fun type(type: IrType): EtsType
    fun expression(expression: IrExpression, scope: Scope): EtsExpression
    fun statements(body: IrBody, scope: Scope): List<EtsStatement>
    fun function(function: IrSimpleFunction, scope: Scope = Scope()): EtsFunction
    fun clazz(declaration: IrClass): EtsClass
    fun interfaceDefaults(declaration: IrClass): List<EtsFunction> = emptyList()
}

fun interface CallRule {
    /** Framework source projections run before the shared dependency worklist and language lowerings. */
    fun prepareSource(declaration: IrDeclaration, diagnostics: DiagnosticSink) {}

    /** Owned target declarations participate in the same validation and module linking as source declarations. */
    fun targetFiles(program: EtsProgram): List<EtsFile> = emptyList()

    fun targetImports(program: EtsProgram): List<EtsImport> = emptyList()

    /** Native type signatures for validation only; these declarations are not printed. */
    fun targetContracts(program: EtsProgram): List<EtsClass> = emptyList()

    /** Platform value representation; the shared call checker still validates every result. */
    fun mapType(type: IrType, language: Language): EtsType? = null

    /** A typed value, or null to decline. Never return void for an object-valued call. */
    fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression?

    /** Object construction is value-producing, even when its result is discarded. */
    fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? = null

    fun lowerObject(value: IrGetObjectValue, language: Language, scope: Scope): EtsExpression? = null

    fun lowerField(value: IrGetField, language: Language, scope: Scope): EtsExpression? = null

    /** Only consulted when the source result is discarded. Empty means a handled no-op. */
    fun lowerStatement(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? = null

    /** Only consulted in UI context. Empty means a handled no-op; source result must be Unit. */
    fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? = null
}

fun linkAdapterDeclarations(program: EtsProgram, rules: List<CallRule>): EtsProgram {
    val files = program.files.associateByTo(linkedMapOf()) { it.sourcePath }
    var linked = program
    while (true) {
        var changed = false
        rules.flatMap { it.targetFiles(linked) }.forEach { file ->
            val previous = files[file.sourcePath]
            require(previous == null || previous == file) { "Conflicting adapter target file: ${file.sourcePath}" }
            if (previous == null) { files[file.sourcePath] = file; changed = true }
        }
        linked = program.copy(files = files.values.toList())
        if (!changed) {
            val contracts = linked.externalClasses.toMutableMap()
            rules.flatMap { it.targetContracts(linked) }.forEach { declaration ->
                val previous = contracts.putIfAbsent(declaration.symbol.id, declaration)
                require(previous == null || previous == declaration) { "Conflicting adapter native type: ${declaration.name}" }
            }
            return linked.copy(imports = (linked.imports + rules.flatMap { it.targetImports(linked) }).distinct(), externalClasses = contracts)
        }
    }
}

enum class CallContext { VALUE, STATEMENT, UI }

sealed interface CallResult {
    data class Value(val expression: EtsExpression) : CallResult
    data class Statements(val statements: List<EtsStatement>) : CallResult
    data class Ui(val statements: List<EtsStatement>) : CallResult
}

private fun checkedAdapterValue(call: IrExpression, expression: EtsExpression,
    language: Language): EtsExpression {
    val expected = language.type(call.type)
    if (!etsAssignable(expression.type, expected)) throw Unsupported(Diagnostic("UNSUPPORTED",
        "Invalid call adapter result for ${when (call) {
            is IrFunctionAccessExpression -> symbolName(call.symbol.owner)
            is IrGetObjectValue -> symbolName(call.symbol.owner)
            is IrGetField -> symbolName(call.symbol.owner)
            else -> call.javaClass.simpleName
        }}: expected $expected, got ${expression.type}",
        language.source(call)))
    return expression
}

fun adaptConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? {
    for (rule in listOfNotNull(scope.callRule) + scope.callRules + language.callRules) {
        rule.lowerConstructor(call, language, scope)?.let { return checkedAdapterValue(call, it, language) }
    }
    return null
}

fun adaptObject(value: IrGetObjectValue, language: Language, scope: Scope): EtsExpression? {
    for (rule in listOfNotNull(scope.callRule) + scope.callRules + language.callRules) {
        rule.lowerObject(value, language, scope)?.let { return checkedAdapterValue(value, it, language) }
    }
    return null
}

fun adaptField(value: IrGetField, language: Language, scope: Scope): EtsExpression? {
    for (rule in listOfNotNull(scope.callRule) + scope.callRules + language.callRules) {
        rule.lowerField(value, language, scope)?.let { return checkedAdapterValue(value, it, language) }
    }
    return null
}

fun adaptCall(call: IrCall, language: Language, scope: Scope, context: CallContext): CallResult? {
    fun reject(message: String): Nothing = throw Unsupported(Diagnostic("UNSUPPORTED", message, language.source(call)))
    fun explicitlyRecorded() = language.diagnostics?.degradations?.any {
        it.diagnostic.source == language.source(call)
    } == true
    fun checkedValue(expression: EtsExpression): CallResult.Value {
        return CallResult.Value(checkedAdapterValue(call, expression, language))
    }
    for (rule in listOfNotNull(scope.callRule) + scope.callRules + language.callRules) {
        when (context) {
            CallContext.VALUE -> rule.lower(call, language, scope)?.let { return checkedValue(it) }
            CallContext.STATEMENT -> {
                rule.lowerStatement(call, language, scope)?.let {
                    if (it.isEmpty() && !explicitlyRecorded())
                        reject("Empty statement adapter result requires an explicit degradation or unsupported record")
                    return CallResult.Statements(it)
                }
                rule.lower(call, language, scope)?.let { return checkedValue(it) }
            }
            CallContext.UI -> rule.lowerUi(call, language, scope)?.let {
                if (!call.type.isUnit()) reject("UI call adapter requires kotlin.Unit: ${symbolName(call.symbol.owner)}")
                if (it.isEmpty() && !explicitlyRecorded())
                    reject("Empty UI adapter result requires an explicit degradation or unsupported record")
                return CallResult.Ui(it)
            }
        }
    }
    return null
}

fun sourceSpan(element: IrElement, diagnostics: DiagnosticSink) =
    SourceSpan((element as? IrDeclaration)?.let(::sourceFile)?.fileEntry?.name ?: diagnostics.currentFile,
        element.startOffset, element.endOffset)

fun argument(call: IrFunctionAccessExpression, name: String): IrExpression? =
    call.symbol.owner.valueParameters.indexOfFirst { it.name.asString() == name }
        .takeIf { it >= 0 }?.let { call.getValueArgument(it) }

fun lambda(expression: IrExpression?, scope: Scope): IrFunction? = when (expression) {
    is IrFunctionExpression -> expression.function
    is IrGetValue -> scope.aliases[expression.symbol]?.let { lambda(it, scope) }
    is IrBlock -> lambda(expression.statements.lastOrNull() as? IrExpression, scope)
    else -> null
}

tailrec fun resolveExpression(expression: IrExpression?, scope: Scope): IrExpression? = when (expression) {
    is IrGetValue -> resolveExpression(scope.aliases[expression.symbol]
        ?: (expression.symbol.owner as? IrVariable)?.takeUnless { it.isVar }?.initializer, scope)
    is IrTypeOperatorCall -> resolveExpression(expression.argument, scope)
    is IrBlock -> resolveExpression(expression.statements.lastOrNull() as? IrExpression, scope)
    else -> expression
}

fun resolvedCall(expression: IrExpression?, scope: Scope): IrCall? =
    resolveExpression(expression, scope) as? IrCall

fun compositionLocalName(expression: IrExpression?, scope: Scope): String? =
    when (val resolved = resolveExpression(expression, scope)) {
        is IrCall -> resolved.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName)
            ?: getterPropertyName(symbolName(resolved.symbol.owner))
        is IrGetField -> resolved.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName)
            ?: symbolName(resolved.symbol.owner)
        else -> null
    }

fun isCompositionLocalCurrent(owner: IrDeclarationWithName): Boolean {
    val api = symbolName(owner)
    val property = (owner as? IrSimpleFunction)?.correspondingPropertySymbol?.owner?.let(::symbolName)
        ?: (owner as? IrProperty)?.let(::symbolName)
    return property in COMPOSITION_LOCAL_CURRENT || api in COMPOSITION_LOCAL_CURRENT ||
        getterPropertyName(api) in COMPOSITION_LOCAL_CURRENT
}

private val COMPOSITION_LOCAL_CURRENT = setOf(
    "androidx.compose.runtime.CompositionLocal.current",
    "androidx.compose.runtime.ProvidableCompositionLocal.current",
    "androidx.compose.runtime.CompositionLocal.<get-current>",
    "androidx.compose.runtime.ProvidableCompositionLocal.<get-current>",
)

private fun getterPropertyName(api: String): String? = when {
    api.endsWith(".<get-current>") -> api.removeSuffix(".<get-current>") + ".current"
    else -> null
}
