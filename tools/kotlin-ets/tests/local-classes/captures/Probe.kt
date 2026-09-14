@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.backend.common.lower.LocalDeclarationsLowering
import org.jetbrains.kotlin.backend.common.lower.BOUND_VALUE_PARAMETER
import org.jetbrains.kotlin.backend.common.lower.BOUND_RECEIVER_PARAMETER
import org.jetbrains.kotlin.descriptors.DescriptorVisibilities
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.expressions.impl.IrGetValueImpl
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.util.*

private fun captured(field: IrField) =
    field.origin === LocalDeclarationsLowering.DECLARATION_ORIGIN_FIELD_FOR_CAPTURED_VALUE

private fun bound(parameter: IrValueParameter) =
    parameter.origin === BOUND_VALUE_PARAMETER || parameter.origin === BOUND_RECEIVER_PARAMETER

private fun span(declaration: IrDeclaration) =
    SourceSpan(sourceFile(declaration)!!.fileEntry.name, declaration.startOffset, declaration.endOffset)

fun main(args: Array<String>) {
    val output = File(args[1])
    val baseline = args[2] == "baseline"
    var negatives = 0
    val program = withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(3)) { module ->
        File(output, "lowered.ir").writeText(module.dump())
        fun lower() = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())).lower(module)
        if (baseline) {
            val failure = runCatching { lower() }.exceptionOrNull()
            check(failure is Unsupported && failure.diagnostic.message.contains("Unsupported nested source class declaration")) {
                "Expected capture-unaware language rejection, got $failure"
            }
            check(failure.diagnostic.source.file in args.drop(3))
            check(failure.diagnostic.source.start >= 0 && failure.diagnostic.source.end > failure.diagnostic.source.start)
            File(output, "rejection.txt").writeText(failure.diagnostic.toString())
            return@withKotlinModule null
        }
        val classes = module.files.flatMap { it.declarations }.filterIsInstance<IrClass>()
        val owners = classes.filter { it.declarations.filterIsInstance<IrField>().any(::captured) }
        check(owners.map { it.name.asString() }.toSet() == setOf("View", "Counter", "Reader", "Handle", "Defaulted", "Collision"))
        val backend = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules()))
        val program = backend.lower(module)
        val targets = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().associateBy { it.symbol.id }
        val nodes = mutableListOf<EtsNode>()
        program.files.forEach { file -> file.declarations.forEach { walkEts(it, nodes::add) } }
        val records = mutableListOf<String>()
        for (owner in owners) {
            val target = targets.getValue(etsClassSymbol(owner.name.asString(), span(owner)).id)
            check(!target.exported && target.source == span(owner))
            check(program.files.single { target in it.declarations }.sourcePath == span(owner).file)
            val constructor = owner.constructors.single()
            val emitted = target.members.filterIsInstance<EtsFunction>().single { it.kind == EtsFunctionKind.CONSTRUCTOR }
            check(emitted.parameters.size == constructor.valueParameters.size)
            constructor.valueParameters.zip(emitted.parameters).filterNot { bound(it.first) }.forEach { (ir, ets) ->
                check(ets.symbol.name == ir.name.asString())
            }
            val fields = owner.declarations.filterIsInstance<IrField>().filter(::captured)
            val writes = (constructor.body as IrBlockBody).statements.take(fields.size).map { it as IrSetField }
            writes.zip(emitted.body.take(fields.size)).forEach { (write, statement) ->
                val assignment = (statement as EtsExpressionStatement).expression as EtsAssignment
                val member = assignment.target as EtsMember
                val field = target.members.filterIsInstance<EtsField>().single { it.symbol.id == member.symbolId }
                val parameterIndex = constructor.valueParameters.indexOfFirst { it.symbol == (write.value as IrGetValue).symbol }
                check(parameterIndex >= 0 && bound(constructor.valueParameters[parameterIndex]))
                check((assignment.value as EtsReference).symbol == emitted.parameters[parameterIndex].symbol)
                check(field.private && !field.static && field.initializer == null)
                check(field.source == span(write.symbol.owner) && field.source == span(owner))
                check(field.symbol.type == backend.language.type(write.symbol.owner.type))
                check(member.type == field.symbol.type && member.name == field.symbol.name)
                check((member.receiver as EtsReference).symbol.name == "this")
                check(statement.source == field.source && assignment.source == field.source && member.source == field.source)
                check(assignment.value.source == field.source)
                val reads = nodes.filterIsInstance<EtsMember>().filter { it.symbolId == field.symbol.id }
                check(reads.size >= 2 && reads.all { it.name == field.symbol.name && it.type == field.symbol.type })
                val original = write.symbol.owner.name.asString()
                val sourceNames = owner.declarations.filterIsInstance<IrProperty>().map { it.name.asString() }
                if (original in sourceNames) check(field.symbol.name !in sourceNames) else check(field.symbol.name == original)
                records += "${owner.name}\t$original\t${field.symbol.name}\t${field.symbol.id}\t${field.symbol.type}"
            }
            for (property in owner.declarations.filterIsInstance<IrProperty>().filterNot { it.isFakeOverride }) {
                check(target.members.filterIsInstance<EtsField>().any { it.symbol.name == property.name.asString() })
            }
            owner.declarations.filterIsInstance<IrSimpleFunction>().filter { !it.isFakeOverride && it.correspondingPropertySymbol == null }
                .forEach { method ->
                    val emittedMethod = target.members.filterIsInstance<EtsFunction>().single { it.source == span(method) }
                    check(emittedMethod.name == method.name.asString())
                    check(emittedMethod.parameters.map { it.symbol.name } == method.valueParameters.map { it.name.asString() })
                }
        }
        for (name in listOf("Counter", "Handle")) {
            val owner = owners.single { it.name.asString() == name }
            val cell = owner.declarations.filterIsInstance<IrField>().single(::captured).type.classOrNull!!.owner
            check(cell.origin === ETS_SHARED_VARIABLE_CELL)
            check(targets.containsKey(etsClassSymbol(cell.name.asString(), span(cell)).id))
        }
        val collision = targets.values.single { (it.sourceName ?: it.name) == "Collision" }
        check(collision.members.filterIsInstance<EtsField>().map { it.symbol.name }.toSet().size == 3)
        check(collision.members.filterIsInstance<EtsFunction>().single { it.kind == EtsFunctionKind.CONSTRUCTOR }
            .parameters.map { it.symbol.name }.toSet().size == 3)
        File(output, "bindings.tsv").writeText(records.joinToString("\n"))

        val owner = owners.single { it.name.asString() == "View" }
        val field = owner.declarations.filterIsInstance<IrField>().single(::captured)
        val constructor = owner.constructors.single()
        val body = constructor.body as IrBlockBody
        val write = body.statements.first() as IrSetField
        fun reject(label: String, expected: String, at: SourceSpan, change: () -> Unit, restore: () -> Unit) {
            val failure = try { change(); runCatching { lower() }.exceptionOrNull() } finally { restore() }
            check(failure is Unsupported && failure.diagnostic.message.contains(expected)) { "$label: $failure" }
            check(failure.diagnostic.source == at) { "$label: ${failure.diagnostic.source}, expected $at" }
            records += "negative\t$label\t${failure.diagnostic}"
            negatives++
        }
        val origin = field.origin
        reject("Origin text is not identity", "Unsupported nested source class declaration", span(field),
            { field.origin = IrDeclarationOriginImpl(origin.name, true) }, { field.origin = origin })
        val visibility = owner.visibility
        reject("Nonlocal owner", "Unsupported captured field ownership", span(field),
            { owner.visibility = DescriptorVisibilities.PRIVATE }, { owner.visibility = visibility })
        reject("Static captured field", "Unsupported captured field ownership", span(field),
            { field.isStatic = true }, { field.isStatic = false })
        reject("Mutable capture storage", "Unsupported captured field ownership", span(field),
            { field.isFinal = false }, { field.isFinal = true })
        val statements = body.statements.toList()
        reject("Late capture prefix", "Captured fields require", span(constructor),
            { body.statements.removeAt(0); body.statements.add(1, write) },
            { body.statements.clear(); body.statements.addAll(statements) })
        val writeOrigin = write.origin
        reject("Unofficial prefix", "one direct leading delegation", span(constructor),
            { write.origin = null }, { write.origin = writeOrigin })
        val value = write.value
        reject("Source parameter substituted for capture", "Invalid official captured-field", span(field),
            { write.value = IrGetValueImpl(-1, -1, constructor.valueParameters.first { !bound(it) }.symbol) },
            { write.value = value })
        val receiver = write.receiver
        reject("Wrong capture receiver", "Invalid official captured-field", span(field),
            { write.receiver = value }, { write.receiver = receiver })
        File(output, "negatives.tsv").writeText(records.filter { it.startsWith("negative\t") }.joinToString("\n"))
        program
    }
    if (baseline) { println("PASS expected RED: source-linked capture-field rejection"); return }
    checkNotNull(program)
    val modules = File(output, "modules").also { check(it.mkdir()) }
    emitEtsModules(program, StandardLibraryRuntime).forEach { (name, text) -> File(modules, name).writeText(text) }
    File(output, "Combined.ets").writeText(emitEtsProgram(program, StandardLibraryRuntime))
    File(output, "negative-count.txt").writeText(negatives.toString())
    println("PASS six captured classes, canonical fields/parameters/types/source, $negatives malformed IR negatives")
}
