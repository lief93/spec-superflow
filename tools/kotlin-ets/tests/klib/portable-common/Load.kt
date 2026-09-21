@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.portabletest

import dev.ets.*
import dev.ets.dependency.klib.KlibLoader
import dev.ets.dependency.klib.KlibModuleSelection
import java.io.File
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrSimpleFunctionSymbol
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

// Experiment-only actual boundary. Match canonical symbols from the explicitly
// selected signature KLIB, never map/filter names or arbitrary matching text.
private class PrimitiveRules(private val primitives: Map<IrSimpleFunctionSymbol, String>) : CallRule {
    val used = mutableSetOf<String>()
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val primitive = primitives[call.symbol] ?: return null
        used += primitive
        val at = language.source(call)
        val result = language.type(call.type)
        return when (primitive) {
            "newList" -> EtsArray(emptyList(), language.type(checkNotNull(call.getTypeArgument(0))), at)
            "append" -> {
                val arguments = (0 until call.valueArgumentsCount).map {
                    language.expression(checkNotNull(call.getValueArgument(it)), scope)
                }
                EtsCall(EtsReference(EtsSymbol("stdlib:__etsListAdd", "__etsListAdd",
                    EtsFunctionType(arguments.map { it.type }, result), at, external = true)),
                    arguments, result, at, listOf(language.type(checkNotNull(call.getTypeArgument(0)))))
            }
            "exhausted" -> EtsCall(EtsLambda(emptyList(), listOf(
                EtsThrow(namedTargetFailure("NoSuchElementException", at, EtsLiteral(null, EtsTypes.NULL, at)), at)), result, at), emptyList(), result, at)
            else -> error("Unapproved primitive: $primitive")
        }
    }
}

fun main(args: Array<String>) {
    val output = File(args[0])
    val main = File(args[1])
    val bodies = File(args[2])
    val primitives = File(args[3])
    val stdlib = File(args[4])
    KlibLoader.withKlibModules(KlibModuleSelection(main, listOf(main, bodies), listOf(primitives, stdlib))) { session ->
        val modules = session.linkedModules()
        check(modules.size == 2)
        val primitiveModule = session.allDependencies.single { it.descriptor.name.asString() == "<primitives>" }
        val declarations = primitiveModule.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
        check(declarations.map { it.name.asString() }.toSet() == setOf("newList", "append", "exhausted"))
        check(declarations.all { it.isExternal && it.body == null && it.dispatchReceiverParameter == null &&
            it.extensionReceiverParameter == null })
        val primitiveSymbols = declarations.associate { it.symbol to it.name.asString() }
        val rules = PrimitiveRules(primitiveSymbols)
        val calls = linkedSetOf<String>()
        val pureFunctions = mutableListOf<IrFunction>()
        val intrinsicNames = setOf("kotlin.Any.<init>", "kotlin.Int.plus", "kotlin.Int.rem", "kotlin.Boolean.not", "kotlin.String.plus",
            "kotlin.internal.ir.lessOrEqual", "kotlin.internal.ir.EQEQ", "kotlin.Function1.invoke")
        modules.forEach { module -> module.acceptChildrenVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrFunction && element.body != null) {
                    pureFunctions += element
                    check(!File(element.file.fileEntry.name).exists()) { "Producer source still exists" }
                }
                if (element is IrFunctionAccessExpression) {
                    val owner = element.symbol.owner
                    val name = owner.fqNameWhenAvailable?.asString() ?: owner.name.asString()
                    val selected = sourceFile(owner)?.module in modules
                    val boundary = element is IrCall && element.symbol in primitiveSymbols
                    check(selected || boundary || name in intrinsicNames) { "Unapproved residual call: $name" }
                    calls += "${if (selected) "PURE_BODY" else if (boundary) "TARGET_PRIMITIVE" else "LANGUAGE_INTRINSIC"}\t$name\t${element.symbol.signature}"
                    if (selected) check(owner.body != null) { "Selected callee lacks body: $name" }
                }
                element.acceptChildrenVoid(this)
            }
        }) }
        check(pureFunctions.any { it.name.asString() == "mapBody" && !it.isInline })
        File(output, "loaded.ir").writeText(modules.joinToString("\n") { it.dump() })
        File(output, "closure.tsv").writeText(calls.sorted().joinToString("\n"))
        fun lower(ordered: List<IrModuleFragment>) = EtsBackend(DiagnosticSink(), listOf(rules, StandardLibraryRules())).lower(ordered)
        val program = lower(modules)
        val helpers = linkedSetOf<String>()
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) {
            if (it is EtsReference && it.symbol.external && it.symbol.id.startsWith("stdlib:")) helpers += it.symbol.id
            if (it is EtsNew && it.type.symbolId?.startsWith("stdlib:") == true) helpers += it.type.symbolId!!
        } } }
        check(helpers == setOf("stdlib:Math", "stdlib:__etsThrowable", "stdlib:__etsIntRem", "stdlib:__etsListAdd")) {
            "Unexpected runtime dependency: $helpers"
        }
        File(output, "runtime-symbols.txt").writeText(helpers.sorted().joinToString("\n"))
        val emitted = emitEtsModules(program, StandardLibraryRuntime)
        val reversed = emitEtsModules(lower(modules.reversed()), StandardLibraryRuntime)
        emitted.forEach { (name, code) -> File(output, "normal-$name").writeText(code) }
        reversed.forEach { (name, code) -> File(output, "reversed-$name").writeText(code) }
        // The existing language lowerer numbers loop labels across the session.
        // Reordering files may rename labels; preserve each label's identity in
        // this alpha-equivalence check rather than claiming byte-identical output.
        fun canonicalLabels(code: String): String {
            val labels = linkedMapOf<String, String>()
            return Regex("__etsLoop[0-9]+\\b").replace(code) { match ->
                labels.getOrPut(match.value) { "__etsLoop${labels.size}" }
            }
        }
        check(emitted.mapValues { canonicalLabels(it.value) } == reversed.mapValues { canonicalLabels(it.value) }) {
            "Module order changed output beyond loop-label names"
        }
        // Remove every materialized stdlib function body, then repeat lowering.
        // Identical target output proves the lowerer does not consult JS bodies.
        var removedBodies = 0
        session.allDependencies.filter { it !in modules && it !== primitiveModule }.forEach { module ->
            module.acceptChildrenVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) {
                    element.acceptChildrenVoid(this)
                    if (element is IrFunction && element.body != null) {
                        element.body = null
                        removedBodies++
                    }
                }
            })
        }
        check(removedBodies > 0) { "Body independence control did not remove any stdlib bodies" }
        check(emitted == emitEtsModules(lower(modules), StandardLibraryRuntime)) {
            "ETS output depends on dependency-only stdlib function bodies"
        }
        File(output, "removed-stdlib-bodies.txt").writeText(removedBodies.toString())
        check(rules.used == setOf("newList", "append", "exhausted"))
        check(emitted.keys == setOf("Bodies.ets", "Consumer.ets"))
        emitted.forEach { (name, code) -> File(output, name).writeText(code) }
        println("PASS pure body KLIB: ${pureFunctions.size} bodies, three actual primitives, no stdlib body emission")
    }
}
