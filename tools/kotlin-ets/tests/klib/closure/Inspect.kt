@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.klibtest

import dev.ets.dependency.klib.KlibLoader
import dev.ets.dependency.klib.KlibModuleSelection
import java.io.File
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrFunctionSymbol
import org.jetbrains.kotlin.ir.symbols.IrSymbol
import org.jetbrains.kotlin.ir.util.fileOrNull
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid
import org.jetbrains.kotlin.ir.visitors.acceptVoid

private data class Identity(
    val signature: String,
    val fqName: String,
    val ownerModule: String,
    val file: String,
    val start: Int,
    val end: Int,
    val inline: Boolean,
    val external: Boolean,
    val origin: String,
    val hasBody: Boolean,
)

private fun identity(function: IrFunction): Identity {
    val file = function.fileOrNull
    return Identity(
        signature = function.symbol.signature?.toString() ?: "unbound:${System.identityHashCode(function.symbol)}",
        fqName = function.fqNameWhenAvailable?.asString() ?: function.name.asString(),
        ownerModule = file?.module?.name?.asString() ?: "<no-file>",
        file = file?.fileEntry?.name ?: "<no-file>",
        start = function.startOffset,
        end = function.endOffset,
        inline = function.isInline,
        external = function.isExternal,
        origin = function.origin.toString(),
        hasBody = function.body != null,
    )
}

private val jsPackages = setOf("kotlin.js", "kotlin.js.internal")

private fun classify(function: IrFunction, translated: Set<IrModuleFragment>): String {
    val file = function.fileOrNull
    val packageFq = file?.packageFqName?.asString() ?: ""
    val origin = function.origin.toString()
    return when {
        function.isExternal -> "UNSUPPORTED_EXTERNAL"
        packageFq in jsPackages || (origin.contains("JS", ignoreCase = true) && origin.contains("INTRINSIC")) -> "JS_SPECIFIC"
        function.body == null -> "MISSING_BODY"
        file?.module in translated -> "COMMON_IR_BODY"
        function.body != null -> "COMMON_IR_BODY"
        else -> "MISSING_BODY"
    }
}

private fun primitiveHint(function: IrFunction): String? {
    if (function.body != null) return null
    val fq = function.fqNameWhenAvailable?.asString() ?: return null
    val constructors = function is IrConstructor && run {
        val parent = function.parent as? IrClass
        parent?.fqNameWhenAvailable?.asString() == "kotlin.collections.ArrayList" ||
            parent?.name?.asString() == "ArrayList"
    }
    val primitives = setOf(
        "kotlin.collections.Iterable.iterator",
        "kotlin.collections.Iterator.hasNext",
        "kotlin.collections.Iterator.next",
        "kotlin.collections.MutableCollection.add",
        "kotlin.collections.Collection.isEmpty",
        "kotlin.collections.List.isEmpty",
        "kotlin.collections.List.get",
        "kotlin.collections.List.<get-size>",
        "kotlin.collections.Collection.<get-size>",
        "kotlin.Int.rem",
        "kotlin.Int.plus",
        "kotlin.Int.toString",
    )
    return if (fq in primitives || constructors) "TARGET_NEUTRAL_PRIMITIVE" else null
}

fun main(args: Array<String>) {
    val output = File(args[0])
    val main = File(args[1])
    val stdlib = File(args[2])
    val selection = KlibModuleSelection(main = main, translated = listOf(main), libraries = listOf(stdlib))
    KlibLoader.withKlibModules(selection, moduleName = "ets-klib-closure") { session ->
        val modules = session.linkedModules()
        val translated = modules.toSet()
        val consumer = modules.single()
        val entries = consumer.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
            .filter { it.name.asString() in setOf("filterEven", "mapPlusOne", "firstOrNullValue") }
        check(entries.size == 3)
        val report = StringBuilder()
        fun writeln(line: String = "") { report.appendLine(line) }
        writeln("# KLIB body-closure spike")
        writeln()
        writeln("Official linked modules: ${session.allDependencies.map { it.name.asString() }}")
        writeln("Translated: ${modules.map { it.name.asString() }}")
        writeln("Identity is IrFunctionSymbol / IdSignature, not FQName matching.")
        writeln()
        for (entry in entries) {
            val seen = LinkedHashSet<IrFunctionSymbol>()
            val queue = ArrayDeque<IrFunction>()
            queue.add(entry)
            seen.add(entry.symbol)
            writeln("## ${entry.name.asString()}")
            writeln()
            writeln("- entry signature: `${entry.symbol.signature}`")
            writeln("- entry fqName: `${entry.fqNameWhenAvailable}`")
            writeln()
            writeln("| kind | signature | fqName | module | body | inline | origin |")
            writeln("| --- | --- | --- | --- | --- | --- | --- |")
            val rows = mutableListOf<String>()
            while (queue.isNotEmpty()) {
                val function = queue.removeFirst()
                val kind = primitiveHint(function) ?: classify(function, translated)
                val id = identity(function)
                rows += "| $kind | `${id.signature}` | `${id.fqName}` | `${id.ownerModule}` | ${id.hasBody} | ${id.inline} | `${id.origin}` |"
                val body = function.body ?: continue
                body.acceptVoid(object : IrElementVisitorVoid {
                    override fun visitElement(element: IrElement) {
                        val symbol: IrSymbol? = when (element) {
                            is IrFunctionAccessExpression -> element.symbol
                            is IrFunctionReference -> element.symbol
                            else -> null
                        }
                        val callee = (symbol as? IrFunctionSymbol)?.takeIf { it.isBound }?.owner
                        if (callee != null && seen.add(callee.symbol)) queue.add(callee)
                        element.acceptChildrenVoid(this)
                    }
                })
            }
            rows.forEach { writeln(it) }
            writeln()
        }
        File(output, "closure.md").writeText(report.toString())
        println("PASS body-closure inspection wrote ${File(output, "closure.md")}")
    }
}
