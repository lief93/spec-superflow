@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.variance

import dev.ets.*
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.types.Variance

fun main(args: Array<String>) {
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(1)) { module ->
        val sources = module.files.flatMap { it.declarations }.filterIsInstance<IrClass>()
        val program = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())).lower(module)
        val targets = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>()
        for (source in sources) {
            val target = targets.single { it.name == source.name.asString() }
            check(target.source.file == source.file.fileEntry.name)
            check(target.typeParameters.map { it.name } == source.typeParameters.map { it.name.asString() })
            check(target.typeParameters.map { it.variance } == source.typeParameters.map {
                when (it.variance) { Variance.INVARIANT -> EtsVariance.INVARIANT; Variance.IN_VARIANCE -> EtsVariance.IN; Variance.OUT_VARIANCE -> EtsVariance.OUT }
            })
        }
        EtsValidator().validate(program, perFileNames = true)
        val functions = program.files.flatMap { it.declarations }.filterIsInstance<EtsFunction>()
        val bound = targets.single { it.name == "SpecificSource" }.symbol.type
        for (name in listOf("broadFirst", "narrowFirst")) {
            val function = functions.single { it.name == name }
            check(function.typeParameters.single().name == "T" && function.typeParameters.single().upperBound == bound)
            check(function.parameters.single().symbol.name == "source")
        }
        check(targets.single { it.name == "BoundedBox" }.typeParameters.single().upperBound == bound)
        val producer = targets.single { it.name == "Producer" }
        val corrupted = program.copy(files = program.files.map { file -> file.copy(declarations = file.declarations.map {
            if (it === producer) producer.copy(typeParameters = producer.typeParameters.map { p -> p.copy(variance = EtsVariance.INVARIANT) }) else it
        }) })
        check(runCatching { EtsValidator().validate(corrupted, perFileNames = true) }.exceptionOrNull() is InvalidTarget)
        println("PASS official IR declaration variance/names/ownership, canonical redundant bounds and erased-metadata refusal")
    }
}
