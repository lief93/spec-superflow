@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.virtualoverloads

import dev.ets.*
import java.io.File
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(2)) { module ->
        val methods = module.files.flatMap { it.declarations }.filterIsInstance<IrClass>()
            .flatMap { it.declarations.filterIsInstance<IrSimpleFunction>() }
            .filter { !it.isFakeOverride && it.correspondingPropertySymbol == null }
        val program = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())).lower(module)
        val nodes = mutableListOf<EtsNode>()
        program.files.forEach { it.declarations.forEach { node -> walkEts(node, nodes::add) } }
        val targets = nodes.filterIsInstance<EtsFunction>()
        fun id(function: IrSimpleFunction) = etsFunctionSymbol(function.name.asString(), emptyList(), EtsTypes.VOID,
            SourceSpan(function.file.fileEntry.name, function.startOffset, function.endOffset)).id
        val declarations = methods.associateWith { original -> targets.single { it.symbol.id == id(original) } }
        var overrides = 0
        for ((source, target) in declarations) {
            check(target.parameters.map { it.symbol.name } == source.valueParameters.map { it.name.asString() })
            check(target.sourceName == source.name.asString().takeUnless { it == target.name })
            for (parent in source.allOverridden().filter { it in declarations }) {
                overrides++
                check(target.name == declarations.getValue(parent).name)
            }
            val immediate = source.overriddenSymbols.flatMap { it.owner.collectRealOverrides() }.filter { it in declarations }
            check(target.overrides.toSet() == immediate.map(::id).toSet())
        }
        check(overrides >= 15)
        val unrelated = methods.single { it.parentAsClass.name.asString() == "Unrelated" && it.name.asString() == "choose" }
        check(declarations.getValue(unrelated).name == "choose")
        val reserved = methods.single { it.name.asString() == "choose_0" }
        check(declarations.getValue(reserved).name == "choose_0")
        check(declarations.filterKeys { it.name.asString() == "choose" }.values.none { it.name == "choose_0" })
        var calls = 0
        module.acceptVoid(object : IrElementVisitorVoid {
            private var currentFile: IrFile? = null
            override fun visitFile(declaration: IrFile) {
                val previous = currentFile
                currentFile = declaration
                super.visitFile(declaration)
                currentFile = previous
            }
            override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
            override fun visitCall(expression: IrCall) {
                val resolved = expression.symbol.owner
                val owner = if (resolved.isFakeOverride) resolved.collectRealOverrides().singleOrNull() else resolved
                if (owner in declarations) {
                    val source = SourceSpan(checkNotNull(currentFile).fileEntry.name, expression.startOffset, expression.endOffset)
                    val target = declarations.getValue(owner!!)
                    val call = nodes.filterIsInstance<EtsCall>().singleOrNull { it.source == source &&
                        (it.callee as? EtsMember)?.symbolId == target.symbol.id }
                    check(call != null) { "Missing typed call for ${owner.name} at $source" }
                    check((call.callee as EtsMember).name == target.name)
                    calls++
                }
                super.visitCall(expression)
            }
        })
        check(calls >= 20)
        File(args[1], "lowered.ir").writeText(module.dump())
        println("PASS $overrides official override edges, $calls exact typed calls, source names/parameters and reserved spelling")
    }
}
