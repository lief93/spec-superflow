@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class, org.jetbrains.kotlin.fir.symbols.SymbolInternals::class)
package dev.ets

import java.nio.file.Path
import java.util.IdentityHashMap
import org.jetbrains.kotlin.fir.FirElement
import org.jetbrains.kotlin.fir.backend.toIrType
import org.jetbrains.kotlin.fir.expressions.FirFunctionCall
import org.jetbrains.kotlin.fir.pipeline.FirResult
import org.jetbrains.kotlin.fir.pipeline.Fir2IrActualizedResult
import org.jetbrains.kotlin.fir.references.FirResolvedNamedReference
import org.jetbrains.kotlin.fir.symbols.impl.FirFunctionSymbol
import org.jetbrains.kotlin.fir.types.*
import org.jetbrains.kotlin.fir.visitors.FirVisitorVoid
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.symbols.IrFunctionSymbol
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.types.AbstractTypeChecker

data class SourceCapture(val readType: IrType, val writeType: IrType?)

/** Preserve FIR facts that the official FIR2IR type approximator intentionally erases. */
internal class CallCaptures(analyzed: FirResult, translated: Fir2IrActualizedResult) {
    private data class Key(val file: String, val start: Int, val end: Int, val symbol: IrFunctionSymbol)
    private data class Binding(val key: Key, val arity: Int, val arguments: Map<Int, SourceCapture>)
    private val bindings = IdentityHashMap<Any, Binding>()

    init {
        fun path(value: String) = Path.of(value).toAbsolutePath().normalize().toString()
        val calls = mutableMapOf<Key, MutableList<IrCall>>()
        for (file in translated.irModuleFragment.files) file.acceptChildrenVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
            override fun visitCall(expression: IrCall) {
                val key = Key(path(file.fileEntry.name), expression.startOffset, expression.endOffset, expression.symbol)
                calls.getOrPut(key) { mutableListOf() }.add(expression)
                expression.acceptChildrenVoid(this)
            }
        })
        for (output in analyzed.outputs) for (file in output.fir) file.accept(object : FirVisitorVoid() {
            override fun visitElement(element: FirElement) { element.acceptChildren(this) }
            override fun visitFunctionCall(functionCall: FirFunctionCall) {
                functionCall.acceptChildren(this)
                val captures = functionCall.typeArguments.mapIndexedNotNull { index, projection ->
                    ((projection as? FirTypeProjectionWithVariance)?.typeRef?.coneType as? ConeCapturedType)?.let { index to it }
                }
                if (captures.isEmpty()) return
                val span = SourceSpan(file.sourceFile?.path, functionCall.source?.startOffset ?: -1, functionCall.source?.endOffset ?: -1)
                fun reject(message: String): Nothing = throw Unsupported(Diagnostic("UNSUPPORTED", message, span))
                val symbol = (functionCall.calleeReference as? FirResolvedNamedReference)?.resolvedSymbol as? FirFunctionSymbol<*>
                    ?: reject("Captured call requires a resolved official function symbol")
                val key = Key(path(span.file ?: reject("Captured call requires source ownership")), span.start, span.end,
                    translated.components.declarationStorage.getIrFunctionSymbol(symbol))
                val call = calls[key]?.singleOrNull() ?: reject("Captured call requires one exact FIR/IR symbol and source binding")
                val arguments = captures.associate { (index, capture) ->
                    val bounds = capture.constructor.supertypes.orEmpty()
                    val upper = bounds.firstOrNull { candidate -> bounds.all { AbstractTypeChecker.isSubtypeOf(output.session.typeContext, candidate, it) } }
                        ?: reject("Captured call requires one representable upper bound")
                    fun convert(type: ConeKotlinType) = (if (capture.isMarkedNullable)
                        type.withNullability(true, output.session.typeContext) else type).toIrType(translated.components)
                    index to SourceCapture(convert(upper), capture.lowerType?.let(::convert))
                }
                bindings[call.attributeOwnerId] = Binding(key, call.typeArgumentsCount, arguments)
            }
        })
    }

    fun arguments(call: IrCall): Map<Int, SourceCapture> {
        val binding = bindings[call.attributeOwnerId] ?: return emptyMap()
        if (call.symbol != binding.key.symbol || call.typeArgumentsCount != binding.arity) throw Unsupported(Diagnostic(
            "UNSUPPORTED", "Lowered captured call changed its original generic binding",
            SourceSpan(binding.key.file, binding.key.start, binding.key.end)))
        return binding.arguments
    }
}
