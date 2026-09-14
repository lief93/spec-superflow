@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.ir.inline.FunctionInlining
import org.jetbrains.kotlin.config.KotlinCompilerVersion
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    check(KotlinCompilerVersion.VERSION == "2.1.20")
    println("Official inliner: ${FunctionInlining::class.java.name}; loadedFrom=${FunctionInlining::class.java.protectionDomain.codeSource.location}")
    val sourcePaths = args.drop(2)
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + sourcePaths) { module ->
        val calls = mutableListOf<IrCall>()
        val blocks = mutableListOf<IrInlinedFunctionBlock>()
        val returnable = mutableListOf<IrReturnableBlock>()
        module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                when (element) {
                    is IrCall -> if (element.symbol.owner.isInline && element.symbol.owner.fileOrNull?.fileEntry?.name in sourcePaths) calls.add(element)
                    is IrInlinedFunctionBlock -> blocks.add(element)
                    is IrReturnableBlock -> returnable.add(element)
                }
                element.acceptChildrenVoid(this)
            }
        })
        File(args[1], "production.ir").writeText(module.dump())
        check(calls.isEmpty()) { "Official inlining missing: ${calls.size} resolved source inline calls remain" }
        check(blocks.isNotEmpty()) { "No actual official inlined function blocks" }
        check(returnable.isEmpty()) { "Returnable blocks must be normalized before language lowering" }
        val libraryBlocks = blocks.filter { it.inlinedFunctionFileEntry.name == sourcePaths.last() }
        check(libraryBlocks.isNotEmpty()) { "No provenance from real library source" }
        check(libraryBlocks.all { block ->
            val function = block.inlinedFunctionSymbol?.owner
            function != null && function.body != null && function.fileOrNull?.fileEntry?.name == sourcePaths.last() &&
                block.inlinedFunctionStartOffset == function.startOffset && block.inlinedFunctionEndOffset == function.endOffset
        }) { "Library bodies must be the actual source declarations, with original offsets" }
        println("PASS official inline: calls=${calls.size}, inlinedBlocks=${blocks.size}, libraryBlocks=${libraryBlocks.size}, returnable=${returnable.size}")
        println("Library body source: ${sourcePaths.last()}")
    }
    val binarySource = File(sourcePaths.first()).parentFile.resolve("BinaryOnly.kt").absolutePath
    val libraryJar = File(args[1], "inline-library.jar").absolutePath
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0] + File.pathSeparator + libraryJar, binarySource)) { module ->
        var found = false
        module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrCall && element.symbol.owner.fqNameWhenAvailable?.asString() == "inlinelibrary.libraryTransform") {
                    val function = element.symbol.owner
                    check(function.isInline && function.body == null && function.fileOrNull == null)
                    check(function.containerSource != null)
                    File(args[1], "binary-body.txt").writeText(
                        "symbol=${function.fqNameWhenAvailable}\nbody=${function.body}\ncontainer=${function.containerSource!!::class.java.name}\n")
                    found = true
                }
                element.acceptChildrenVoid(this)
            }
        })
        check(found) { "Real built JAR must resolve its inline signature without inventing an IR body" }
        println("PASS built JAR: inline signature resolves, IR body absent; frontend does not preempt adapter callbacks")
    }
}
