@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.config.KotlinCompilerVersion
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    check(KotlinCompilerVersion.VERSION == "2.1.20")
    val source = File(args[0])
    val work = File(args[2])
    val program = withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[1], source.path)) { module ->
        File(work, "actual.ir").writeText(module.dump())
        val originals = mutableListOf<IrSimpleFunction>()
        val calls = mutableListOf<IrCall>()
        val sourceNames = mutableSetOf<String>()
        module.acceptVoid(object : IrElementVisitorVoid {
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
                val owner = expression.symbol.owner
                if (sourceFile(owner)?.fileEntry?.name == source.path && owner.correspondingPropertySymbol == null &&
                    (owner.parent is IrFile || owner.parent is IrClass)) calls += expression
                super.visitCall(expression)
            }
        })
        val backend = EtsBackend(DiagnosticSink(source.path), listOf(StandardLibraryRules()))
        val program = backend.lower(module)
        val nodes = mutableListOf<EtsNode>()
        program.files.forEach { file -> file.declarations.forEach { walkEts(it, nodes::add) } }
        val targets = nodes.filterIsInstance<EtsFunction>()
        fun id(function: IrSimpleFunction): String = etsFunctionSymbol(function.name.asString(), emptyList(), EtsTypes.VOID,
            SourceSpan(sourceFile(function)!!.fileEntry.name, function.startOffset, function.endOffset)).id
        val declarations = originals.associateWith { original -> targets.single { it.symbol.id == id(original) } }
        val groups = originals.groupBy { it.parent to it.name }.values
        val renamed = targets.filter { it.sourceName != null }
        check(renamed.size == groups.sumOf { it.size - 1 })
        val records = mutableListOf<String>()
        for (group in groups) {
            val ordered = group.sortedBy { it.startOffset }
            check(declarations.getValue(ordered.first()).name == ordered.first().name.asString())
            for (original in ordered) {
                val target = declarations.getValue(original)
                check(target.sourceName == original.name.asString().takeUnless { it == target.name })
                check(target.parameters.map { it.symbol.name } == original.valueParameters.map { it.name.asString() })
                check(target.typeParameters.map { it.name } == original.typeParameters.map { it.name.asString() })
                if (target.sourceName != null) check(target.name !in sourceNames)
                records += "${target.symbol.id} -> ${target.name}; sourceName=${target.sourceName}; ${target.symbol.type}"
            }
        }
        for (call in calls) {
            val target = nodes.filterIsInstance<EtsCall>().single { it.source.start == call.startOffset && it.source.end == call.endOffset &&
                when (val callee = it.callee) {
                    is EtsReference -> callee.symbol.id == id(call.symbol.owner)
                    is EtsMember -> callee.symbolId == id(call.symbol.owner)
                    else -> false
                }
            }
            val declaration = declarations.getValue(call.symbol.owner)
            when (val callee = target.callee) {
                is EtsReference -> check(callee.symbol.name == declaration.name && !callee.symbol.external)
                is EtsMember -> check(callee.name == declaration.name && callee.receiver.type == backend.language.type(call.dispatchReceiver!!.type))
                else -> error("Expected bound source overload call")
            }
            check(target.type == backend.language.type(call.type))
            records += "call ${call.startOffset} -> ${declaration.symbol.id} / ${declaration.name}"
        }
        check(calls.isNotEmpty() && renamed.isNotEmpty())
        File(work, "bindings.txt").writeText(records.joinToString("\n"))
        EtsValidator().validate(program)
        println("PASS ${originals.size} declarations, ${renamed.size} minimal renamed bodies and ${calls.size} source-bound IR calls; canonical IDs, names, binders and collision avoidance")
        program
    }
    EtsValidator().validate(program)
    File(work, "Overloads.ets").writeText(emitEtsProgram(program, StandardLibraryRuntime))
}
