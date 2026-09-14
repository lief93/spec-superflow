package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrValueSymbol
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.isUnit
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable

data class Diagnostic(val code: String, val message: String, val source: SourceSpan)
class Unsupported(val diagnostic: Diagnostic) : RuntimeException(diagnostic.message)

fun sourceFile(declaration: IrDeclaration): IrFile? {
    var parent: IrDeclarationParent = declaration.parent
    while (parent is IrDeclaration) parent = parent.parent
    return parent as? IrFile
}
fun symbolName(declaration: IrDeclarationWithName): String =
    declaration.fqNameWhenAvailable?.asString() ?: declaration.name.asString()

class DiagnosticSink(var currentFile: String? = null) {
    fun unsupported(element: IrElement, message: String): Nothing = throw Unsupported(
        Diagnostic("UNSUPPORTED", message, SourceSpan(currentFile, element.startOffset, element.endOffset)))
}

class Scope(
    val bindings: MutableMap<IrValueSymbol, EtsExpression> = linkedMapOf(),
    val aliases: MutableMap<IrValueSymbol, IrExpression> = linkedMapOf(),
    var callRule: CallRule? = null,
    val callRules: List<CallRule> = emptyList(),
) {
    fun fork() = Scope(LinkedHashMap(bindings), LinkedHashMap(aliases), callRule, callRules)
}

interface Language {
    val callRules: List<CallRule> get() = emptyList()
    fun source(element: IrElement): SourceSpan
    fun type(type: IrType): EtsType
    fun expression(expression: IrExpression, scope: Scope): EtsExpression
    fun statements(body: IrBody, scope: Scope): List<EtsStatement>
    fun function(function: IrSimpleFunction, scope: Scope = Scope()): EtsFunction
    fun clazz(declaration: IrClass): EtsClass
}

fun interface CallRule {
    /** A typed value, or null to decline. Never return void for an object-valued call. */
    fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression?

    /** Only consulted when the source result is discarded. Empty means a handled no-op. */
    fun lowerStatement(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? = null

    /** Only consulted in UI context. Empty means a handled no-op; source result must be Unit. */
    fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? = null
}

enum class CallContext { VALUE, STATEMENT, UI }

sealed interface CallResult {
    data class Value(val expression: EtsExpression) : CallResult
    data class Statements(val statements: List<EtsStatement>) : CallResult
    data class Ui(val statements: List<EtsStatement>) : CallResult
}

fun adaptCall(call: IrCall, language: Language, scope: Scope, context: CallContext): CallResult? {
    fun reject(message: String): Nothing = throw Unsupported(Diagnostic("UNSUPPORTED", message, language.source(call)))
    fun checkedValue(expression: EtsExpression): CallResult.Value {
        val expected = language.type(call.type)
        if (!etsAssignable(expression.type, expected)) reject(
            "Invalid call adapter result for ${symbolName(call.symbol.owner)}: expected $expected, got ${expression.type}")
        return CallResult.Value(expression)
    }
    for (rule in listOfNotNull(scope.callRule) + scope.callRules + language.callRules) {
        when (context) {
            CallContext.VALUE -> rule.lower(call, language, scope)?.let { return checkedValue(it) }
            CallContext.STATEMENT -> {
                rule.lowerStatement(call, language, scope)?.let { return CallResult.Statements(it) }
                rule.lower(call, language, scope)?.let { return checkedValue(it) }
            }
            CallContext.UI -> rule.lowerUi(call, language, scope)?.let {
                if (!call.type.isUnit()) reject("UI call adapter requires kotlin.Unit: ${symbolName(call.symbol.owner)}")
                return CallResult.Ui(it)
            }
        }
    }
    return null
}

fun sourceSpan(element: IrElement, diagnostics: DiagnosticSink) =
    SourceSpan(diagnostics.currentFile, element.startOffset, element.endOffset)

fun argument(call: IrFunctionAccessExpression, name: String): IrExpression? =
    call.symbol.owner.valueParameters.indexOfFirst { it.name.asString() == name }
        .takeIf { it >= 0 }?.let { call.getValueArgument(it) }

fun lambda(expression: IrExpression?, scope: Scope): IrFunction? = when (expression) {
    is IrFunctionExpression -> expression.function
    is IrGetValue -> scope.aliases[expression.symbol]?.let { lambda(it, scope) }
    is IrBlock -> lambda(expression.statements.lastOrNull() as? IrExpression, scope)
    else -> null
}
