@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.backend.common.lower.BOUND_VALUE_PARAMETER
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    val output = File(args[1])
    val baseline = args[2] == "baseline"
    val program = withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(3)) { module ->
        File(output, "lowered.ir").writeText(module.dump())
        val functions = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
        val helpers = functions.filter { it.name.asString() == "\$seed" }
        val owner = module.files.flatMap { it.declarations }.filterIsInstance<IrClass>().single()
        val constructor = owner.constructors.single()
        val capture = constructor.valueParameters.single { it.origin === BOUND_VALUE_PARAMETER }
        val sourceParameters = constructor.valueParameters.filter { it !== capture }
        val originalNames = constructor.valueParameters.map { it.symbol to it.name }
        val calls = mutableListOf<IrCall>()
        owner.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrCall && element.symbol.owner in helpers) calls += element
                element.acceptChildrenVoid(this)
            }
        })
        check(calls.size == 1)
        val call = calls.single()
        val callSource = SourceSpan(sourceFile(owner)!!.fileEntry.name, call.startOffset, call.endOffset)
        val attempted = runCatching { EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())).lower(module) }
        if (baseline) {
            val failure = attempted.exceptionOrNull()
            val expectedName = if (helpers.size == 1) "\$seed" else "\$seed_0"
            check(failure is InvalidTarget && failure.message!!.contains("Unbound target symbol: $expectedName")) { "$failure" }
            check(failure.source == callSource) { "${failure.source}, expected $callSource" }
            File(output, "rejection.txt").writeText("${failure.message}\n${failure.source}\nFlat and modules blocked before emission")
            return@withKotlinModule null
        }
        val program = attempted.getOrThrow()
        val target = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().single()
        val emittedConstructor = target.members.filterIsInstance<EtsFunction>().single { it.kind == EtsFunctionKind.CONSTRUCTOR }
        val targetFunctions = program.files.flatMap { it.declarations }.filterIsInstance<EtsFunction>()
        val names = OverloadNaming()
        for (original in functions) {
            val source = SourceSpan(sourceFile(original)!!.fileEntry.name, original.startOffset, original.endOffset)
            val emitted = targetFunctions.single { it.source == source }
            check(emitted.name == names.name(original))
            check((emitted.sourceName ?: emitted.name) == original.name.asString())
            check(emitted.symbol.id == etsFunctionSymbol(original.name.asString(), emptyList(), EtsTypes.VOID, source).id)
            check(emitted.parameters.map { it.symbol.name } == original.valueParameters.map { it.name.asString() })
        }
        check(constructor.valueParameters.map { it.symbol to it.name } == originalNames)
        val captureName = emittedConstructor.parameters[constructor.valueParameters.indexOf(capture)].symbol.name
        check(captureName == if (helpers.size == 1) "\$seed_0" else "\$seed_1")
        check(captureName !in targetFunctions.map { it.name })
        for (parameter in sourceParameters) {
            check(emittedConstructor.parameters[constructor.valueParameters.indexOf(parameter)].symbol.name == parameter.name.asString())
        }
        val nodes = mutableListOf<EtsNode>()
        walkEts(target, nodes::add)
        val emittedCall = nodes.filterIsInstance<EtsCall>().single { it.source == callSource }
        val reference = emittedCall.callee as EtsReference
        check(reference.symbol == targetFunctions.single { it.name == names.name(call.symbol.owner) }.symbol)
        val fields = target.members.filterIsInstance<EtsField>()
        check(fields.count { it.symbol.name == "value" } == 1)
        if (sourceParameters.isNotEmpty()) check(fields.count { it.symbol.name == "\$seed" } == 1)
        File(output, "bindings.txt").writeText("capture=$captureName\ncallee=${reference.symbol}\nsourceParameters=${sourceParameters.map { it.name }}")
        program
    }
    if (baseline) { println("PASS expected RED at canonical helper call"); return }
    checkNotNull(program)
    val modules = File(output, "modules").also { check(it.mkdir()) }
    emitEtsModules(program, StandardLibraryRuntime).forEach { (name, text) -> File(modules, name).writeText(text) }
    File(output, "Combined.ets").writeText(emitEtsProgram(program, StandardLibraryRuntime))
    println("PASS emitted helper/capture names, canonical calls, original source names and parameters")
}
