@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.tests.overloadbindings

import dev.ets.*
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*
import java.io.File

fun main(args: Array<String>) {
    val directory = File(args.first())
    check(directory.mkdirs())
    withKotlinFrontend(args.drop(1)) { frontend ->
        val sourceDeclarations = mutableListOf<IrSimpleFunction>()
        val sourceCalls = mutableListOf<Pair<String, IrCall>>()
        val overloadNames = setOf("choose", "select", "accept")
        frontend.module.files.forEach { file -> file.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
            override fun visitSimpleFunction(declaration: IrSimpleFunction) {
                if (declaration.name.asString() in overloadNames) sourceDeclarations.add(declaration)
                declaration.acceptChildrenVoid(this)
            }
            override fun visitCall(expression: IrCall) {
                if (expression.symbol.owner.name.asString() in overloadNames && sourceFile(expression.symbol.owner) != null)
                    sourceCalls.add(file.fileEntry.name to expression)
                expression.acceptChildrenVoid(this)
            }
        }) }
        check(sourceDeclarations.size == 6 && sourceCalls.size == 17) { "Unexpected fixture coverage: ${sourceDeclarations.size}/${sourceCalls.size}" }
        fun sourceId(declaration: IrSimpleFunction) =
            "function:${sourceFile(declaration)!!.fileEntry.name}:${declaration.startOffset}:${declaration.name.asString()}"
        val program = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())).lower(frontend.module)
        val targetFunctions = mutableListOf<EtsFunction>()
        val targetCalls = mutableListOf<EtsCall>()
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) {
            if (it is EtsFunction) targetFunctions.add(it)
            if (it is EtsCall) targetCalls.add(it)
        } } }
        val bindings = sourceDeclarations.associateWith { original -> targetFunctions.single { it.symbol.id == sourceId(original) } }
        bindings.forEach { (original, target) ->
            check((target.sourceName ?: target.name) == original.name.asString())
            check(target.source == SourceSpan(sourceFile(original)!!.fileEntry.name, original.startOffset, original.endOffset))
            check(target.symbol.name == target.name)
        }
        bindings.entries.groupBy { it.key.name.asString() }.values.forEach { group ->
            check(group.map { it.value.name }.distinct().size == 2)
            check(group.map { it.value.symbol.type }.distinct().size == 1) { "Numeric overloads must exercise identical ETS signatures" }
        }
        targetFunctions.filter { it.kind == EtsFunctionKind.FUNCTION && it.symbol.id !in bindings.values.map { it.symbol.id } }.forEach {
            check(it.sourceName == null || it.sourceName == it.name) { "Unnecessary public wrapper rename: ${it.name}" }
        }
        val callEvidence = sourceCalls.map { (file, original) ->
            val declaration = original.symbol.owner
            val expected = bindings.getValue(declaration)
            val span = SourceSpan(file, original.startOffset, original.endOffset)
            val matches = targetCalls.filter { it.source == span && when (val callee = it.callee) {
                is EtsReference -> callee.symbol.id in bindings.values.map { value -> value.symbol.id }
                is EtsMember -> callee.symbolId in bindings.values.map { value -> value.symbol.id }
                else -> false
            } }
            check(matches.size == 1) { "Overload call lost/duplicated at $span: $matches" }
            when (val callee = matches.single().callee) {
                is EtsReference -> check(callee.symbol == expected.symbol)
                is EtsMember -> check(callee.symbolId == expected.symbol.id && callee.name == expected.name && callee.type == expected.symbol.type)
                else -> error("Not a resolved source overload")
            }
            listOf(file, original.startOffset, original.endOffset, declaration.valueParameters.first().type.render(),
                expected.symbol.id, expected.name).joinToString("\t")
        }
        val visits = mutableListOf<EtsProgram>()
        val modules = emitEtsModules(program, EtsRuntimeSupport { part ->
            visits.add(part)
            StandardLibraryRuntime.declarations(part)
        })
        check(visits.size == 5 && visits.map { it.files.single().sourcePath }.toSet().size == 5)
        check(visits.all { it.files.single() in program.files })
        frontend.module.files.reverse()
        try {
            val reversed = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())).lower(frontend.module)
            check(emitEtsModules(reversed, StandardLibraryRuntime) == modules) { "Overload bindings depend on file visitation order" }
        } finally { frontend.module.files.reverse() }
        File(directory, "bindings.tsv").writeText(bindings.map { (original, target) -> listOf(
            File(target.source.file!!).nameWithoutExtension, original.name.asString(),
            original.valueParameters.first().type.classOrNull!!.owner.fqNameWhenAvailable!!.asString(), target.name,
            target.symbol.id).joinToString("\t") }.sorted().joinToString("\n") + "\n")
        File(directory, "calls.tsv").writeText(callEvidence.sorted().joinToString("\n") + "\n")
        val emitted = File(directory, "modules")
        check(emitted.mkdir())
        modules.forEach { (name, text) -> File(emitted, name).writeText(text) }
        println("PASS six source overload identities and 17 actual resolved calls through callbacks; numeric signatures erase equally")
        println("PASS preserved source IDs/spans, unique wrapper names, five provider visits and file-order-stable output")
    }
}
