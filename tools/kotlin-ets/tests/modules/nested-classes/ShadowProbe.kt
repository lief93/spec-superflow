@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    val work = File(args[1])
    val program = withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(2)) { module ->
        File(work, "source.ir").writeText(module.dump())
        val originals = mutableListOf<IrDeclarationWithName>()
        module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrDeclarationWithName) originals += element
                element.acceptChildrenVoid(this)
            }
        })
        fun span(value: IrDeclaration) = SourceSpan(sourceFile(value)!!.fileEntry.name, value.startOffset, value.endOffset)
        val originalNames = originals.associateWith { it.name }
        val program = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())).lower(module)
        originals.forEach { check(it.name == originalNames.getValue(it)) }
        val nodes = mutableListOf<EtsNode>()
        program.files.forEach { it.declarations.forEach { declaration -> walkEts(declaration, nodes::add) } }
        val classes = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>()
        check(classes.size == 7 && classes.count { it.sourceName != null } == 1)
        val originalNodes = originals.filterIsInstance<IrClass>().filter { it.name.asString() == "Node" }.sortedBy { it.startOffset }
        val targets = originalNodes.map { original -> classes.single { it.symbol.id == etsClassSymbol("Node", span(original)).id } }
        check(targets.map { it.name } == listOf("Node_1", "Node"))
        check(targets[0].sourceName == "Node" && targets[1].sourceName == null)
        check(classes.filter { it.name in setOf("Safe", "Unique") }.size == 2)
        for (original in originals.filterIsInstance<IrSimpleFunction>().filter {
            it.parent is IrFile && !it.name.isSpecial
        }) {
            val target = nodes.filterIsInstance<EtsFunction>().single {
                it.symbol.id == etsFunctionSymbol(original.name.asString(), emptyList(), EtsTypes.VOID, span(original)).id
            }
            check(target.name == original.name.asString())
            check(target.parameters.map { it.symbol.name } == original.valueParameters.map { it.name.asString() })
        }
        val locals = originals.filterIsInstance<IrVariable>().filter { it.origin == IrDeclarationOrigin.DEFINED &&
            it.name.asString() in setOf("Node", "Safe") }
        check(locals.size >= 5)
        locals.forEach { original ->
            check(nodes.filterIsInstance<EtsVariable>().single { it.source == span(original) }.symbol.name == original.name.asString())
        }
        val holder = classes.single { it.name == "Holder" }
        check(holder.members.filterIsInstance<EtsFunction>().single { it.kind == EtsFunctionKind.CONSTRUCTOR }
            .parameters.single().symbol.name == "Node")
        val classValues = nodes.filterIsInstance<EtsReference>().filter { it.symbol.id in classes.map { value -> value.symbol.id } }
        check(classValues.any { it.symbol == targets[0].symbol })
        check(nodes.filterIsInstance<EtsNew>().any { it.classType == targets[0].symbol.type })
        File(work, "bindings.tsv").writeText(classes.joinToString("\n") { "${it.source}\t${it.sourceName ?: it.name}\t${it.name}\t${it.symbol.id}" })
        program
    }
    val modules = emitEtsModules(program, StandardLibraryRuntime)
    val output = File(work, "modules")
    check(output.mkdir())
    modules.forEach { (name, text) -> File(output, name).writeText(text) }
    File(work, "Combined.ets").writeText(emitEtsProgram(program, StandardLibraryRuntime))
    println("PASS actual class-value lexical scopes, one fresh class name, unchanged parameter/local/source identities")
}
