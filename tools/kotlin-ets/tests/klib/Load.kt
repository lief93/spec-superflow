@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.klibtest

import dev.ets.*
import dev.ets.dependency.klib.KlibLoader
import dev.ets.dependency.klib.KlibModuleSelection
import java.io.File
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.util.dump
import org.jetbrains.kotlin.ir.util.file
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    val output = File(args[0])
    val main = File(args[1])
    val stdlib = File(args[2])
    val translated = args.drop(3).map(::File)
    val selection = KlibModuleSelection(
        main = main,
        translated = listOf(main) + translated,
        libraries = listOf(stdlib),
    )
    KlibLoader.withKlibModules(selection) { session ->
        val modules = session.linkedModules()
        val functions = modules.flatMap { it.files }.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
        check(functions.map { it.name.asString() }.toSet() == setOf("scenario", "adjusted", "buttonLabel", "echo", "offset"))
        functions.forEach { function ->
            check(function.body != null) { "Signature without body: ${function.name}" }
            check(function.file.module in modules)
            check(!File(function.file.fileEntry.name).exists()) { "Producer source still exists" }
            check(function.startOffset >= 0 && function.endOffset > function.startOffset)
            function.acceptChildrenVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) {
                    if (element is IrCall && element.symbol.owner.fqNameWhenAvailable?.asString()?.startsWith("klib") == true) {
                        check(functions.any { it === element.symbol.owner }) { "Call and loaded declaration identities differ" }
                    }
                    element.acceptChildrenVoid(this)
                }
            })
        }
        File(output, "loaded.ir").writeText(modules.joinToString("\n") { it.dump() })
        File(output, "bodies.txt").writeText(functions.joinToString("\n") {
            "${it.fqNameWhenAvailable}: ${it.file.fileEntry.name}:${it.startOffset}..${it.endOffset}; body=true"
        })
        val backend = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules()))
        val emitted = emitEtsModules(backend.lower(modules), StandardLibraryRuntime)
        val reversed = emitEtsModules(EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules()))
            .lower(modules.reversed()), StandardLibraryRuntime)
        check(emitted == reversed) { "Module input order changed ETS output" }
        functions.forEach { check(it.file.module in modules) { "Lowering changed IR ownership" } }
        emitted.forEach { (name, code) -> File(output, name).writeText(code) }
        println("PASS official KLIB loader: three modules, five real bodies, canonical transitive call symbols")
    }
}
