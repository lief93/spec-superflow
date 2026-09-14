package dev.ets

fun checkDeclarationVariance() {
    val at = SourceSpan("Variance.kt", 1, 2)
    val animal = EtsClass("Animal", emptyList(), at, kind = EtsClassKind.INTERFACE)
    val a = animal.symbol.type as EtsNamedType
    val dog = EtsClass("Dog", emptyList(), at, kind = EtsClassKind.INTERFACE, interfaces = listOf(a))
    val d = dog.symbol.type as EtsNamedType
    val t = EtsTypeParameter("Producer:T", "T", variance = EtsVariance.OUT)
    val ref = EtsTypeParameterType(t.id, t.name)
    val read = EtsFunction("read", emptyList(), ref, emptyList(), at, kind = EtsFunctionKind.METHOD, abstract = true)
    val producer = EtsClass("Producer", listOf(read), at, kind = EtsClassKind.INTERFACE, typeParameters = listOf(t))
    val consume = EtsFunction("accept", listOf(EtsParameter(EtsSymbol("value", "value", ref, at))), EtsTypes.VOID,
        emptyList(), at, kind = EtsFunctionKind.METHOD, abstract = true)
    val consumer = producer.copy(name = "Consumer", members = listOf(consume), typeParameters = listOf(t.copy(variance = EtsVariance.IN)))
    fun applied(owner: EtsClass, argument: EtsType) = (owner.symbol.type as EtsNamedType).copy(arguments = listOf(argument))
    fun conversion(from: EtsType, to: EtsType): EtsFunction {
        val value = EtsSymbol("input", "input", from, at)
        return EtsFunction("convert", listOf(EtsParameter(value)), to, listOf(EtsReturn(EtsReference(value), at)), at)
    }
    fun validate(from: EtsType, to: EtsType, vararg owners: EtsClass) = EtsValidator().validate(
        EtsProgram(listOf(EtsFile("Variance.kt", listOf(animal, dog) + owners + conversion(from, to)))))
    validate(applied(producer, d), applied(producer, a), producer)
    validate(applied(consumer, a), applied(consumer, d), consumer)
    validate(applied(producer, applied(producer, d)), applied(producer, applied(producer, a)), producer)
    validate(applied(producer, d), applied(producer, EtsNullableType(a)), producer)
    fun reject(label: String, action: () -> Unit) {
        val failure = runCatching(action).exceptionOrNull()
        check(failure is InvalidTarget && failure.source == at) { "$label: $failure" }
    }
    reject("Producer cannot narrow") { validate(applied(producer, a), applied(producer, d), producer) }
    reject("Consumer cannot widen") { validate(applied(consumer, d), applied(consumer, a), consumer) }
    reject("Invariant remains invariant") { validate(applied(producer, d), applied(producer, a),
        producer.copy(typeParameters = listOf(t.copy(variance = EtsVariance.INVARIANT)))) }
    reject("Nullable cannot satisfy nonnull") { validate(applied(producer, EtsNullableType(d)), applied(producer, a), producer) }
    reject("Out used as input") { validate(a, a, producer.copy(members = listOf(consume))) }
    reject("In used as output") { validate(a, a, consumer.copy(members = listOf(read))) }
    reject("Mutable out field") { validate(a, a, producer.copy(members = listOf(EtsField(EtsSymbol("field", "value", ref, at))))) }
    val mutable = producer.copy(name = "Mutable", typeParameters = listOf(t.copy(variance = EtsVariance.INVARIANT)))
    reject("Out nested in invariant container") { validate(a, a, mutable, producer.copy(members = listOf(read.copy(returnType = applied(mutable, ref))))) }
    val callback = EtsFunctionType(listOf(ref), EtsTypes.VOID)
    reject("Out in returned callback input") { validate(a, a, producer.copy(members = listOf(read.copy(returnType = callback)))) }
    validate(a, a, producer.copy(members = listOf(consume.copy(parameters = listOf(EtsParameter(EtsSymbol("callback", "callback", callback, at)))))))
    println("PASS declaration variance, nested and nullable conversion, callback polarity and nine refusals")
}
