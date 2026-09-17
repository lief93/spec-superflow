package dev.ets

fun checkDeclarationVariance() {
    val concreteArray = EtsNamedType("Array", listOf(EtsTypes.STRING))
    val outputArray = EtsNamedType("Array", listOf(EtsCapturedType(EtsTypes.OBJECT, EtsTypes.NEVER)))
    check(etsAssignable(concreteArray, outputArray))
    check(!etsAssignable(outputArray, concreteArray))
    check(!etsAssignable(concreteArray, EtsNamedType("Array", listOf(EtsCapturedType(EtsTypes.NUMBER, EtsTypes.NEVER)))))
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
    checkCapturedArguments()
}

private fun checkCapturedArguments() {
    val at = SourceSpan("Projections.kt", 1, 2)
    val animal = EtsClass("Animal", emptyList(), at, kind = EtsClassKind.INTERFACE)
    val a = animal.symbol.type as EtsNamedType
    val dog = EtsClass("Dog", emptyList(), at, kind = EtsClassKind.INTERFACE, interfaces = listOf(a))
    val d = dog.symbol.type as EtsNamedType
    val t = EtsTypeParameter("Cell:T", "T")
    val field = EtsField(EtsSymbol("Cell:value", "value", EtsTypeParameterType(t.id, t.name), at))
    val cell = EtsClass("Cell", listOf(field), at, kind = EtsClassKind.INTERFACE, typeParameters = listOf(t))
    val top = EtsNullableType(EtsTypes.OBJECT)
    val out = EtsCapturedType(a, EtsTypes.NEVER)
    val input = EtsCapturedType(top, d)
    val star = EtsCapturedType(top, EtsTypes.NEVER)
    fun applied(argument: EtsType) = (cell.symbol.type as EtsNamedType).copy(arguments = listOf(argument))
    fun validate(function: EtsFunction, others: List<EtsDeclaration> = emptyList()) = EtsValidator().validate(EtsProgram(listOf(
        EtsFile("Projections.kt", listOf(animal, dog, cell, function) + others))))
    fun conversion(from: EtsType, to: EtsType) {
        val p = EtsSymbol("input", "input", applied(from), at)
        validate(EtsFunction("convert", listOf(EtsParameter(p)), applied(to), listOf(EtsReturn(EtsReference(p), at)), at))
    }
    fun write(argument: EtsCapturedType, assigned: EtsType) {
        val p = EtsSymbol("input", "input", applied(argument), at)
        val v = EtsSymbol("assigned", "assigned", assigned, at)
        val access = EtsMember(EtsReference(p), "value", argument.readType, at, field.symbol.id)
        validate(EtsFunction("write", listOf(EtsParameter(p), EtsParameter(v)), EtsTypes.VOID,
            listOf(EtsExpressionStatement(EtsAssignment(access, EtsReference(v), at), at)), at))
    }
    fun read(argument: EtsCapturedType, claimed: EtsType, identity: String = field.symbol.id) {
        val p = EtsSymbol("input", "input", applied(argument), at)
        validate(EtsFunction("read", listOf(EtsParameter(p)), claimed,
            listOf(EtsReturn(EtsMember(EtsReference(p), "value", claimed, at, identity), at)), at))
    }
    var refusals = 0
    fun reject(label: String, action: () -> Unit) {
        val failure = runCatching(action).exceptionOrNull()
        check(failure is InvalidTarget && failure.source == at) { "$label: $failure" }; refusals++
    }
    conversion(d, out); conversion(a, input); conversion(out, star); conversion(input, star)
    write(input, d); read(out, a); read(input, top); read(star, top)
    reject("Out cannot be invariant") { conversion(out, a) }
    reject("In cannot be invariant") { conversion(input, d) }
    reject("Star cannot be invariant") { conversion(star, top) }
    reject("Out cannot narrow") { conversion(out, EtsCapturedType(d, EtsTypes.NEVER)) }
    reject("Out cannot write") { write(out, d) }
    reject("Star cannot write even null") { write(star, EtsTypes.NULL) }
    reject("In cannot write a supertype") { write(input, a) }
    reject("In cannot read Specific") { read(input, d) }
    reject("Invalid interval") { conversion(EtsCapturedType(d, a), star) }
    reject("Capture cannot bypass member identity") { read(out, a, "unrelated") }
    reject("Capture cannot be a standalone value type") {
        val p = EtsSymbol("input", "input", out, at)
        validate(EtsFunction("invalid", listOf(EtsParameter(p)), EtsTypes.VOID, emptyList(), at))
    }
    val callback = EtsFunctionType(listOf(out), input)
    check(etsReadType(callback) == EtsFunctionType(listOf(EtsTypes.NEVER), top))
    check(etsReadType(callback, write = true) == EtsFunctionType(listOf(a), d))
    val binder = EtsTypeParameter("get:T", "T")
    val ref = EtsTypeParameterType(binder.id, binder.name)
    val box = EtsSymbol("get:cell", "cell", applied(ref), at)
    val get = EtsFunction("get", listOf(EtsParameter(box)), ref, listOf(EtsReturn(
        EtsMember(EtsReference(box), "value", ref, at, field.symbol.id), at)), at, typeParameters = listOf(binder))
    val receiver = EtsSymbol("call:cell", "cell", applied(out), at)
    val call = EtsCall(EtsReference(get.symbol), listOf(EtsReference(receiver)), a, at, listOf(out))
    val invoke = EtsFunction("invoke", listOf(EtsParameter(receiver)), a, listOf(EtsReturn(call, at)), at)
    validate(invoke, listOf(get))
    val second = box.copy(id = "get:second", name = "second")
    val repeated = get.copy(parameters = get.parameters + EtsParameter(second))
    reject("Intervals cannot establish shared existential identity") {
        validate(invoke.copy(body = listOf(EtsReturn(call.copy(callee = EtsReference(repeated.symbol),
            arguments = listOf(EtsReference(receiver), EtsReference(receiver))), at))), listOf(repeated))
    }
    val duplicated = (get.symbol.type as EtsFunctionType).copy(parameters = listOf(applied(EtsFunctionType(listOf(ref), ref))))
    check(!etsSupportsCapturedCall(duplicated, listOf(out)))
    check(!etsSupportsCapturedCall((get.symbol.type as EtsFunctionType).copy(parameters = listOf(ref)), listOf(out)))
    val argument = EtsSymbol("callback:value", "value", a, at)
    val body = listOf(EtsReturn(EtsReference(argument), at))
    val wide = EtsLambda(emptyList(), body, top, at)
    val narrowed = etsContextualLambda(wide, EtsFunctionType(emptyList(), a)) as EtsLambda
    check(narrowed.body === wide.body && narrowed.returnType == a)
    validate(EtsFunction("callback", listOf(EtsParameter(argument)), narrowed.type, listOf(EtsReturn(narrowed, at)), at))
    val invalid = etsContextualLambda(wide, EtsFunctionType(emptyList(), d)) as EtsLambda
    reject("Contextual lambda narrowing must check its return body") {
        validate(EtsFunction("callback", listOf(EtsParameter(argument)), invalid.type, listOf(EtsReturn(invalid, at)), at))
    }
    println("PASS captured read/write intervals, callback polarity and $refusals source-linked refusals")
}
