@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.declarations.IrProperty

fun main(args: Array<String>) {
    val extra = File(args[0]).readLines().filter(String::isNotBlank)
    val classpath = File(args[1]).readLines().filter(String::isNotBlank).joinToString(File.pathSeparator)
    val sources = File(args[2]).readLines().filter(String::isNotBlank)
    withKotlinFrontend(extra + listOf("-no-stdlib", "-no-reflect", "-classpath", classpath) + sources) { session ->
        val serializer = session.module.files.flatMap { it.declarations }.filterIsInstance<IrClass>()
            .single { it.name.asString() == "ModelSerializer" }
        val descriptor = serializer.declarations.filterIsInstance<IrProperty>()
            .single { it.name.asString() == "descriptor" }
        check(descriptor.getter?.body != null) { "Serialization plugin did not generate descriptor getter body" }
        println("PASS official frontend and serialization-generated descriptor IR")
    }
}
