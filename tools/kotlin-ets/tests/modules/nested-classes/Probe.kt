@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.IrConstructorCall
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    val work = File(args[1])
    val baseline = args[2] == "baseline"
    val program = withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(3)) { module ->
        File(work, "lowered.ir").writeText(module.dump())
        if (baseline) return@withKotlinModule EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())).lower(module)
        val originals = module.files.flatMap { it.declarations }.filterIsInstance<IrClass>()
        check(originals.size == 11) { "Expected eleven flattened source classes/interfaces, got ${originals.map { it.name }}" }
        val names = originals.associateWith { it.name }
        val positions = originals.associateWith { SourceSpan(sourceFile(it)!!.fileEntry.name, it.startOffset, it.endOffset) }
        val binders = originals.associateWith { it.typeParameters.map { parameter -> parameter.symbol to parameter.name } }
        val methods = originals.flatMap { it.declarations.filterIsInstance<IrSimpleFunction>() }
            .filter { !it.isFakeOverride && it.correspondingPropertySymbol == null }
            .associateWith { it.name to it.valueParameters.map { parameter -> parameter.name } }
        val constructors = mutableListOf<Pair<String, IrConstructorCall>>()
        module.files.forEach { file -> file.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrConstructorCall && element.type.classOrNull?.owner in originals)
                    constructors += file.fileEntry.name to element
                element.acceptChildrenVoid(this)
            }
        }) }
        val backend = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules()))
        val program = backend.lower(module)
        val targetClasses = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>()
        val targetById = targetClasses.associateBy { it.symbol.id }
        val nodes = mutableListOf<EtsNode>()
        program.files.forEach { file -> file.declarations.forEach { walkEts(it, nodes::add) } }
        val records = mutableListOf<String>()
        for (original in originals) {
            val source = positions.getValue(original)
            val id = etsClassSymbol(names.getValue(original).asString(), source).id
            val target = targetById.getValue(id)
            check(original.name == names.getValue(original))
            check(SourceSpan(sourceFile(original)!!.fileEntry.name, original.startOffset, original.endOffset) == source)
            check(original.typeParameters.map { it.symbol to it.name } == binders.getValue(original))
            check(target.source == source)
            check(target.sourceName == original.name.asString().takeUnless { it == target.name })
            check(program.files.single { target in it.declarations }.sourcePath == source.file)
            check(target.symbol == etsClassSymbol(target.name, source, original.name.asString()))
            check(target.typeParameters.size == original.typeParameters.size)
            original.typeParameters.zip(target.typeParameters).forEach { (ir, ets) ->
                check(ets.name == ir.name.asString())
                check(ets.id == "type-parameter:class:${source.file}:${source.start}:${original.name}:${ir.index}:${ir.name}")
            }
            check(target.exported == (original.name.asString() != "Local"))
            records += "class\t${source.file}:${source.start}\t${original.name}\t${target.name}\t$id"
        }
        for ((original, before) in methods) {
            check((original.name to original.valueParameters.map { it.name }) == before)
            val source = SourceSpan(sourceFile(original)!!.fileEntry.name, original.startOffset, original.endOffset)
            val target = nodes.filterIsInstance<EtsFunction>().single {
                it.symbol.id == etsFunctionSymbol(original.name.asString(), emptyList(), EtsTypes.VOID, source).id
            }
            check(target.name == original.name.asString())
            check(target.parameters.map { it.symbol.name } == original.valueParameters.map { it.name.asString() })
        }
        check(targetClasses.count { it.sourceName != null } == 5)
        check(targetClasses.filter { it.sourceName == "Node" }.map { it.name }.toSet() == setOf("Node_1", "Node_2"))
        check(targetClasses.single { it.sourceName == "Local" }.name == "Local_1")
        val cellBinders = targetClasses.filter { (it.sourceName ?: it.name) == "Cell" }.map { it.typeParameters.single().id }
        check(cellBinders.size == 3 && cellBinders.distinct().size == 3)
        check(targetClasses.single { it.kind == EtsClassKind.INTERFACE }.let { it.name == "Cell_1" && it.sourceName == "Cell" })
        val classReferences = nodes.filterIsInstance<EtsReference>().filter { it.symbol.id in targetById }
        check(classReferences.any { it.symbol.name == "Node_1" })
        classReferences.forEach { check(it.symbol == targetById.getValue(it.symbol.id).symbol) }
        check(constructors.isNotEmpty())
        for ((file, call) in constructors) {
            val irClass = call.type.classOrNull!!.owner
            val id = etsClassSymbol(irClass.name.asString(), positions.getValue(irClass)).id
            val creation = nodes.filterIsInstance<EtsNew>().single {
                it.source == SourceSpan(file, call.startOffset, call.endOffset) && it.classType.symbolId == id
            }
            check(creation.classType.name == targetById.getValue(id).name)
            check(creation.classType == backend.language.type(call.type))
            records += "constructor\t$file:${call.startOffset}\t$id\t${creation.classType.name}"
        }
        check(nodes.filterIsInstance<EtsNew>().any { creation ->
            creation.classType.arguments.any { it is EtsNamedType && it.symbolId in targetById && it.arguments.isNotEmpty() }
        }) { "Nested generic arguments require an independent typed proof" }
        File(work, "bindings.tsv").writeText(records.joinToString("\n"))
        program
    }
    check(!baseline) { "Baseline unexpectedly accepted nested/local declarations" }
    val rejected = checkNestedBindings(program)
    val modules = emitEtsModules(program, StandardLibraryRuntime)
    val output = File(work, "modules")
    check(!output.exists() && output.mkdir())
    modules.forEach { (name, text) -> File(output, name).writeText(text) }
    File(work, "Combined.ets").writeText(emitEtsProgram(program, StandardLibraryRuntime))
    File(work, "negative-count.txt").writeText(rejected.toString())
    println("PASS eleven source classes/interfaces, five minimal renames, original binders/constructor IDs, $rejected typed negatives")
}
