@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*

internal val exceptionParents = linkedMapOf(
    "Throwable" to "", "Exception" to "Throwable", "RuntimeException" to "Exception",
    "IllegalArgumentException" to "RuntimeException", "IllegalStateException" to "RuntimeException",
    "NullPointerException" to "RuntimeException", "ClassCastException" to "RuntimeException",
    "ArithmeticException" to "RuntimeException", "IndexOutOfBoundsException" to "RuntimeException",
    "ArrayIndexOutOfBoundsException" to "IndexOutOfBoundsException", "NoSuchElementException" to "RuntimeException",
    "ConcurrentModificationException" to "RuntimeException", "UnsupportedOperationException" to "RuntimeException",
    "NoWhenBranchMatchedException" to "RuntimeException", "Error" to "Throwable", "LinkageError" to "Error",
    "ExceptionInInitializerError" to "LinkageError", "NoClassDefFoundError" to "LinkageError", "AssertionError" to "Error")

internal fun exceptionCategory(owner: IrClass?): String? {
    if (owner == null || sourceFile(owner) != null) return null
    val name = symbolName(owner)
    val short = name.substringAfterLast('.')
    return short.takeIf { it in exceptionParents && name.substringBeforeLast('.') in setOf("kotlin", "java.lang", "java.util") }
}

internal fun exceptionCheck(value: EtsExpression, category: String, at: SourceSpan): EtsExpression = EtsCall(
    EtsReference(EtsSymbol("stdlib:__etsIsFailure", "__etsIsFailure",
        EtsFunctionType(listOf(EtsNullableType(EtsTypes.OBJECT), EtsTypes.STRING), EtsTypes.BOOLEAN), at, true)),
    listOf(value, EtsLiteral(category, EtsTypes.STRING, at)), EtsTypes.BOOLEAN, at)

internal object ExceptionRules : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? =
        exceptionCategory(type.classOrNull?.owner)?.let { targetErrorType }

    fun constructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? {
        val category = exceptionCategory(call.symbol.owner.parentAsClass) ?: return null
        return EtsNew(targetErrorType, constructorArguments(call, category, language, scope), language.source(call))
    }

    fun constructorArguments(call: IrFunctionAccessExpression, category: String, language: Language, scope: Scope): List<EtsExpression> {
        if (call.valueArgumentsCount > 1 || call.symbol.owner.valueParameters.any { !it.type.makeNotNull().isString() })
            throw Unsupported(Diagnostic("UNSUPPORTED", "Exception constructors currently require an optional message", language.source(call)))
        val message = (if (call.valueArgumentsCount > 0) call.getValueArgument(0) else null)?.let { language.expression(it, scope) }
            ?: EtsLiteral(null, EtsTypes.NULL, language.source(call))
        return listOf(EtsLiteral(category, EtsTypes.STRING, language.source(call)), message)
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        val original = if (owner.isFakeOverride) owner.collectRealOverrides().singleOrNull() ?: return null else owner
        if (exceptionCategory(original.parent as? IrClass) == null) return null
        val receiver = call.dispatchReceiver ?: return null
        if (original.correspondingPropertySymbol?.owner?.name?.asString() == "message")
            return EtsMember(language.expression(receiver, scope), "sourceMessage", language.type(call.type), language.source(call))
        return null
    }
}
