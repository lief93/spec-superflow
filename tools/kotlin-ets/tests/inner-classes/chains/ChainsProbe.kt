@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.chains

import dev.ets.*
import java.io.File
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*

private fun span(owner: IrClass) = SourceSpan(sourceFile(owner)!!.fileEntry.name, owner.startOffset, owner.endOffset)

fun main(args: Array<String>) {
    val output = File(args[1])
    val files = args.drop(3)
    val failure = runCatching {
        withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + files) { module ->
            check(args[2] == "current") { "Old core unexpectedly accepted inner chains" }
            File(output, "lowered.ir").writeText(module.dump())
            val classes = module.files.flatMap { it.declarations }.filterIsInstance<IrClass>()
            val bindings = classes.mapNotNull { owner -> sourceInnerClassBinding(owner)?.let { owner to it } }.toMap()
            check(bindings.size == 5)
            fun lower() = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())).lower(module)
            val names = classes.associateWith { it.name }
            val program = lower()
            check(classes.all { it.name == names.getValue(it) })
            val targets = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().associateBy { it.symbol.id }
            val nodes = mutableListOf<EtsNode>()
            program.files.forEach { file -> file.declarations.forEach { walkEts(it, nodes::add) } }
            val records = mutableListOf<String>()
            for ((owner, binding) in bindings) {
                val target = targets.getValue(etsClassSymbol(owner.name.asString(), span(owner)).id)
                val outer = targets.getValue(etsClassSymbol(binding.outer.name.asString(), span(binding.outer)).id)
                check(program.files.single { target in it.declarations }.sourcePath == binding.source.file)
                check((target.sourceName ?: target.name) == owner.name.asString() && target.source == binding.source)
                val ctor = target.members.filterIsInstance<EtsFunction>().single { it.kind == EtsFunctionKind.CONSTRUCTOR }
                val write = (ctor.body.first() as EtsExpressionStatement).expression as EtsAssignment
                val member = write.target as EtsMember
                val field = target.members.filterIsInstance<EtsField>().single { it.symbol.id == member.symbolId }
                check(field.symbol.type == outer.symbol.type && ctor.parameters.first().symbol.type == outer.symbol.type)
                check((write.value as EtsReference).symbol == ctor.parameters.first().symbol)
                check((field.visibility == EtsVisibility.PRIVATE) == bindings.values.none { it.outer === owner })
                check(ctor.parameters.drop(1).map { it.symbol.name } == binding.constructor.valueParameters.drop(1).map { it.name.asString() })
                check(nodes.filterIsInstance<EtsMember>().filter { it.symbolId == field.symbol.id }
                    .all { it.name == field.symbol.name && it.type == field.symbol.type })
                check(binding.field.type.classOrNull?.owner === binding.outer)
                records += "${target.name}\t${target.symbol.id}\t${outer.symbol.id}\t${field.symbol}\tprivate=${field.visibility == EtsVisibility.PRIVATE}"
            }
            check(nodes.filterIsInstance<EtsMember>().any { it.receiver is EtsMember &&
                bindings.keys.any { owner -> it.type == targets.getValue(etsClassSymbol(owner.name.asString(), span(owner)).id).symbol.type } })
            File(output, "bindings.tsv").writeText(records.joinToString("\n"))
            val middle = bindings.keys.first { it.name.asString() == "Inner" && bindings.values.any { binding -> binding.outer === it } }
            val binding = bindings.getValue(middle)
            val oldType = binding.field.type
            binding.field.type = middle.defaultType
            val bad = try { runCatching { lower() }.exceptionOrNull() } finally { binding.field.type = oldType }
            check(bad is Unsupported && bad.diagnostic.source == binding.source && bad.diagnostic.message.contains("Invalid registered inner"))
            File(output, "malformed.txt").writeText(bad.diagnostic.toString())
            val modules = File(output, "modules").also { check(it.mkdir()) }
            emitEtsModules(program, StandardLibraryRuntime).forEach { (name, text) -> File(modules, name).writeText(text) }
            File(output, "Combined.ets").writeText(emitEtsProgram(program, StandardLibraryRuntime))
        }
    }.exceptionOrNull()
    if (args[2] != "current") {
        check(failure is Unsupported) { "$failure" }
        val expected = if (args[2] == "red") "top-level outer" else args[2]
        check(failure.diagnostic.message.contains(expected)) { "$failure" }
        val at = failure.diagnostic.source
        check(at.file in files && at.start >= 0 && at.end > at.start)
        val text = File(at.file).readText().substring(at.start, at.end)
        if (expected == "capture-aware allocation") check(text.startsWith("constructor(")) { text }
        else check(text.startsWith("inner class") || text.startsWith("object")) { text }
        File(output, "rejection.txt").writeText("${failure.diagnostic}\n$text")
        println("PASS source-linked rejection: ${failure.diagnostic}")
    } else {
        if (failure != null) throw failure
        println("PASS five registered chain links, immediate owner identity, source files, canonical field types and malformed ancestor")
    }
}
