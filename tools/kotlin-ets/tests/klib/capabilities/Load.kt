@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.capabilitytest

import dev.ets.*
import dev.ets.dependency.klib.*
import java.io.File
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrFunctionSymbol
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    val mode = args[0]
    val output = File(args[1])
    val main = File(args[2])
    val library = File(args[3])
    val stdlib = File(args[4])
    val translated = if (mode == "positive") listOf(main, library) else listOf(main)
    val dependencies = if (mode == "positive") listOf(stdlib) else listOf(library, stdlib)
    var borrowed: FunctionBodies? = null
    var borrowedSymbol: IrFunctionSymbol? = null
    KlibLoader.withKlibModules(KlibModuleSelection(main, translated, dependencies)) { session ->
        val calls = mutableListOf<IrCall>()
        session.linkedModules().forEach { module -> module.acceptChildrenVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrCall) calls += element
                element.acceptChildrenVoid(this)
            }
        }) }
        // Test selects the canonical linked symbol, not a production FQName rule.
        val let = calls.singleOrNull { it.symbol.owner.fqNameWhenAvailable?.asString() == "kotlin.let" }?.symbol
        if (let != null) check(session.bodies().resolve(let) ==
            FunctionBody.Unavailable(FunctionBody.Reason.NON_TRANSLATED_KLIB))
        val bodies = session.bodies(setOfNotNull(let))
        val entry = session.linkedModules().first { it.files.any { file -> file.fileEntry.name.endsWith("${if (mode == "external") "Rejected" else "Consumer"}.kt") } }
            .files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>().single { it.name.asString() == "scenario" }
        borrowed = bodies
        borrowedSymbol = entry.symbol
        val entryBody = bodies.resolve(entry.symbol) as FunctionBody.Available
        check((entryBody.origin as FunctionBody.Origin.SerializedKlibIr).libraryLocation == main.canonicalPath)
        check(!File(entryBody.source.file!!).exists())
        val decisions = mutableListOf<KlibDependencyDecision>()
        try {
            val result = session.lowerToEts(listOf(StandardLibraryRules()), setOfNotNull(let), decisions::add)
            check(mode == "positive") { "Expected rejection for $mode" }
            check(result.decisions == decisions)
            check(result.runtimeSymbols == setOf("stdlib:__etsIntRem")) { result.runtimeSymbols }
            val reusedLet = decisions.single { it.kind == KlibDependencyDecision.Kind.REUSABLE_BODY && it.signature.startsWith("kotlin/let|") }
            check(reusedLet.library == stdlib.canonicalPath)
            check(reusedLet.declaration.file!!.endsWith("Standard.kt")) { reusedLet }
            check(decisions.any { it.kind == KlibDependencyDecision.Kind.REUSABLE_BODY && it.signature.startsWith("dependencies/adjusted|") })
            val replacement = decisions.single { it.kind == KlibDependencyDecision.Kind.TARGET_REPLACEMENT && it.signature.contains("Int.rem|") }
            check(replacement.library == stdlib.canonicalPath)
            check(replacement.callSite != null && replacement.callSite!!.start >= 0)
            check(decisions.none { it.kind == KlibDependencyDecision.Kind.TARGET_REPLACEMENT && it.signature.startsWith("kotlin/let|") })
            session.linkedModules().forEach { module -> module.acceptChildrenVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) {
                    if (element is IrCall) check(element.symbol != let) { "Official let was not inlined" }
                    element.acceptChildrenVoid(this)
                }
            }) }
            val emitted = emitEtsModules(result.program, StandardLibraryRuntime)
            check(emitted.keys == setOf("Library.ets", "Consumer.ets"))
            check(!emitted.getValue("Library.ets").contains("function __ets"))
            emitted.forEach { (name, code) -> File(output, name).writeText(code) }
            File(output, "runtime-symbols.txt").writeText(result.runtimeSymbols.sorted().joinToString("\n"))
        } catch (failure: Unsupported) {
            check(mode != "positive") { failure.diagnostic }
            val diagnostic = failure.diagnostic
            check(diagnostic.code == "UNSUPPORTED_KLIB_DEPENDENCY") { diagnostic }
            check(diagnostic.source.file!!.endsWith(if (mode == "external") "Rejected.kt" else "Consumer.kt")) { diagnostic }
            check(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start)
            check(diagnostic.message.contains(library.canonicalPath)) { diagnostic }
            check(diagnostic.message.contains(if (mode == "external") "external" else "dependency-only")) { diagnostic }
            check(decisions.last().kind == KlibDependencyDecision.Kind.REJECTED)
            check(decisions.last().library == library.canonicalPath)
            File(output, "rejection.txt").writeText(diagnostic.toString())
            check(output.listFiles()!!.none { it.extension == "ets" })
        }
        File(output, "decisions.tsv").writeText(decisions.joinToString("\n") {
            "${it.kind}\t${it.signature}\t${it.library}\t${it.declaration}\t${it.callSite}\t${it.detail}"
        })
    }
    check(runCatching { borrowed!!.resolve(borrowedSymbol!!) }.exceptionOrNull() is IllegalStateException)
    println("PASS $mode: provenance, canonical body symbols, source-linked dependency boundary")
}
