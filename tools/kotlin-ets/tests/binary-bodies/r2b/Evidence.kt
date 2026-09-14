@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.r2b

import dev.ets.*
import java.io.File
import java.security.MessageDigest
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrTypeParameterSymbol
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.load.kotlin.JvmPackagePartSource

fun main(args: Array<String>) {
    val mode = args.getOrNull(3)
    if (mode != null && mode != "signature-only") {
        val failure = runCatching {
            withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) {
                error("Unsupported graph reached emission")
            }
        }.exceptionOrNull() as? Unsupported ?: error("Expected source-linked dependency rejection")
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
        var extensionTemporaries = 0
        session.module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrInlinedFunctionBlock && element.inlinedFunctionFileEntry.name.contains("#SourceFile=")) blocks.add(element)
                if (element is IrCall && element.symbol.owner.isInline) calls.add(element)
                if (element is IrVariable && element.origin == IrDeclarationOrigin.IR_TEMPORARY_VARIABLE_FOR_INLINED_EXTENSION_RECEIVER) extensionTemporaries++
                fun checkType(type: IrType) {
                    val simple = type as? IrSimpleType ?: return
                    check(simple.classifier.isBound && simple.classifier !is IrTypeParameterSymbol)
                    simple.arguments.filterIsInstance<IrTypeProjection>().forEach { checkType(it.type) }
                }
                if (element is IrExpression) checkType(element.type)
                if (element is IrValueDeclaration) checkType(element.type)
                element.acceptChildrenVoid(this)
            }
        })
        if (mode == "signature-only") {
            check(blocks.isEmpty() && calls.size == 5)
            calls.forEach { check(it.symbol.owner.body == null && session.bodies.resolve(it.symbol) is FunctionBody.Unavailable) }
            println("PASS actual extension signatures remain body-unavailable")
            return@withKotlinFrontend
        }
        check(calls.isEmpty())
        check(blocks.size == 8 && extensionTemporaries > 0)
        check(blocks.map { it.inlinedFunctionSymbol!!.owner.name.asString() }.toSet() == setOf("extDirect", "extEntry", "extHelper"))
        val report = blocks.map { block ->
            val symbol = block.inlinedFunctionSymbol!!
            val function = symbol.owner
            val body = session.bodies.resolve(symbol) as FunctionBody.Available
            check(body.declaration === function && body.body === function.body)
            check(function.dispatchReceiverParameter == null && function.extensionReceiverParameter != null)
            check(function.typeParameters.size == 2 && function.typeParameters.none { it.isReified })
            check(function.valueParameters.map { it.name.asString() } == listOf("stamp", "action"))
            val parameters = function.typeParameters.map { it.symbol }.toSet()
            fun checkLinked(type: IrType) {
                val simple = type as? IrSimpleType ?: return
                check(simple.classifier.isBound)
                if (simple.classifier is IrTypeParameterSymbol) check(simple.classifier in parameters)
                simple.arguments.filterIsInstance<IrTypeProjection>().forEach { checkLinked(it.type) }
            }
            checkLinked(function.extensionReceiverParameter!!.type)
            check((function.extensionReceiverParameter!!.type as IrSimpleType).classifier === function.typeParameters.first().symbol)
            function.valueParameters.forEach { checkLinked(it.type) }
            checkLinked(function.returnType)
            val receiver = function.extensionReceiverParameter!!.symbol
            var receiverReads = 0
            body.body.acceptVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) {
                    if (element is IrGetValue && element.symbol === receiver) receiverReads++
                    element.acceptChildrenVoid(this)
                }
            })
            check(receiverReads == if (function.name.asString() == "extEntry") 1 else 2)
            check(body.source.file == block.inlinedFunctionFileEntry.name)
            check(body.source.start >= 0 && body.source.end > body.source.start)
            check(!block.inlinedFunctionFileEntry.supportsDebugInfo && block.inlinedFunctionFileEntry.getLineNumber(body.source.start) == -1)
            val binary = (function.containerSource as JvmPackagePartSource).knownJvmBinaryClass!!
            val bytes = binary.classHeader.serializedIr!!
            val digest = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
            "${function.name}: receiverReads=$receiverReads; typeParameters=${function.typeParameters.map { it.name }}; bytes=${bytes.size}; serializedSha256=$digest; ${body.source}"
        }
        File(args[2], "production.ir").writeText(session.module.dump())
        File(args[2], "bodies.txt").writeText(report.joinToString("\n"))
        println("PASS eight official extension inline blocks; actual receiver symbols and binary provenance; $extensionTemporaries official receiver temporaries")
    }
}
