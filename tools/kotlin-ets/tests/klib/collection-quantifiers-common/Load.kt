@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.collectionquantifierscommontest

import dev.ets.*
import dev.ets.dependency.klib.*
import java.io.File
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

private fun IrElement.calls(): List<IrFunctionAccessExpression> {
    val calls = mutableListOf<IrFunctionAccessExpression>()
    acceptChildrenVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            if (element is IrFunctionAccessExpression) calls += element
            element.acceptChildrenVoid(this)
        }
    })
    return calls
}

fun main(args: Array<String>) {
    val output = File(args[0])
    val consumer = File(args[1])
    val stdlib = File(args[2])
    val mode = args.getOrNull(3) ?: "positive"
    KlibLoader.withKlibModules(KlibModuleSelection(consumer, listOf(consumer), listOf(stdlib))) { session ->
        val entries = session.linkedModules().single().files.flatMap { it.declarations }
            .filterIsInstance<IrSimpleFunction>()
        val names = setOf("kotlin.collections.any", "kotlin.collections.all", "kotlin.collections.none")
        val quantifiers = entries.flatMap { it.calls() }.map { it.symbol }.distinct()
            .filter { it.owner.fqNameWhenAvailable?.asString() in names }
        val ordinaryAny = quantifiers.single {
            it.owner.fqNameWhenAvailable?.asString() == "kotlin.collections.any" && it.owner.valueParameters.isEmpty()
        }
        val ordinaryNone = quantifiers.single {
            it.owner.fqNameWhenAvailable?.asString() == "kotlin.collections.none" && it.owner.valueParameters.isEmpty()
        }
        check(!ordinaryAny.owner.isInline && !ordinaryNone.owner.isInline)
        val predicates = quantifiers - setOf(ordinaryAny, ordinaryNone)
        check(predicates.size == 3 && predicates.all { it.owner.isInline }) { predicates.map { symbolName(it.owner) } }
        check(quantifiers.all { it.owner.body != null })
        val residual = quantifiers.flatMap { it.owner.body!!.calls() }.map { it.symbol }
            .filter { it !in quantifiers }.toSet()
        fun symbol(name: String) = residual.single { it.owner.fqNameWhenAvailable?.asString() == name }
        val hasNext = symbol("kotlin.collections.Iterator.hasNext")
        val bindings = KlibCollectionRuntimeBindings(
            iterator = symbol("kotlin.collections.Iterable.iterator"),
            hasNext = hasNext,
            next = symbol("kotlin.collections.Iterator.next"),
            isEmpty = symbol("kotlin.collections.Collection.isEmpty"),
        )
        if (mode == "reject-body") ordinaryAny.owner.body = null
        val collectionRule = KlibCollectionRuntimeRule(bindings)
        val selectedRule = if (mode != "reject-has-next") collectionRule else object : CallRule by collectionRule,
            KlibPrimitiveBoundary by collectionRule {
            override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? =
                if (call.symbol === hasNext) null else collectionRule.lower(call, language, scope)
        }
        val decisions = mutableListOf<KlibDependencyDecision>()
        if (mode != "positive") {
            val failure = try {
                session.lowerToEts(listOf(selectedRule, StandardLibraryRules()), decisions::add)
                error("Missing ${mode.removePrefix("reject-")} unexpectedly lowered")
            } catch (failure: Unsupported) {
                failure
            }
            val rejection = decisions.single { it.kind == KlibDependencyDecision.Kind.REJECTED }
            val expected = if (mode == "reject-body") ordinaryAny else hasNext
            check(failure.diagnostic.code == "UNSUPPORTED_KLIB_DEPENDENCY") { failure.diagnostic }
            check(rejection.signature == expected.signature.toString() && failure.diagnostic.source == rejection.callSite &&
                rejection.callSite?.isSourceLinked() == true) { rejection }
            check(File(checkNotNull(rejection.library)).canonicalFile == stdlib.canonicalFile)
            if (mode == "reject-body") {
                check(rejection.detail.contains("no function body", ignoreCase = true)) { rejection }
                check(rejection.callSite?.file?.endsWith("Consumer.kt") == true) { rejection }
            } else {
                check(rejection.declaration.file?.endsWith("Iterator.kt") == true) { rejection }
                check(rejection.callSite?.file?.endsWith(".kt") == true) { rejection }
            }
            check(output.listFiles().orEmpty().none { it.extension == "ets" })
            File(output, "rejection.tsv").writeText(
                "${failure.diagnostic.code}\t${rejection.signature}\t${rejection.library}\t${rejection.declaration}" +
                    "\t${rejection.callSite}\t${rejection.detail}\n")
            println("PASS source-linked rejection for $mode")
            return@withKlibModules
        }
        val result = session.lowerToEts(listOf(selectedRule, StandardLibraryRules()), decisions::add)
        val reused = decisions.filter { it.kind == KlibDependencyDecision.Kind.REUSABLE_BODY }
            .map { it.signature }.toSet()
        check(quantifiers.all { it.signature.toString() in reused }) { reused }
        val replacements = decisions.filter { it.kind == KlibDependencyDecision.Kind.TARGET_REPLACEMENT &&
            it.detail.contains("KlibCollectionRuntimeRule") }.map { it.signature }.toSet()
        check(replacements == setOf(bindings.iterator, bindings.hasNext, bindings.next, checkNotNull(bindings.isEmpty))
            .map { it.signature.toString() }.toSet()) { replacements }
        check(result.runtimeSymbols == setOf("stdlib:__etsThrowable", "stdlib:__etsIterator",
            "stdlib:__etsArrayIterator")) {
            result.runtimeSymbols
        }
        val emitted = emitEtsModules(result.program, StandardLibraryRuntime)
        check(emitted.keys == setOf("Consumer.ets", "_Collections.ets")) { emitted.keys }
        val bodyCode = emitted.getValue("_Collections.ets")
        check("function any" in bodyCode && "function none" in bodyCode)
        check(emitted.values.none { "__etsListAny" in it })
        emitted.forEach { (name, code) -> File(output, name).writeText(code) }
        File(output, "decisions.tsv").writeText(decisions.joinToString("\n") {
            "${it.kind}\t${it.signature}\t${it.library}\t${it.declaration}\t${it.callSite}\t${it.detail}"
        })
        File(output, "runtime-symbols.txt").writeText(result.runtimeSymbols.sorted().joinToString("\n"))
        println("PASS ordinary and predicate quantifier bodies")
    }
}

private fun SourceSpan.isSourceLinked(): Boolean = file != null && start >= 0 && end >= start
