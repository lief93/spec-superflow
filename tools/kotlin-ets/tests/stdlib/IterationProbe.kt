@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.tests.stdlib

import dev.ets.*
import java.io.File
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    withKotlinFrontend(listOf(args[0], "-no-stdlib", "-no-reflect", "-classpath", args[1])) { session ->
        File(args[2], "actual.ir").writeText(session.module.dump())
        val signatures = linkedSetOf<String>()
        val calls = mutableListOf<IrCall>()
        session.module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
            override fun visitCall(expression: IrCall) {
                calls.add(expression)
                val owner = expression.symbol.owner
                signatures.add("${symbolName(owner)} | ${owner.render()} | receiver=" +
                    "${(expression.dispatchReceiver ?: expression.extensionReceiver)?.type?.render()} " +
                    "result=${expression.type.render()} body=${session.bodies.resolve(owner.symbol)::class.simpleName}")
                expression.acceptChildrenVoid(this)
            }
            override fun visitConstructorCall(expression: IrConstructorCall) {
                signatures.add("CONSTRUCTOR ${expression.symbol.owner.render()}")
                expression.acceptChildrenVoid(this)
            }
        })
        File(args[2], "calls.txt").writeText(signatures.sorted().joinToString("\n", postfix = "\n"))
        println(signatures.sorted().joinToString("\n"))
        if (args.getOrNull(3) == "--verify") {
            val intType = calls.first { it.type.isInt() }.type
            val booleanType = calls.first { it.type.isBoolean() }.type
            var accepted = 0
            var mutations = 0
            val rules = IterationRules
            fun language(inputs: MutableList<IrExpression>): Language {
                val delegate = LanguageLowering(DiagnosticSink(args[0]), emptyList())
                return object : Language by delegate {
                    override fun expression(expression: IrExpression, scope: Scope): EtsExpression {
                        inputs.add(expression)
                        return EtsReference(EtsSymbol("input${inputs.size}", "input${inputs.size}",
                            type(expression.type), source(expression)))
                    }
                }
            }
            for (call in calls) {
                val owner = call.symbol.owner
                val name = symbolName(owner)
                if (!(name.startsWith("kotlin.Array.") || name.startsWith("kotlin.IntArray.") ||
                    name in setOf("kotlin.arrayOf", "kotlin.intArrayOf", "kotlin.Int.rangeTo") ||
                    name.startsWith("kotlin.ranges.") || name.endsWith(".iterator") ||
                    name.endsWith(".hasNext") || name.endsWith(".next") || name.endsWith(".nextInt"))) continue
                val inputs = mutableListOf<IrExpression>()
                val lowerer = language(inputs)
                val target = checkNotNull(rules.lower(call, lowerer, Scope())) { "Missing observed adapter: $name / ${call.type.render()}" }
                check(target.type == lowerer.type(call.type))
                accepted++
                fun reject(label: String, change: () -> Unit, restore: () -> Unit) {
                    try {
                        change()
                        val ignored = mutableListOf<IrExpression>()
                        check(rules.lower(call, language(ignored), Scope()) == null) { "Accepted $name malformed $label" }
                        check(ignored.isEmpty()) { "Rejected $name lowered children" }
                        mutations++
                    } finally { restore() }
                }
                val original = call.type
                val wrong = if (original.isBoolean()) intType else booleanType
                val declaredResult = owner.returnType
                reject("result", { call.type = wrong }, { call.type = original })
                reject("declared result", { owner.returnType = wrong }, { owner.returnType = declaredResult })
                val qualifier = call.superQualifierSymbol
                reject("super dispatch", { call.superQualifierSymbol = intType.classOrNull },
                    { call.superQualifierSymbol = qualifier })
                owner.valueParameters.forEach { parameter ->
                    val declaredType = parameter.type
                    val altered = if (declaredType.isBoolean()) intType else booleanType
                    reject("declared parameter", { parameter.type = altered }, { parameter.type = declaredType })
                }
                val receiver = call.dispatchReceiver ?: call.extensionReceiver
                if (receiver != null) {
                    val parameter = owner.dispatchReceiverParameter ?: owner.extensionReceiverParameter!!
                    val declaredType = parameter.type
                    reject("declared receiver", { parameter.type = booleanType }, { parameter.type = declaredType })
                    if (call.dispatchReceiver != null) {
                        reject("extension dispatch", { call.insertExtensionReceiver(receiver) }, { call.removeExtensionReceiver() })
                    } else {
                        reject("member dispatch", { call.insertDispatchReceiver(receiver) }, { call.removeDispatchReceiver() })
                    }
                }
            }
            check(accepted >= 35 && mutations >= 160) { "Expected full fixture: $accepted / $mutations" }
            println("PASS actual resolved iteration calls=$accepted; malformed signatures=$mutations; no lowered children on rejection")
        }
    }
}
