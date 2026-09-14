package dev.ets

fun checkCovariantPropertyContract() {
    fun at(offset: Int) = SourceSpan("CovariantProperty.kt", offset, offset + 1)
    val animal = EtsClass("Animal", emptyList(), at(1), kind = EtsClassKind.INTERFACE)
    val animalType = animal.symbol.type as EtsNamedType
    val dog = EtsClass("Dog", emptyList(), at(2), kind = EtsClassKind.INTERFACE, interfaces = listOf(animalType))
    val dogType = dog.symbol.type as EtsNamedType
    val unrelated = EtsClass("Unrelated", emptyList(), at(3), kind = EtsClassKind.INTERFACE)
    val field = EtsField(EtsSymbol("view:value", "value", animalType, at(4)), readonly = true)
    val view = EtsClass("View", listOf(field), at(5), kind = EtsClassKind.INTERFACE)
    val getter = EtsFunction("value", emptyList(), animalType, emptyList(), at(6), kind = EtsFunctionKind.GETTER, abstract = true)
    val setter = EtsFunction("value", listOf(EtsParameter(EtsSymbol("next", "next", animalType, at(7)))), EtsTypes.VOID,
        emptyList(), at(7), kind = EtsFunctionKind.SETTER, abstract = true)
    val implementation = getter.copy(source = at(8), returnType = dogType)
    fun validate(vararg values: EtsClass) = EtsValidator().validate(EtsProgram(listOf(EtsFile("CovariantProperty.kt",
        listOf(animal, dog, unrelated) + values))))
    val computed = EtsClass("Computed", listOf(implementation), at(9), abstract = true, interfaces = listOf(view.symbol.type as EtsNamedType))
    validate(view, computed)
    val narrowed = EtsClass("Narrowed", listOf(field.copy(symbol = field.symbol.copy(id = "narrowed:value", type = dogType))),
        at(10), kind = EtsClassKind.INTERFACE, interfaces = listOf(view.symbol.type as EtsNamedType))
    validate(view, narrowed)
    val mutable = computed.copy(members = listOf(field.copy(symbol = field.symbol.copy(id = "mutable:value", type = dogType), readonly = false)))
    validate(view, mutable)
    val base = EtsClass("Base", listOf(getter), at(11), abstract = true)
    val override = implementation.copy(overrides = listOf(getter.symbol.id))
    val child = EtsClass("Child", listOf(override), at(12), abstract = true, baseClass = base.symbol.type as EtsNamedType)
    validate(base, child)
    validate(base.copy(members = listOf(getter.copy(returnType = EtsNullableType(animalType)))), child)
    fun reject(label: String, vararg values: EtsClass) {
        val failure = runCatching { validate(*values) }.exceptionOrNull()
        check(failure is InvalidTarget && failure.source.file == "CovariantProperty.kt") { "$label: $failure" }
    }
    reject("Unrelated getter", view, computed.copy(members = listOf(implementation.copy(returnType = unrelated.symbol.type))))
    reject("Nullable getter", view, computed.copy(members = listOf(implementation.copy(returnType = EtsNullableType(dogType)))))
    reject("Writable field contract is invariant", view.copy(members = listOf(field.copy(readonly = false))), mutable)
    reject("Readonly cannot implement writable", view.copy(members = listOf(field.copy(readonly = false))), narrowed)
    reject("Wrong getter identity", base, child.copy(members = listOf(override.copy(overrides = listOf("wrong")))))
    reject("Getter cannot narrow writable base", base.copy(members = listOf(getter, setter)), child.copy(members = listOf(
        override, setter.copy(source = at(13), overrides = listOf(setter.symbol.id)))))
    reject("Setter cannot narrow writable base", base.copy(members = listOf(getter, setter)), child.copy(members = listOf(
        getter.copy(source = at(8), overrides = listOf(getter.symbol.id)), setter.copy(source = at(13), overrides = listOf(setter.symbol.id),
            parameters = setter.parameters.map { it.copy(symbol = it.symbol.copy(type = dogType)) }))))
    reject("Getter cannot mask writable base", base.copy(members = listOf(getter, setter)), child)
    println("PASS readonly covariance through fields/accessors, invariant writable contracts and eight refusals")
}
