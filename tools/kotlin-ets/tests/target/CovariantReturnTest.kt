package dev.ets

fun checkCovariantReturnContract() {
    fun span(start: Int) = SourceSpan("CovariantReturn.kt", start, start + 1)
    val animal = EtsClass("Animal", emptyList(), span(1), kind = EtsClassKind.INTERFACE)
    val animalType = animal.symbol.type as EtsNamedType
    val dog = EtsClass("Dog", emptyList(), span(2), kind = EtsClassKind.INTERFACE, interfaces = listOf(animalType))
    val dogType = dog.symbol.type as EtsNamedType
    val unrelated = EtsClass("Unrelated", emptyList(), span(3), kind = EtsClassKind.INTERFACE)
    val argument = EtsParameter(EtsSymbol("seed", "seed", EtsTypes.NUMBER, span(4)))
    val required = EtsFunction("make", listOf(argument), animalType, emptyList(), span(5),
        kind = EtsFunctionKind.METHOD, abstract = true)
    val factory = EtsClass("Factory", listOf(required), span(6), kind = EtsClassKind.INTERFACE)
    val implementation = required.copy(returnType = dogType, source = span(7), overrides = listOf(required.symbol.id))
    fun program(value: EtsFunction = implementation, requirement: EtsFunction = required): EtsProgram =
        EtsProgram(listOf(EtsFile("CovariantReturn.kt", listOf(animal, dog, unrelated,
            factory.copy(members = listOf(requirement)), EtsClass("Impl", listOf(value), span(8), abstract = true,
                interfaces = listOf(factory.symbol.type as EtsNamedType))))))
    EtsValidator().validate(program())
    EtsValidator().validate(program(requirement = required.copy(returnType = EtsNullableType(animalType))))
    EtsValidator().validate(program(implementation.copy(returnType = EtsNullableType(dogType)),
        required.copy(returnType = EtsNullableType(animalType))))
    fun reject(label: String, value: EtsFunction, requirement: EtsFunction = required) {
        val failure = runCatching { EtsValidator().validate(program(value, requirement)) }.exceptionOrNull()
        check(failure is InvalidTarget && failure.source.file == "CovariantReturn.kt") { "$label: $failure" }
    }
    reject("Unrelated return", implementation.copy(returnType = unrelated.symbol.type))
    reject("Widened return", implementation.copy(returnType = animalType), required.copy(returnType = dogType))
    reject("Nullable return cannot satisfy nonnull", implementation.copy(returnType = EtsNullableType(dogType)))
    reject("Void cannot satisfy object", implementation.copy(returnType = EtsTypes.VOID))
    reject("Wrong entry identity", implementation.copy(overrides = listOf("wrong")))
    reject("Parameter types remain invariant", implementation.copy(parameters = listOf(
        argument.copy(symbol = argument.symbol.copy(type = EtsTypes.STRING)))))
    val t = EtsTypeParameter("Factory.make:T", "T", animalType)
    val r = EtsTypeParameter("Impl.make:R", "R", animalType)
    val genericRequired = required.copy(typeParameters = listOf(t), parameters = listOf(
        argument.copy(symbol = argument.symbol.copy(type = EtsTypeParameterType(t.id, t.name)))))
    val genericImplementation = implementation.copy(typeParameters = listOf(r), returnType = EtsTypeParameterType(r.id, r.name),
        parameters = listOf(argument.copy(symbol = argument.symbol.copy(type = EtsTypeParameterType(r.id, r.name)))))
    EtsValidator().validate(program(genericImplementation, genericRequired))
    reject("Method bound cannot be narrowed", genericImplementation.copy(typeParameters = listOf(r.copy(upperBound = dogType))), genericRequired)
    reject("Method bound cannot be lost", genericImplementation.copy(typeParameters = listOf(r.copy(upperBound = null))), genericRequired)
    reject("Generic return must hold for every instantiation", genericImplementation.copy(returnType = dogType),
        genericRequired.copy(returnType = EtsTypeParameterType(t.id, t.name)))
    println("PASS covariant target returns, nullable and rebound method bounds, nine invalid contracts")
}
