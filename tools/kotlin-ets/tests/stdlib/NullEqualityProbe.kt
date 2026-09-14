@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.tests.stdlib

import dev.ets.*
import java.io.File
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.IrDeclarationOrigin
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    val directory = File(args[0])
    withKotlinFrontend(args.drop(1)) { session ->
        File(directory, "actual.ir").writeText(session.module.dump())
        val calls = mutableListOf<IrCall>()
        session.module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
            override fun visitCall(expression: IrCall) {
                if (symbolName(expression.symbol.owner) == "kotlin.internal.ir.EQEQ") calls.add(expression)
                expression.acceptChildrenVoid(this)
            }
        })
        val nullCalls = calls.filter { call -> (0 until call.valueArgumentsCount).any {
            (call.getValueArgument(it) as? IrConst)?.kind == IrConstKind.Null
        } }
        File(directory, "null-calls.txt").writeText(nullCalls.joinToString("\n") { call ->
            "${call.startOffset}..${call.endOffset} ${call.symbol.owner.render()}\n${call.dump()}"
        })
        check(nullCalls.any { it.startOffset == 209 && it.endOffset == 221 }) { "Original quantifier failure path missing" }
        val backend = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules()))
        val intType = calls.flatMap { call -> (0 until call.valueArgumentsCount).mapNotNull(call::getValueArgument) }
            .first { it.type.isInt() }.type
        var mutations = 0
        for (call in nullCalls) {
            val owner = call.symbol.owner
            val inputs = mutableListOf<IrExpression>()
            fun language(inputs: MutableList<IrExpression>): Language = object : Language by backend.language {
                override fun expression(expression: IrExpression, scope: Scope): EtsExpression {
                    inputs.add(expression)
                    return EtsReference(EtsSymbol("input${inputs.size}", "input${inputs.size}",
                        type(expression.type), source(expression)))
                }
            }
            val rules = StandardLibraryRules()
            val expression = checkNotNull(rules.lower(call, language(inputs), Scope())) as EtsBinary
            check(expression.operator == "===" && expression.type == EtsTypes.BOOLEAN)
            check(inputs == listOf(call.getValueArgument(0), call.getValueArgument(1)))
            fun reject(label: String, change: () -> Unit, restore: () -> Unit) {
                try {
                    change()
                    val ignored = mutableListOf<IrExpression>()
                    check(rules.lower(call, language(ignored), Scope()) == null) { "Accepted malformed null equality: $label" }
                    check(ignored.isEmpty())
                    mutations++
                } finally { restore() }
            }
            val first = call.getValueArgument(0)!!
            val second = call.getValueArgument(1)!!
            val result = call.type
            val declaredResult = owner.returnType
            val origin = owner.origin
            val nullIndex = if ((first as? IrConst)?.kind == IrConstKind.Null) 0 else 1
            val nullValue = call.getValueArgument(nullIndex)!!
            val nullType = nullValue.type
            val nonNullExpression = call.getValueArgument(1 - nullIndex)!!
            reject("no literal null", { call.putValueArgument(nullIndex, nonNullExpression) },
                { call.putValueArgument(nullIndex, nullValue) })
            reject("malformed null type", { nullValue.type = intType }, { nullValue.type = nullType })
            reject("missing operand", { call.putValueArgument(1, null) }, { call.putValueArgument(1, second) })
            reject("dispatch", { call.insertDispatchReceiver(first) }, { call.removeDispatchReceiver() })
            reject("extension", { call.insertExtensionReceiver(first) }, { call.removeExtensionReceiver() })
            reject("super", { call.superQualifierSymbol = intType.classOrNull }, { call.superQualifierSymbol = null })
            reject("call result", { call.type = intType }, { call.type = result })
            reject("declaration result", { owner.returnType = intType }, { owner.returnType = declaredResult })
            reject("source origin", { owner.origin = IrDeclarationOrigin.DEFINED }, { owner.origin = origin })
            for (parameter in owner.valueParameters) {
                val type = parameter.type
                reject("declared operand", { parameter.type = intType }, { parameter.type = type })
            }
        }
        check(nullCalls.size >= 10 && mutations == nullCalls.size * 11)
        println("PASS ${nullCalls.size} actual literal-null signatures and $mutations malformed calls")
        val quantifierFile = session.module.files.single { it.fileEntry.name.endsWith("QuantifierCases.kt") }
        val failingFunction = quantifierFile.declarations.filterIsInstance<IrSimpleFunction>().single { it.name.asString() == "quantify" }
        try {
            EtsBackend(DiagnosticSink(quantifierFile.fileEntry.name), listOf(StandardLibraryRules()))
                .language.function(failingFunction)
        } catch (failure: Unsupported) {
            File(directory, "original-failure.txt").writeText(failure.diagnostic.toString())
            throw failure
        }
        val program = try { backend.lower(session.module) } catch (failure: Unsupported) {
            File(directory, "backend-failure.txt").writeText(failure.diagnostic.toString())
            throw failure
        }
        val modules = emitEtsModules(program, StandardLibraryRuntime)
        modules.forEach { (name, text) -> File(directory, name).writeText(text) }
        println("PASS full official IR/backend original quantifier null path, ${nullCalls.size} null calls, $mutations malformed signatures")
    }
}
