@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    if (args.size > 3) {
        val failure = runCatching {
            withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) {
                error("Invalid dependency must not reach emission callback")
            }
        }.exceptionOrNull() as? Unsupported ?: error("Expected source-linked unsupported dependency")
        check(failure.diagnostic.message.contains(args[3]))
        check(failure.diagnostic.source.file == args[1])
        check(failure.diagnostic.source.start >= 0 && failure.diagnostic.source.end > failure.diagnostic.source.start)
        File(args[2], "rejection-${args[4]}.txt").writeText(failure.diagnostic.toString())
        println("PASS dependency rejection before emission: ${failure.diagnostic.message}")
        return
    }
    var borrowed: FunctionBodies? = null
    withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) { session ->
        val blocks = mutableListOf<IrInlinedFunctionBlock>()
        val calls = mutableListOf<IrCall>()
        val constants = mutableListOf<IrConst>()
        session.module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                when (element) {
                    is IrInlinedFunctionBlock -> blocks.add(element)
                    is IrCall -> calls.add(element)
                    is IrConst -> constants.add(element)
                }
                element.acceptChildrenVoid(this)
            }
        })
        val binaryBlocks = blocks.filter { it.inlinedFunctionFileEntry.name.contains("#SourceFile=") }
        check(binaryBlocks.size == 2)
        val symbol = checkNotNull(binaryBlocks.first().inlinedFunctionSymbol)
        check(binaryBlocks.all { it.inlinedFunctionSymbol === symbol })
        check(calls.none { it.symbol === symbol }) { "Binary calls must really be inlined" }
        val body = session.bodies.resolve(symbol) as FunctionBody.Available
        check(body.declaration === symbol.owner && body.body === symbol.owner.body)
        check(body.declaration.valueParameters.map { it.name.asString() } == listOf("first", "second", "operation"))
        check(body.declaration.valueParameters[1].defaultValue != null)
        check(body.declaration.returnType.classOrNull === constants.first { it.value is Int }.type.classOrNull)
        check(body.source.file == binaryBlocks.first().inlinedFunctionFileEntry.name)
        check(body.source.file!!.endsWith("!/binarylibrary/BinaryLibraryKt.class#SourceFile=BinaryLibrary.kt"))
        check(body.source.start >= 0 && body.source.end > body.source.start)
        check(body.source.start == body.body.startOffset && body.source.end == body.body.endOffset)
        binaryBlocks.forEach {
            check(!it.inlinedFunctionFileEntry.supportsDebugInfo)
            check(it.inlinedFunctionFileEntry.getLineNumber(0) == -1)
            check(it.inlinedFunctionFileEntry.getColumnNumber(0) == -1)
        }
        File(args[2], "production.ir").writeText(session.module.dump())
        File(args[2], "body-provenance.txt").writeText("source=${body.source}\nidentity=true\nbinaryBlocks=${binaryBlocks.size}\nremainingCalls=0\ndebugLine=-1\ndebugColumn=-1\n")
        borrowed = session.bodies
        println("PASS actual serialized body: original symbol/type/defaults, binary SourceFile provenance, two official inlined blocks")
    }
    check(runCatching { borrowed!!.resolve(org.jetbrains.kotlin.ir.symbols.impl.IrSimpleFunctionSymbolImpl()) }.isFailure)
}
