@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.collectionmapcommontest

import dev.ets.*
import dev.ets.dependency.klib.*
import java.io.File
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.*
import org.jetbrains.kotlin.ir.types.isInt
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
    val rejectCapacity = args.getOrNull(3) == "reject-capacity"
    KlibLoader.withKlibModules(KlibModuleSelection(consumer, listOf(consumer), listOf(stdlib))) { session ->
        val module = session.linkedModules().single()
        val entries = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
        val rootCalls = entries.flatMap { it.calls() }
        val map = rootCalls.single { it.symbol.owner.fqNameWhenAvailable?.asString() == "kotlin.collections.map" }.symbol
        val mapNotNull = rootCalls.single {
            it.symbol.owner.fqNameWhenAvailable?.asString() == "kotlin.collections.mapNotNull"
        }.symbol
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
        val approved = inlineClosure(map) + inlineClosure(mapNotNull)
        check(approved.map { symbolName(it.owner) }.toSet() == setOf("kotlin.collections.map",
            "kotlin.collections.mapTo", "kotlin.collections.mapNotNull", "kotlin.collections.mapNotNullTo",
            "kotlin.collections.forEach", "kotlin.let")) { approved.map { symbolName(it.owner) } }
        val residual = approved.flatMap { it.owner.body!!.calls() }.map { it.symbol }.filter { it !in approved }.toSet()
        fun symbol(name: String) = residual.single { it.owner.fqNameWhenAvailable?.asString() == name }
        val constructors = residual.filter { it.owner is IrConstructor &&
            (it.owner.parent as? IrClass)?.fqNameWhenAvailable?.asString() == "kotlin.collections.ArrayList" }
            .map { it as IrConstructorSymbol }
        val emptyConstructor = constructors.single { it.owner.valueParameters.isEmpty() }
        val capacityConstructor = constructors.single { it.owner.valueParameters.singleOrNull()?.type?.isInt() == true }
        val bindings = KlibCollectionRuntimeBindings(
            emptyListConstructor = emptyConstructor,
            iterator = symbol("kotlin.collections.Iterable.iterator"),
            hasNext = symbol("kotlin.collections.Iterator.hasNext"),
            next = symbol("kotlin.collections.Iterator.next"),
            append = symbol("kotlin.collections.MutableCollection.add"),
            capacityListConstructor = capacityConstructor,
            collectionSizeOrDefault = symbol("kotlin.collections.collectionSizeOrDefault"),
        )
        val decisions = mutableListOf<KlibDependencyDecision>()
        val collectionRule = KlibCollectionRuntimeRule(bindings)
        val rule = if (!rejectCapacity) collectionRule else object : CallRule by collectionRule,
            KlibPrimitiveBoundary by collectionRule {
            override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? =
                if (call.symbol === capacityConstructor) null else collectionRule.lowerConstructor(call, language, scope)
        }
        if (rejectCapacity) {
            val failure = try {
                session.lowerToEts(listOf(rule, StandardLibraryRules()), decisions::add)
                error("Missing capacity constructor unexpectedly lowered")
            } catch (failure: Unsupported) {
                failure
            }
            val rejection = decisions.single { it.kind == KlibDependencyDecision.Kind.REJECTED }
            check(failure.diagnostic.code == "UNSUPPORTED_KLIB_DEPENDENCY") { failure.diagnostic }
            check(rejection.signature == capacityConstructor.signature.toString() &&
                failure.diagnostic.source == rejection.callSite && rejection.callSite?.endsWithSource("Consumer.kt") == true) {
                rejection
            }
            check(File(checkNotNull(rejection.library)).canonicalFile == stdlib.canonicalFile)
            check(rejection.declaration.file?.endsWith("js/src/kotlin/collections/ArrayList.kt") == true)
            check(output.listFiles().orEmpty().none { it.extension == "ets" })
            File(output, "rejection.tsv").writeText(
                "${failure.diagnostic.code}\t${rejection.signature}\t${rejection.library}\t${rejection.declaration}" +
                    "\t${rejection.callSite}\t${rejection.detail}\n")
            println("PASS source-linked rejection when capacity constructor primitive is absent")
            return@withKlibModules
        }
        val result = session.lowerToEts(listOf(rule, StandardLibraryRules()), decisions::add)
        val bodies = decisions.filter { it.kind == KlibDependencyDecision.Kind.REUSABLE_BODY }.map { it.signature }.toSet()
        check(listOf(map, mapNotNull).all { it.signature.toString() in bodies }) { bodies }
        val replacements = decisions.filter { it.kind == KlibDependencyDecision.Kind.TARGET_REPLACEMENT &&
            it.detail.contains("KlibCollectionRuntimeRule") }.map { it.signature }.toSet()
        val expectedReplacements = setOf(emptyConstructor, capacityConstructor, bindings.iterator, bindings.hasNext,
            bindings.next, checkNotNull(bindings.append), checkNotNull(bindings.collectionSizeOrDefault))
            .map { it.signature.toString() }.toSet()
        check(replacements == expectedReplacements) { replacements }
        check(result.runtimeSymbols == setOf("stdlib:__etsIterator", "stdlib:__etsArrayIterator", "stdlib:__etsIntDiv",
            "stdlib:__etsIntRem", "stdlib:__etsListAdd", "stdlib:__etsThrowable")) { result.runtimeSymbols }
        val emitted = emitEtsModules(result.program, StandardLibraryRuntime)
        check(emitted.keys == setOf("Consumer.ets"))
        val code = emitted.getValue("Consumer.ets")
        check("__etsListMap" !in code && "function mapShift" in code && "function mapEvenHalves" in code)
        File(output, "Consumer.ets").writeText(code)
        File(output, "decisions.tsv").writeText(decisions.joinToString("\n") {
            "${it.kind}\t${it.signature}\t${it.library}\t${it.declaration}\t${it.callSite}\t${it.detail}"
        })
        File(output, "runtime-symbols.txt").writeText(result.runtimeSymbols.sorted().joinToString("\n"))
        File(output, "official-bodies.txt").writeText(approved.map { symbolName(it.owner) }.sorted().joinToString("\n"))
        println("PASS official map/mapNotNull bodies with symbol-bound collection primitives")
    }
}

private fun SourceSpan.endsWithSource(name: String): Boolean = file?.endsWith(name) == true && start >= 0 && end >= start
