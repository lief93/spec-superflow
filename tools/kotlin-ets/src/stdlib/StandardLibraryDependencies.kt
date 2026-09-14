package dev.ets

object StandardLibraryRuntime : EtsRuntimeSupport {
    override fun declarations(program: EtsProgram) = standardLibrarySupportLines(program)
}

/** Collect from the complete emitted tree, not source IR or printed target text. */
fun standardLibrarySupportLines(program: EtsProgram): List<String> {
    val collector = StandardLibraryDependencies()
    program.files.forEach { file -> file.declarations.forEach(collector::visit) }
    return standardLibrarySupportLines(collector.symbols)
}

private class StandardLibraryDependencies {
    val symbols = mutableSetOf<String>()

    fun visit(node: EtsNode) {
        walkEts(node) { child ->
            if (child is EtsExpression) type(child.type)
            when (child) {
                is EtsVariable -> type(child.symbol.type)
                is EtsField -> type(child.symbol.type)
                is EtsFunction -> type(child.symbol.type)
                is EtsClass -> {
                    child.typeParameters.forEach { it.upperBound?.let(::type) }
                    child.baseClass?.let(::type)
                    child.interfaces.forEach(::type)
                }
                is EtsSuperConstructorCall -> type(child.baseClass)
                is EtsCall -> child.typeArguments.forEach(::type)
                is EtsUiForEach -> type(child.item.symbol.type)
                else -> Unit
            }
            if (child is EtsReference) {
                val symbol = child.symbol
                if (symbol.external && symbol.id.startsWith("stdlib:")) {
                    require(symbol.name == symbol.id.removePrefix("stdlib:")) {
                        "Mismatched standard library runtime symbol: ${symbol.id} / ${symbol.name}"
                    }
                    if (symbol.id != "stdlib:Math") symbols.add(symbol.id)
                }
            }
        }
    }

    private fun type(value: EtsType) {
        when (value) {
            is EtsNamedType -> {
                val id = value.symbolId
                if (id?.startsWith("stdlib:") == true) {
                    val arity = when (id) {
                        "stdlib:__etsIterator" -> 1
                        "stdlib:__etsIntProgression" -> 0
                        else -> error("Unknown standard library runtime type: $id")
                    }
                    require(value.external && value.name == id.removePrefix("stdlib:") && value.arguments.size == arity) {
                        "Malformed standard library runtime type: $value"
                    }
                    require(value.arguments.none { it == EtsTypes.VOID || it == EtsTypes.UNDEFINED }) {
                        "Unsupported standard library runtime type argument: $value"
                    }
                    symbols.add(id)
                }
                value.arguments.forEach(::type)
            }
            is EtsRecordType -> value.fields.values.forEach(::type)
            is EtsFunctionType -> {
                value.parameters.forEach(::type)
                type(value.result)
                value.typeParameters.forEach { it.upperBound?.let(::type) }
            }
            is EtsNullableType -> type(value.inner)
            is EtsCapturedType -> { type(value.readType); type(value.writeType) }
            is EtsTupleType -> value.elements.forEach(::type)
            is EtsTypeParameterType -> Unit
        }
    }
}
