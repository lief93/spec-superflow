@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.collectioncommontest

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
    val rejectAppend = args.getOrNull(3) == "reject-append"
    KlibLoader.withKlibModules(KlibModuleSelection(consumer, listOf(consumer), listOf(stdlib))) { session ->
        val module = session.linkedModules().single()
        val entries = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
        val rootCalls = entries.flatMap { it.calls() }
        val filter = rootCalls.single { it.symbol.owner.fqNameWhenAvailable?.asString() == "kotlin.collections.filter" }.symbol
        val filterNot = rootCalls.single { it.symbol.owner.fqNameWhenAvailable?.asString() == "kotlin.collections.filterNot" }.symbol
        fun inlineClosure(root: IrFunctionSymbol): Set<IrFunctionSymbol> {
            val result = linkedSetOf<IrFunctionSymbol>()
            val pending = ArrayDeque<IrFunctionSymbol>()
            pending += root
            while (pending.isNotEmpty()) {
                val symbol = pending.removeFirst()
                if (!result.add(symbol)) continue
                check(symbol.owner.isInline && symbol.owner.body != null)
                symbol.owner.body!!.calls().map { it.symbol }.filter { it.owner.isInline && it.owner.body != null }
                    .forEach(pending::addLast)
            }
            return result
        }
        val approved = inlineClosure(filter) + inlineClosure(filterNot)
        val residual = approved.flatMap { it.owner.body!!.calls() }.map { it.symbol }.filter { it !in approved }.toSet()
        fun symbol(name: String) = residual.single { it.owner.fqNameWhenAvailable?.asString() == name }
        val constructor = residual.single { it.owner is IrConstructor &&
            (it.owner.parent as? IrClass)?.fqNameWhenAvailable?.asString() == "kotlin.collections.ArrayList" }
        val bindings = KlibCollectionRuntimeBindings(
            emptyListConstructor = constructor as IrConstructorSymbol,
            iterator = symbol("kotlin.collections.Iterable.iterator"),
            hasNext = symbol("kotlin.collections.Iterator.hasNext"),
            next = symbol("kotlin.collections.Iterator.next"),
            append = symbol("kotlin.collections.MutableCollection.add"),
        )
        val decisions = mutableListOf<KlibDependencyDecision>()
        val collectionRule = KlibCollectionRuntimeRule(bindings)
        val selectedRule = if (!rejectAppend) collectionRule else object : CallRule by collectionRule,
            KlibPrimitiveBoundary by collectionRule {
            override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? =
                if (call.symbol === bindings.append) null else collectionRule.lower(call, language, scope)
        }
        if (rejectAppend) {
            val failure = try {
                session.lowerToEts(listOf(selectedRule, StandardLibraryRules()), decisions::add)
                error("Missing append binding unexpectedly lowered")
            } catch (failure: Unsupported) {
                failure
            }
            val rejection = decisions.single { it.kind == KlibDependencyDecision.Kind.REJECTED }
            check(failure.diagnostic.code == "UNSUPPORTED_KLIB_DEPENDENCY") { failure.diagnostic }
            check(failure.diagnostic.source == rejection.callSite &&
                rejection.signature == checkNotNull(bindings.append).signature.toString()) {
                rejection
            }
            check(File(checkNotNull(rejection.library)).canonicalFile == stdlib.canonicalFile) { rejection }
            check(rejection.declaration.file?.endsWith("js/builtins/Collections.kt") == true &&
                rejection.callSite?.endsWithSource("Consumer.kt") == true) { rejection }
            check(output.listFiles().orEmpty().none { it.extension == "ets" })
            File(output, "rejection.tsv").writeText(
                "${failure.diagnostic.code}\t${rejection.signature}\t${rejection.library}\t${rejection.declaration}" +
                    "\t${rejection.callSite}\t${rejection.detail}\n")
            println("PASS source-linked rejection when exact append primitive is absent")
            return@withKlibModules
        }
        val result = session.lowerToEts(listOf(selectedRule, StandardLibraryRules()), decisions::add)
        check(decisions.any { it.kind == KlibDependencyDecision.Kind.REUSABLE_BODY && it.signature == filter.signature.toString() })
        check(decisions.any { it.kind == KlibDependencyDecision.Kind.REUSABLE_BODY && it.signature == filterNot.signature.toString() })
        val collectionReplacements = decisions.filter { it.kind == KlibDependencyDecision.Kind.TARGET_REPLACEMENT &&
            it.detail.contains("KlibCollectionRuntimeRule") }
        check(collectionReplacements.map { it.signature }.toSet() ==
            setOf(constructor, bindings.iterator, bindings.hasNext, bindings.next, checkNotNull(bindings.append))
                .map { it.signature.toString() }.toSet()) { collectionReplacements }
        check(result.runtimeSymbols == setOf("stdlib:__etsIterator", "stdlib:__etsArrayIterator", "stdlib:__etsIntRem",
            "stdlib:__etsListAdd")) {
            result.runtimeSymbols
        }
        val emitted = emitEtsModules(result.program, StandardLibraryRuntime)
        check(emitted.keys == setOf("Consumer.ets"))
        val code = emitted.getValue("Consumer.ets")
        check("__etsListFilter" !in code && "function filterEven" in code && "function filterOdd" in code)
        File(output, "Consumer.ets").writeText(code)
        File(output, "decisions.tsv").writeText(decisions.joinToString("\n") {
            "${it.kind}\t${it.signature}\t${it.library}\t${it.declaration}\t${it.callSite}\t${it.detail}"
        })
        File(output, "runtime-symbols.txt").writeText(result.runtimeSymbols.sorted().joinToString("\n"))
        println("PASS official filter/filterNot bodies with symbol-bound collection primitives")
    }
}

private fun SourceSpan.endsWithSource(name: String): Boolean = file?.endsWith(name) == true && start >= 0 && end >= start
