@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.klibtest

import dev.ets.*
import dev.ets.dependency.klib.*
import java.io.File
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.symbols.IrFunctionSymbol
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid

private class BiasFallback(
    private val bias: IrFunctionSymbol,
) : CallRule, KlibAdapterFallback {
    override val klibAdapterFallbackSymbols = setOf(bias)
    var calls = 0

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        if (call.symbol !== bias) return null
        calls++
        val at = language.source(call)
        val value = language.expression(checkNotNull(call.getValueArgument(0)), scope)
        val amount = language.expression(checkNotNull(call.getValueArgument(1)), scope)
        return EtsBinary("|", EtsBinary("+", value, amount, EtsTypes.NUMBER, at),
            EtsLiteral(0, EtsTypes.NUMBER, at), EtsTypes.NUMBER, at)
    }
}

fun main(args: Array<String>) {
    val mode = args[0]
    val output = File(args[1])
    val application = File(args[2])
    val library = File(args[3])
    val helper = File(args[4])
    val stdlib = File(args[5])
    val selection = KlibModuleSelection(
        main = application,
        translated = listOf(application),
        libraries = if (mode == "missing-helper") listOf(library, stdlib)
            else listOf(library, helper, stdlib),
    )
    KlibLoader.withKlibModules(selection) { session ->
        val applicationModule = session.linkedModules().single()
        check(applicationModule.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
            .map { it.name.asString() } == listOf("scenario"))
        val dependencyFunctions = session.allDependencies.flatMap { it.files }.flatMap { it.declarations }
            .filterIsInstance<IrSimpleFunction>()
        // Fixture setup resolves one canonical declaration. Production admission and replacement use symbol identity.
        val bias = dependencyFunctions.single { it.fqNameWhenAvailable?.asString() == "klibhelper.bias" }
        val biasOrigin = session.bodies().resolve(bias.symbol) as FunctionBody.Available
        check((biasOrigin.origin as FunctionBody.Origin.SerializedKlibIr).libraryLocation == helper.canonicalPath)
        val calls = mutableListOf<IrCall>()
        session.allDependencies.forEach { module -> module.acceptChildrenVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrCall) calls += element
                element.acceptChildrenVoid(this)
            }
        }) }
        check(calls.single { it.symbol.owner.fqNameWhenAvailable?.asString() == "klibhelper.bias" }.symbol === bias.symbol)
        val fallback = BiasFallback(bias.symbol)
        val decisions = mutableListOf<KlibDependencyDecision>()
        val rules = if (mode == "positive") listOf<CallRule>(fallback, StandardLibraryRules())
            else listOf(StandardLibraryRules())
        try {
            val result = session.lowerToEts(rules, decisions::add)
            check(mode == "positive") { "Expected dependency rejection in $mode" }
            check(result.decisions == decisions)
            check(fallback.calls == 1) { "Expected exactly one bias replacement, got ${fallback.calls}" }
            val replacement = decisions.single { it.kind == KlibDependencyDecision.Kind.TARGET_REPLACEMENT &&
                it.signature == bias.symbol.signature.toString() }
            check(replacement.library == helper.canonicalPath)
            check(replacement.declaration.file!!.endsWith("Helper.kt"))
            check(replacement.callSite?.file?.endsWith("Library.kt") == true)
            val reused = decisions.filter { it.kind == KlibDependencyDecision.Kind.REUSABLE_BODY }
            for ((signature, location) in listOf(
                "kliblibrary/adjusted|" to library.canonicalPath,
                "kliblibrary/buttonLabel|" to library.canonicalPath,
                "klibhelper/echo|" to helper.canonicalPath,
                "klibhelper/offset|" to helper.canonicalPath,
            )) check(reused.single { it.signature.startsWith(signature) }.library == location)
            check(reused.none { it.signature == bias.symbol.signature.toString() })
            val ordinary = listOf("kliblibrary/adjusted|", "kliblibrary/buttonLabel|",
                "klibhelper/echo|", "klibhelper/offset|")
            check(decisions.none { decision -> decision.kind == KlibDependencyDecision.Kind.TARGET_REPLACEMENT &&
                ordinary.any(decision.signature::startsWith) })
            val emitted = emitEtsModules(result.program, StandardLibraryRuntime)
            check(emitted.keys == setOf("Application.ets", "Library.ets", "Helper.ets")) { emitted.keys }
            emitted.forEach { (name, code) -> File(output, name).writeText(code) }
        } catch (failure: Unsupported) {
            check(mode == "missing-adapter") { failure.diagnostic }
            val diagnostic = failure.diagnostic
            check(diagnostic.code == "UNSUPPORTED_KLIB_DEPENDENCY")
            check(diagnostic.message.contains("kliblibrary/adjusted|")) { diagnostic }
            check(diagnostic.message.contains("klibhelper/bias|")) { diagnostic }
            check(diagnostic.message.contains(library.canonicalPath)) { diagnostic }
            check(diagnostic.message.contains(helper.canonicalPath)) { diagnostic }
            check(diagnostic.message.contains("Fallback decision: no declared typed adapter accepted the call")) { diagnostic }
            val rejected = decisions.last()
            check(rejected.kind == KlibDependencyDecision.Kind.REJECTED)
            check(rejected.library == library.canonicalPath)
            File(output, "rejection.json").writeText("{" +
                "\"code\":" + quote(diagnostic.code) +
                ",\"message\":" + quote(diagnostic.message) +
                ",\"source\":" + diagnosticSourceJson(diagnostic.source) +
                ",\"signature\":" + quote(rejected.signature) +
                ",\"library\":" + quote(rejected.library) +
                ",\"detail\":" + quote(rejected.detail) + "}\n")
            check(output.listFiles()!!.none { it.extension == "ets" })
        }
        File(output, "decisions.tsv").writeText(decisions.joinToString("\n") {
            "${it.kind}\t${it.signature}\t${it.library}\t${it.declaration}\t${it.callSite}\t${it.detail}"
        })
    }
    println("PASS $mode: dependency-only direct/transitive bodies and identity-based fallback")
}
