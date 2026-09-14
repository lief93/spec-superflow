@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.variance

import dev.ets.*
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.types.Variance

fun main(args: Array<String>) {
    withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(1)) { frontend ->
        val module = frontend.module
        val sources = module.files.flatMap { it.declarations }.filterIsInstance<IrClass>()
        val program = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules()), frontend.types).lower(module)
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
        val constraints = sources.filter { it.origin === ETS_BOUND_CONSTRAINT }
        check(constraints.size == 12)
        for (source in constraints) {
            val target = targets.single { it.name == source.name.asString() }
            check(target.constraint)
            check(target.interfaces.size + (if (target.baseClass != null) 1 else 0) == source.superTypes.size)
            check(source.superTypes.size == 2)
            if (target.kind == EtsClassKind.INTERFACE) check(target.members.isEmpty())
            else {
                check(target.abstract && target.members.all { it is EtsFunction && it.abstract })
                val abstractFunctions = source.declarations.flatMap { declaration -> when (declaration) {
                    is IrSimpleFunction -> listOf(declaration)
                    is IrProperty -> listOfNotNull(declaration.getter, declaration.setter)
                    else -> emptyList()
                } }.filter { it.modality == org.jetbrains.kotlin.descriptors.Modality.ABSTRACT }
                check(abstractFunctions.isNotEmpty() && abstractFunctions.size == target.members.size)
                check(abstractFunctions.all { it.isFakeOverride && it.overriddenSymbols.isNotEmpty() })
                for ((original, emitted) in abstractFunctions.zip(target.members)) {
                    check(emitted.source == target.source) {
                        "Generated constraint ${source.name}.${original.name} must point to its owning bound: ${emitted.source}; expected ${target.source}"
                    }
                    val contracts = original.collectRealOverrides()
                    check(contracts.isNotEmpty() && contracts.all { !it.isFakeOverride && sourceFile(it) != null })
                    check(contracts.all { it.startOffset >= 0 && it.endOffset > it.startOffset })
                }
            }
        }
        check(targets.filter { it.constraint }.size == constraints.size)
        val functions = program.files.flatMap { it.declarations }.filterIsInstance<EtsFunction>()
        for (name in listOf("readProjected", "writeProjected", "emptyProjected", "project", "readBounded", "readNested")) {
            val original = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>().single { it.name.asString() == name }
            val target = functions.single { it.name == name }
            check(target.parameters.map { it.symbol.name } == original.valueParameters.map { it.name.asString() })
            check(target.source.file == original.file.fileEntry.name)
        }
        fun capture(name: String) = ((functions.single { it.name == name }.parameters.first().symbol.type as EtsNamedType)
            .arguments.single() as EtsCapturedType)
        val valueType = targets.single { it.name == "Value" }.symbol.type
        val specificType = targets.single { it.name == "Specific" }.symbol.type
        check(capture("readProjected") == EtsCapturedType(valueType, EtsTypes.NEVER))
        check(capture("writeProjected") == EtsCapturedType(EtsNullableType(EtsTypes.OBJECT), specificType))
        check(capture("emptyProjected") == EtsCapturedType(EtsNullableType(EtsTypes.OBJECT), EtsTypes.NEVER))
        check(capture("readBounded") == EtsCapturedType(valueType, specificType))
        val project = functions.single { it.name == "project" }
        check(((project.body.single() as EtsReturn).value as EtsReference).symbol == project.parameters.single().symbol)
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
        println("PASS official IR variance/names/ownership, twelve named constraints, fake overrides, four retained capture intervals, identity return and erased-metadata refusal")
    }
}
