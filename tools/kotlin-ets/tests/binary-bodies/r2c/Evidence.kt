@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.r2c

import dev.ets.*
import java.io.File
import java.security.MessageDigest
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrFunctionSymbol
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.load.kotlin.JvmPackagePartSource

fun main(args: Array<String>) {
    val mode = args.getOrNull(3)
    if (mode != null && mode != "signature-only") {
        val failure = runCatching {
            withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) {
                error("Incomplete default dependency graph reached emission")
            }
        }.exceptionOrNull() as? Unsupported ?: error("Expected a source-linked dependency rejection")
        check(failure.diagnostic.message.contains(mode)) { failure.diagnostic.message }
        check(failure.diagnostic.source.file == args[1])
        check(failure.diagnostic.source.start >= 0 && failure.diagnostic.source.end > failure.diagnostic.source.start)
        File(args[2], "rejection.txt").writeText(failure.diagnostic.toString())
        println("PASS ${failure.diagnostic}")
        return
    }
    withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) { session ->
        val blocks = mutableListOf<IrInlinedFunctionBlock>()
        val calls = mutableListOf<IrCall>()
        session.module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrInlinedFunctionBlock && element.inlinedFunctionFileEntry.name.contains("#SourceFile=")) blocks.add(element)
                if (element is IrCall && element.symbol.owner.isInline) calls.add(element)
                element.acceptChildrenVoid(this)
            }
        })
        if (mode == "signature-only") {
            check(blocks.isEmpty() && calls.size == 5)
            calls.forEach { check(it.symbol.owner.body == null && session.bodies.resolve(it.symbol) is FunctionBody.Unavailable) }
            println("PASS signature-only defaults do not manufacture a usable body")
            return@withKotlinFrontend
        }
        check(calls.isEmpty())
        val names = blocks.groupingBy { it.inlinedFunctionSymbol!!.owner.name.asString() }.eachCount()
        check(names == mapOf("defaultSelect" to 5, "defaultHelper" to 3)) { names }
        val symbols = blocks.map { it.inlinedFunctionSymbol!! }.toSet()
        val entry = symbols.single { it.owner.name.asString() == "defaultSelect" }
        val helper = symbols.single { it.owner.name.asString() == "defaultHelper" }
        val entryBody = session.bodies.resolve(entry) as FunctionBody.Available
        val owner = entryBody.declaration
        check(owner.valueParameters.map { it.name.asString() } == listOf("mark", "selected"))
        check(owner.valueParameters[0].isNoinline)
        val default = owner.valueParameters[1].defaultValue ?: error("Missing actual default expression body")
        check(default.startOffset >= 0 && default.endOffset > default.startOffset)
        val referencedHelpers = mutableSetOf<IrFunctionSymbol>()
        default.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrCall && element.symbol === helper) referencedHelpers.add(element.symbol)
                if (element is IrInlinedFunctionBlock && element.inlinedFunctionSymbol === helper) referencedHelpers.add(helper)
                element.acceptChildrenVoid(this)
            }
        })
        check(referencedHelpers == setOf(helper))
        val report = symbols.map { symbol ->
            val function = symbol.owner
            val body = session.bodies.resolve(symbol) as FunctionBody.Available
            check(body.declaration === function && body.body === function.body)
            check(function.dispatchReceiverParameter == null && function.typeParameters.size == 1)
            check(!function.typeParameters.single().isReified)
            check((function.extensionReceiverParameter!!.type as IrSimpleType).classifier === function.typeParameters.single().symbol)
            val fileEntry = blocks.first { it.inlinedFunctionSymbol === symbol }.inlinedFunctionFileEntry
            check(body.source.file == fileEntry.name && !fileEntry.supportsDebugInfo)
            check(body.source.start >= 0 && body.source.end > body.source.start)
            check(fileEntry.getLineNumber(body.source.start) == -1)
            val binary = (function.containerSource as JvmPackagePartSource).knownJvmBinaryClass!!
            val bytes = binary.classHeader.serializedIr!!
            val digest = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
            "${function.name}: bytes=${bytes.size}; serializedSha256=$digest; ${body.source}"
        }
        File(args[2], "production.ir").writeText(session.module.dump())
        File(args[2], "default.ir").writeText(default.dump())
        File(args[2], "bodies.txt").writeText(report.joinToString("\n") + "\ndefaultOffsets=${default.startOffset}..${default.endOffset}\n")
        println("PASS real default expression/body provenance; five entry expansions, three needed default helper expansions")
    }
}
