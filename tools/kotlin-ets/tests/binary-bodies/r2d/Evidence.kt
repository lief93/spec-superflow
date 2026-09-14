@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.r2d

import dev.ets.*
import java.io.File
import java.security.MessageDigest
import org.jetbrains.kotlin.backend.common.serialization.signature.PublicIdSignatureComputer
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.backend.jvm.serialization.JvmIrMangler
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.load.kotlin.JvmPackagePartSource

fun main(args: Array<String>) {
    val mode = args.getOrNull(3)
    if (mode != null && mode != "signature-only") {
        val failure = runCatching {
            withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) {
                error("Missing selected overload must not reach emission")
            }
        }.exceptionOrNull() as? Unsupported ?: error("Expected source-linked selected-overload rejection")
        check(failure.diagnostic.message.contains(mode)) { failure.diagnostic.message }
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
        if (mode == "signature-only") {
            check(blocks.isEmpty() && remaining.size == 1)
            val call = remaining.single()
            check(call.symbol.owner.valueParameters.first().type.classOrNull!!.owner.fqNameWhenAvailable!!.asString() == "kotlin.Double")
            check(call.symbol.owner.body == null && session.bodies.resolve(call.symbol) is FunctionBody.Unavailable)
            println("PASS selected Double signature remains unavailable despite serialized Int sibling")
            return@withKotlinFrontend
        }
        check(remaining.isEmpty())
        val symbols = blocks.map { it.inlinedFunctionSymbol!! }.toSet()
        check(symbols.size == 4 && blocks.size == 8)
        val signatures = PublicIdSignatureComputer(JvmIrMangler)
        check(symbols.map { signatures.computeSignature(it.owner) }.toSet().size == 4)
        val counts = blocks.groupingBy {
            val owner = it.inlinedFunctionSymbol!!.owner
            "${owner.name}:${owner.valueParameters.first().type.classOrNull!!.owner.fqNameWhenAvailable}"
        }.eachCount()
        check(counts == mapOf("select:kotlin.Int" to 2, "select:kotlin.Double" to 2,
            "helper:kotlin.Int" to 2, "helper:kotlin.Double" to 2)) { counts }
        val report = symbols.map { symbol ->
            val function = symbol.owner
            val body = session.bodies.resolve(symbol) as FunctionBody.Available
            check(body.declaration === function && body.body === function.body)
            check(function.valueParameters.map { it.name.asString() } == listOf("value", "bias", "action"))
            val type = function.valueParameters.first().type.classOrNull!!.owner.fqNameWhenAvailable!!.asString()
            val prefix = if (type == "kotlin.Int") "Int" else "Double"
            val suffix = if (function.name.asString() == "select") "Entry" else "Helper"
            if (suffix == "Entry") check(function.valueParameters[1].defaultValue != null)
            check(body.source.file!!.endsWith("#SourceFile=$prefix$suffix.kt"))
            val fileEntry = blocks.first { it.inlinedFunctionSymbol === symbol }.inlinedFunctionFileEntry
            check(body.source.file == fileEntry.name && !fileEntry.supportsDebugInfo)
            check(body.source.start >= 0 && body.source.end > body.source.start && fileEntry.getLineNumber(body.source.start) == -1)
            val binary = (function.containerSource as JvmPackagePartSource).knownJvmBinaryClass!!
            val bytes = binary.classHeader.serializedIr!!
            val digest = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
            "${function.name}: $type; signature=${signatures.computeSignature(function)}; bytes=${bytes.size}; serializedSha256=$digest; ${body.source}"
        }
        File(args[2], "production.ir").writeText(session.module.dump())
        File(args[2], "bodies.txt").writeText(report.joinToString("\n"))
        println("PASS four distinct official overload signatures; eight selected inline blocks with actual binary provenance")
    }
}
