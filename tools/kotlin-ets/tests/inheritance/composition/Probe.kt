@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.composition

import dev.ets.*
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.symbols.IrTypeParameterSymbol
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.types.classifierOrNull
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(1)) { frontend ->
        val calls = mutableMapOf<String, MutableList<IrCall>>()
        frontend.module.acceptChildrenVoid(object : IrElementVisitorVoid {
            private var owner = ""
            override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
            override fun visitSimpleFunction(declaration: IrSimpleFunction) {
                val previous = owner
                owner = declaration.name.asString()
                try { declaration.acceptChildrenVoid(this) } finally { owner = previous }
            }
            override fun visitCall(expression: IrCall) {
                if (expression.symbol.owner.name.asString() == "read") calls.getOrPut(owner) { mutableListOf() }.add(expression)
                expression.acceptChildrenVoid(this)
            }
        })
        fun call(owner: String) = calls.getValue(owner).single()
        fun capture(owner: String) = frontend.types.callCaptures(call(owner)).getValue(0)
        check(capture("genericCopy").readType.classifierOrNull is IrTypeParameterSymbol)
        for (owner in listOf("inlineCapture", "substitutedCapture", "nestedCapture")) {
            val bound = capture(owner)
            check(bound.readType == call(owner).getTypeArgument(0))
            check(bound.readType.classOrNull?.owner?.name?.asString() == "Value")
            check(bound.writeType == null)
        }
        check(capture("copiedInput").writeType?.classifierOrNull is IrTypeParameterSymbol)
        check(capture("inputCapture").writeType?.classOrNull?.owner?.name?.asString() == "Specific")
        check(call("substitutedCapture").attributeOwnerId === call("genericCopy").attributeOwnerId)
        check(call("substitutedCapture").symbol === call("genericCopy").symbol)
        val altered = call("substitutedCapture")
        val original = altered.symbol
        altered.symbol = frontend.module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
            .single { it.name.asString() == "boundedRead" }.symbol
        try {
            check(runCatching { frontend.types.callCaptures(altered) }.exceptionOrNull() is Unsupported)
        } finally { altered.symbol = original }
        println("PASS original FIR capture identity, copied read erasure, nested substitution, input lower bound and changed-symbol refusal")
    }
}
