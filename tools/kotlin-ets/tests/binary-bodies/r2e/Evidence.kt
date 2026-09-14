@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.r2e

import dev.ets.*
import java.io.File
import java.security.MessageDigest
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrClassSymbol
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.load.kotlin.KotlinJvmBinarySourceElement

fun main(args: Array<String>) {
    val mode = args.getOrNull(3)
    if (mode?.startsWith("reject:") == true) {
        val failure = runCatching {
            withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) {
                error("Unsupported member reached emission")
            }
        }.exceptionOrNull() as? Unsupported ?: error("Expected checked binary member rejection")
        check(failure.diagnostic.message.contains(mode.removePrefix("reject:"))) { failure.diagnostic.toString() }
        check(failure.diagnostic.source.file == args[1])
        check(failure.diagnostic.source.start >= 0 && failure.diagnostic.source.end > failure.diagnostic.source.start)
        File(args[2], "rejection.txt").writeText(failure.diagnostic.toString())
        println("PASS ${failure.diagnostic}")
        return
    }
    withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) { session ->
        if (mode == "signature-only") {
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
            check(count == 13) { "Expected thirteen unavailable member calls, got $count" }
            println("PASS signature-only member bodies remain unavailable")
            return@withKotlinFrontend
        }
        val blocks = mutableListOf<IrInlinedFunctionBlock>()
        session.module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrInlinedFunctionBlock && element.inlinedFunctionFileEntry.name.contains("#SourceFile=")) blocks.add(element)
                if (element is IrCall) check(!element.symbol.owner.isInline) { "Residual member inline call: ${element.dump()}" }
                element.acceptChildrenVoid(this)
            }
        })
        check(blocks.size == 26) { "Expected thirteen direct and thirteen transitive expansions, got ${blocks.size}" }
        val scenario = session.module.files.single().declarations.filterIsInstance<IrSimpleFunction>().single { it.name.asString() == "scenario" }
        val receivers = scenario.valueParameters.take(2).map { it.type.classOrNull!! }.toSet()
        check(receivers.size == 2)
        val memberOwners = mutableSetOf<IrClassSymbol>()
        val report = blocks.map { block ->
            val function = block.inlinedFunctionSymbol!!.owner
            val owner = function.parent as IrClass
            memberOwners.add(owner.symbol)
            check(owner.symbol in receivers) { "Member owner is not original source signature classifier" }
            check(function.dispatchReceiverParameter!!.type.classOrNull === owner.symbol)
            check(owner.thisReceiver!!.type.classOrNull === owner.symbol)
            check(owner.declarations.filterIsInstance<IrSimpleFunction>().single { it.symbol === function.symbol } === function)
            check(owner.fileOrNull !in session.module.files) { "Binary owner must not become a source class" }
            check(sourceFile(owner) == null && sourceFile(function) == null) {
                "Binary provenance must not satisfy source-owned declaration checks"
            }
            val loaded = session.bodies.resolve(function.symbol) as FunctionBody.Available
            check(loaded.origin is FunctionBody.Origin.SerializedJvmIr)
            if (function.name.asString() in setOf("choose", "relay", "extend", "selectFrom")) {
                val parameter = function.typeParameters.single()
                check(parameter.name.asString() == "T")
                check(parameter.parent === function)
                check(function.returnType.classifierOrNull === parameter.symbol)
                check(function.valueParameters.first().type.classifierOrNull === parameter.symbol)
                check(parameter.superTypes.single().isNullableAny())
                if (function.name.asString() == "selectFrom") {
                    check(function.extensionReceiverParameter!!.type.classifierOrNull === parameter.symbol)
                    check(function.extensionReceiverParameter!!.parent === function)
                    check(function.valueParameters.first().defaultValue != null)
                }
            }
            if (function.name.asString() == "bounded") {
                val (result, value) = function.typeParameters
                check(result.parent === function && value.parent === function)
                check(result.index == 0 && value.index == 1)
                check(result.name.asString() == "R" && value.name.asString() == "T")
                check(result.superTypes.single().isNullableAny())
                check(value.superTypes.single().classifierOrNull === result.symbol)
                check(function.returnType.classifierOrNull === result.symbol)
                check(function.valueParameters.first().type.classifierOrNull === value.symbol)
            }
            if (function.name.asString() == "nonNull") {
                val parameter = function.typeParameters.single()
                check(parameter.parent === function && parameter.index == 0)
                check(parameter.superTypes.single().isAny())
                check(function.returnType.classifierOrNull === parameter.symbol)
                check(function.valueParameters.first().type.classifierOrNull === parameter.symbol)
            }
            check(loaded.declaration === function && loaded.body === function.body)
            check(loaded.source.file == block.inlinedFunctionFileEntry.name)
            check(loaded.source.start >= 0 && loaded.source.end > loaded.source.start)
            check(!block.inlinedFunctionFileEntry.supportsDebugInfo)
            check(block.inlinedFunctionFileEntry.getLineNumber(loaded.source.start) == -1)
            val bytes = (owner.source as KotlinJvmBinarySourceElement).binaryClass.classHeader.serializedIr!!
            check(bytes.isNotEmpty())
            val digest = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
            "${owner.name}.${function.name}: parameters=${function.valueParameters.map { it.name }}; bytes=${bytes.size}; serializedSha256=$digest; ${loaded.source}"
        }
        check(memberOwners == receivers)
        File(args[2], "production.ir").writeText(session.module.dump())
        File(args[2], "bodies.txt").writeText(report.joinToString("\n"))
        println("PASS twenty-six official member blocks, generic bounds/receivers/defaults, original classifiers and binary provenance")
    }
}
