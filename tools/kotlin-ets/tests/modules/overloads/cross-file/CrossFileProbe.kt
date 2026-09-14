@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    val work = File(args[1])
    val baseline = args[2] == "baseline" || args[2] == "private-baseline"
    val privateGroups = args[2] == "private" || args[2] == "private-baseline"
    val sources = args.drop(3)
    val program = withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + sources) { module ->
        File(work, "actual.ir").writeText(module.dump())
        val originals = mutableListOf<IrSimpleFunction>()
        val calls = mutableListOf<Pair<String, IrCall>>()
        val sourceNames = mutableSetOf<String>()
        module.acceptVoid(object : IrElementVisitorVoid {
            private var currentFile: String? = null
            override fun visitFile(declaration: IrFile) {
                val previous = currentFile
                currentFile = declaration.fileEntry.name
                super.visitFile(declaration)
                currentFile = previous
            }
            override fun visitElement(element: IrElement) {
                if (element is IrDeclarationWithName && !element.name.isSpecial) sourceNames += element.name.asString()
                element.acceptChildrenVoid(this)
            }
            override fun visitSimpleFunction(declaration: IrSimpleFunction) {
                if (!declaration.isFakeOverride && declaration.correspondingPropertySymbol == null &&
                    (declaration.parent is IrFile || declaration.parent is IrClass)) originals += declaration
                super.visitSimpleFunction(declaration)
            }
            override fun visitCall(expression: IrCall) {
                if (sourceFile(expression.symbol.owner)?.fileEntry?.name in sources &&
                    expression.symbol.owner.correspondingPropertySymbol == null) calls += checkNotNull(currentFile) to expression
                super.visitCall(expression)
            }
        })
        val backend = EtsBackend(DiagnosticSink(sources.first()), listOf(StandardLibraryRules()))
        val program = backend.lower(module)
        if (!baseline) {
            val nodes = mutableListOf<EtsNode>()
            program.files.forEach { file -> file.declarations.forEach { walkEts(it, nodes::add) } }
            fun id(function: IrSimpleFunction) = etsFunctionSymbol(function.name.asString(), emptyList(), EtsTypes.VOID,
                SourceSpan(sourceFile(function)!!.fileEntry.name, function.startOffset, function.endOffset)).id
            val declarations = originals.associateWith { original -> nodes.filterIsInstance<EtsFunction>().single { it.symbol.id == id(original) } }
            val renamed = declarations.values.filter { it.sourceName != null }
            check(renamed.size == if (privateGroups) 3 else 2) { "Unexpected collision-driven renames: $renamed" }
            val records = mutableListOf<String>()
            for ((original, target) in declarations) {
                check(target.source.file == sourceFile(original)!!.fileEntry.name)
                check(target.source.start == original.startOffset && target.source.end == original.endOffset)
                check(target.parameters.map { it.symbol.name } == original.valueParameters.map { it.name.asString() })
                check(target.sourceName == original.name.asString().takeUnless { it == target.name })
                if (target.sourceName != null) check(target.name !in sourceNames)
                records += "declaration\t${File(target.source.file!!).name}\t${original.name}\t${target.name}\t${target.symbol.id}"
            }
            if (privateGroups) {
                check(renamed.count { it.sourceName == "mixed" } == 2)
                check(renamed.single { it.sourceName == "pick" }.source.file!!.endsWith("/PrivateRight.kt"))
                for ((original, target) in declarations) {
                    if (original.name.asString() in setOf("localOffset", "privateOrPublic"))
                        check(target.name == original.name.asString() && target.sourceName == null)
                    if (original.name.asString() == "pick" &&
                        org.jetbrains.kotlin.descriptors.DescriptorVisibilities.isPrivate(original.visibility))
                        check(target.name == "pick" && target.sourceName == null)
                    check(target.exported == !org.jetbrains.kotlin.descriptors.DescriptorVisibilities.isPrivate(original.visibility))
                }
            } else {
                val choose = originals.filter { it.name.asString() == "choose" }.sortedBy { sourceFile(it)!!.fileEntry.name }
                check(choose.size == 2 && choose[0].valueParameters[0].type != choose[1].valueParameters[0].type)
                check(declarations.getValue(choose[0]).symbol.type == declarations.getValue(choose[1]).symbol.type)
                check(declarations.getValue(choose[0]).name == "choose")
                check(declarations.getValue(choose[1]).name == "choose_2")
            }
            for ((file, call) in calls) {
                val declaration = declarations.getValue(call.symbol.owner)
                val target = nodes.filterIsInstance<EtsCall>().single { candidate ->
                    candidate.source.file == file && candidate.source.start == call.startOffset &&
                        candidate.source.end == call.endOffset && when (val callee = candidate.callee) {
                            is EtsReference -> callee.symbol.id == declaration.symbol.id
                            is EtsMember -> callee.symbolId == declaration.symbol.id
                            else -> false
                        }
                }
                when (val callee = target.callee) {
                    is EtsReference -> check(callee.symbol == declaration.symbol && !callee.symbol.external)
                    is EtsMember -> check(callee.name == declaration.name && callee.type == declaration.symbol.type)
                    else -> error("Missing canonical source callee")
                }
                check(target.type == backend.language.type(call.type))
                records += "call\t${target.source.file}:${call.startOffset}\t${declaration.symbol.id}\t${declaration.name}"
            }
            check(calls.isNotEmpty())
            File(work, "bindings.tsv").writeText(records.joinToString("\n"))
        }
        program
    }
    // Baseline must fail at the real module binding conflict before publishing files.
    val modules = emitEtsModules(program, StandardLibraryRuntime)
    check(!baseline) { "Baseline unexpectedly accepted split-file overload imports" }
    val flat = if (privateGroups) null else emitEtsProgram(program, StandardLibraryRuntime)
    val output = File(work, "modules")
    check(!output.exists() && output.mkdir())
    modules.forEach { (name, text) -> File(output, name).writeText(text) }
    if (flat != null) File(work, "Combined.ets").writeText(flat)
    println("PASS split-file source identities, two minimal renames, exact resolved calls, module and flat output")
}
