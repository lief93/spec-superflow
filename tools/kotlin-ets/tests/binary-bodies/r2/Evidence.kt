@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.r2

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
    if (args.getOrNull(3)?.startsWith("reject:") == true) {
        val failure = runCatching {
            withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) {
                error("Unsupported binary graph must not reach emission")
            }
        }.exceptionOrNull() as? Unsupported ?: error("Expected a source-linked dependency rejection")
        check(failure.diagnostic.message.contains(args[3].removePrefix("reject:"))) { failure.diagnostic.message }
        check(failure.diagnostic.source.file == args[1])
        check(failure.diagnostic.source.start >= 0 && failure.diagnostic.source.end > failure.diagnostic.source.start)
        File(args[2], "rejection.txt").writeText(failure.diagnostic.toString())
        println("PASS ${failure.diagnostic}")
        return
    }
    if (args.getOrNull(3) == "member-ok") {
        withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) { session ->
            val blocks = mutableListOf<IrInlinedFunctionBlock>()
            session.module.acceptVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) {
                    if (element is IrInlinedFunctionBlock) blocks.add(element)
                    if (element is IrCall) check(!element.symbol.owner.isInline) { "Residual inline call: ${element.dump()}" }
                    element.acceptChildrenVoid(this)
                }
            })
            check(blocks.any { it.inlinedFunctionSymbol?.owner?.name?.asString() == "unsupported" }) {
                "Expected serialized member inline body: ${blocks.map { it.inlinedFunctionSymbol?.owner?.name }}"
            }
            println("PASS serialized member inline body loaded for unsupported")
        }
        return
    }
    withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) { session ->
        if (args.getOrNull(3) == "signature-only") {
            var count = 0
            session.module.acceptVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) {
                    if (element is IrCall && element.symbol.owner.isInline) {
                        check(session.bodies.resolve(element.symbol) is FunctionBody.Unavailable)
                        check(element.symbol.owner.body == null)
                        count++
                    }
                    element.acceptChildrenVoid(this)
                }
            })
            check(count == 3)
            println("PASS three signature-only calls remain unavailable; no manufactured body")
            return@withKotlinFrontend
        }
        val blocks = mutableListOf<IrInlinedFunctionBlock>()
        session.module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrInlinedFunctionBlock && element.inlinedFunctionFileEntry.name.contains("#SourceFile=")) blocks.add(element)
                if (element is IrCall) check(!element.symbol.owner.isInline) { "Residual inline call: ${element.dump()}" }
                fun checkType(type: IrType) {
                    val simple = type as? IrSimpleType ?: return
                    check(simple.classifier.isBound)
                    check(simple.classifier !is IrTypeParameterSymbol) { "Unsubstituted binary type: ${type.render()}" }
                    simple.arguments.filterIsInstance<IrTypeProjection>().forEach { checkType(it.type) }
                }
                if (element is IrExpression) checkType(element.type)
                if (element is IrValueDeclaration) checkType(element.type)
                element.acceptChildrenVoid(this)
            }
        })
        check(blocks.size == 5) { "Expected direct + two entry/helper expansions: ${blocks.size}" }
        check(blocks.map { it.inlinedFunctionSymbol!!.owner.name.asString() }.toSet() == setOf("direct", "entry", "helper"))
        val report = blocks.map { block ->
            val symbol = block.inlinedFunctionSymbol!!
            val owner = symbol.owner
            val body = session.bodies.resolve(symbol) as FunctionBody.Available
            check(body.declaration === owner && body.body === owner.body)
            check(body.source.file == block.inlinedFunctionFileEntry.name)
            check(body.source.start >= 0 && body.source.end > body.source.start)
            check(!block.inlinedFunctionFileEntry.supportsDebugInfo)
            check(block.inlinedFunctionFileEntry.getLineNumber(body.source.start) == -1)
            check(owner.typeParameters.size == 2 && owner.typeParameters.none { it.isReified })
            check(owner.valueParameters.map { it.name.asString() } == listOf("value", "action"))
            val binary = (owner.containerSource as JvmPackagePartSource).knownJvmBinaryClass!!
            val bytes = binary.classHeader.serializedIr!!
            check(bytes.isNotEmpty())
            val digest = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
            val parameters = owner.typeParameters.map { it.symbol }.toSet()
            fun checkLinked(type: IrType) {
                val simple = type as? IrSimpleType ?: return
                check(simple.classifier.isBound)
                if (simple.classifier is IrTypeParameterSymbol) check(simple.classifier in parameters)
                simple.arguments.filterIsInstance<IrTypeProjection>().forEach { checkLinked(it.type) }
            }
            owner.valueParameters.forEach { checkLinked(it.type) }
            checkLinked(owner.returnType)
            "${owner.name}: ${owner.typeParameters.map { it.name }}; bytes=${bytes.size}; serializedSha256=$digest; ${body.source}"
        }
        File(args[2], "production.ir").writeText(session.module.dump())
        File(args[2], "bodies.txt").writeText(report.joinToString("\n"))
        println("PASS five official generic inline blocks; linked declaration/type symbols; binary SourceFile with unknown debug lines")
    }
}
