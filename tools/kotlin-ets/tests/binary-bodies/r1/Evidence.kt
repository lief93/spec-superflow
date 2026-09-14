@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.r1

import dev.ets.*
import java.io.File
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    if (args.getOrNull(3)?.startsWith("reject:") == true) {
        val failure = runCatching {
            withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) {
                error("Incomplete graph must not reach emission")
            }
        }.exceptionOrNull() as? Unsupported ?: error("Expected a source-linked dependency rejection")
        check(failure.diagnostic.message.contains(args[3].removePrefix("reject:"))) { failure.diagnostic.message }
        check(failure.diagnostic.source.file == args[1])
        check(failure.diagnostic.source.start >= 0 && failure.diagnostic.source.end > failure.diagnostic.source.start)
        File(args[2], "rejection.txt").writeText(failure.diagnostic.toString())
        println("PASS ${failure.diagnostic}")
        return
    }
    withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) { session ->
        val blocks = mutableListOf<IrInlinedFunctionBlock>()
        val remaining = mutableListOf<IrCall>()
        session.module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrInlinedFunctionBlock && element.inlinedFunctionFileEntry.name.contains("#SourceFile=")) blocks.add(element)
                if (element is IrCall && element.symbol.owner.isInline) remaining.add(element)
                element.acceptChildrenVoid(this)
            }
        })
        check(remaining.isEmpty())
        val names = blocks.map { it.inlinedFunctionSymbol!!.owner.name.asString() }.toSet()
        check(names == setOf("entry", "helper")) { "Expected actual transitive inline blocks, got $names" }
        check(blocks.map { it.inlinedFunctionFileEntry.name }.toSet().size == (args.getOrNull(3)?.toInt() ?: 1))
        blocks.forEach { block ->
            val symbol = block.inlinedFunctionSymbol!!
            val body = session.bodies.resolve(symbol) as FunctionBody.Available
            check(body.declaration === symbol.owner && body.body === symbol.owner.body)
            check(body.source.file == block.inlinedFunctionFileEntry.name)
            check(body.source.start >= 0 && body.source.end > body.source.start)
            check(!block.inlinedFunctionFileEntry.supportsDebugInfo)
        }
        File(args[2], "production.ir").writeText(session.module.dump())
        File(args[2], "bodies.txt").writeText(blocks.joinToString("\n") {
            "${it.inlinedFunctionSymbol!!.owner.name}: ${it.inlinedFunctionFileEntry.name}"
        })
        println("PASS production official transitive inline: $names; original symbols and binary provenance")
    }
}
