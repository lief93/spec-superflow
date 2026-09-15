package dev.ets

import java.io.File
import java.util.Locale

fun emitEtsProgram(program: EtsProgram, runtime: EtsRuntimeSupport): String {
    EtsValidator().validate(program)
    val support = runtime.declarations(program)
    return EtsPrinter().program(program, support)
}

/** Assemble files by declaration identity before printing; never infer imports from text. */
fun emitEtsModules(program: EtsProgram, runtime: EtsRuntimeSupport): Map<String, String> {
    EtsValidator().validate(program, perFileNames = true)
    val names = linkedMapOf<String, String>()
    val outputOwners = mutableMapOf<String, String>()
    for (file in program.files) {
        val source = file.declarations.firstOrNull()?.source ?: SourceSpan(file.sourcePath, -1, -1)
        if (file.sourcePath in names) throw InvalidTarget(source,
            "Duplicate source file in target program: ${file.sourcePath}")
        val name = File(file.sourcePath).nameWithoutExtension + ".ets"
        val previous = outputOwners.putIfAbsent(name.lowercase(Locale.ROOT), file.sourcePath)
        if (previous != null) throw InvalidTarget(source,
            "Source filenames collide in flat ETS output: $previous and ${file.sourcePath} map to $name; use distinct source basenames")
        names[file.sourcePath] = name
    }
    data class Owner(val path: String, val symbol: EtsSymbol, val exported: Boolean)
    val owners = program.files.flatMap { file -> file.declarations.map { declaration ->
        val symbol = when (declaration) {
            is EtsFunction -> declaration.symbol
            is EtsClass -> declaration.symbol
            is EtsGlobal -> declaration.symbol
        }
        val exported = when (declaration) {
            is EtsFunction -> declaration.exported
            is EtsClass -> declaration.exported
            is EtsGlobal -> declaration.exported
        }
        symbol.id to Owner(file.sourcePath, symbol, exported)
    } }.toMap()
    val plans = program.files.sortedBy { names.getValue(it.sourcePath) }.map { file ->
        val dependencies = linkedMapOf<String, SourceSpan>()
        fun typeReferences(type: EtsType, source: SourceSpan) {
            when (type) {
                is EtsNamedType -> {
                    if (!type.external) type.symbolId?.let { dependencies.putIfAbsent(it, source) }
                    type.arguments.forEach { typeReferences(it, source) }
                }
                is EtsFunctionType -> {
                    type.parameters.forEach { typeReferences(it, source) }
                    typeReferences(type.result, source)
                    type.typeParameters.forEach { it.upperBound?.let { bound -> typeReferences(bound, source) } }
                }
                is EtsNullableType -> typeReferences(type.inner, source)
                is EtsCapturedType -> { typeReferences(type.readType, source); typeReferences(type.writeType, source) }
                is EtsTupleType -> type.elements.forEach { typeReferences(it, source) }
                is EtsTypeParameterType -> Unit
                is EtsRecordType -> type.fields.values.forEach { typeReferences(it, source) }
            }
        }
        file.declarations.forEach { declaration -> walkEts(declaration) { node ->
            if (node is EtsReference && !node.symbol.external && node.symbol.id in owners)
                dependencies.putIfAbsent(node.symbol.id, node.source)
            if (node is EtsExpression) typeReferences(node.type, node.source)
            when (node) {
                is EtsVariable -> typeReferences(node.symbol.type, node.source)
                is EtsGlobal -> typeReferences(node.symbol.type, node.source)
                is EtsField -> typeReferences(node.symbol.type, node.source)
                is EtsFunction -> typeReferences(node.symbol.type, node.source)
                is EtsClass -> {
                    node.typeParameters.forEach { it.upperBound?.let { bound -> typeReferences(bound, node.source) } }
                    node.baseClass?.let { typeReferences(it, node.source) }
                    node.interfaces.forEach { typeReferences(it, node.source) }
                }
                is EtsSuperConstructorCall -> typeReferences(node.baseClass, node.source)
                is EtsCall -> node.typeArguments.forEach { typeReferences(it, node.source) }
                else -> Unit
            }
        } }
        val occupied = owners.values.filter { it.path == file.sourcePath }.map { it.symbol.name }.toMutableSet()
        occupied.addAll(program.imports.map { it.alias ?: it.name })
        val imports = program.imports + dependencies.mapNotNull { (id, source) ->
            val owner = owners.getValue(id)
            if (owner.path == file.sourcePath) null else {
                if (!owner.exported) throw InvalidTarget(source,
                    "Referenced target declaration is not exported: ${owner.symbol.name} from ${owner.path}")
                if (!occupied.add(owner.symbol.name)) throw InvalidTarget(source,
                    "Conflicting module binding: ${owner.symbol.name} from ${owner.path}")
                EtsImport("./" + names.getValue(owner.path).removeSuffix(".ets"), owner.symbol.name)
            }
        }.sortedWith(compareBy({ it.module }, { it.name }))
        file to imports
    }
    val printer = EtsPrinter()
    return plans.associate { (file, imports) ->
        val support = runtime.declarations(EtsProgram(listOf(file), imports))
        val declarations = file.declarations.map { declaration -> when (declaration) {
            is EtsFunction -> printer.function(declaration)
            is EtsClass -> printer.clazz(declaration)
            is EtsGlobal -> printer.global(declaration)
        }.joinToString("\n") }
        val header = printer.program(EtsProgram(emptyList(), imports)).trim()
        names.getValue(file.sourcePath) to
            (listOf(header, support.joinToString("\n")) + declarations).filter { it.isNotBlank() }
                .joinToString("\n\n", postfix = "\n")
    }
}
