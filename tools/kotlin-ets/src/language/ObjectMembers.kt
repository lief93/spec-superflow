package dev.ets

/** Like Kotlin/JS identityHashCode, cache a process-local hash on the instance. */
internal fun identityHashMembers(receiver: EtsExpression, at: SourceSpan): List<EtsClassMember> {
    val cache = EtsSymbol("identity-hash:${at.file}:${at.start}", "__etsIdentityHash", EtsTypes.NUMBER, at)
    val access = EtsMember(receiver, cache.name, cache.type, at, cache.id)
    fun number(value: Int) = EtsLiteral(value, EtsTypes.NUMBER, at)
    val math = EtsReference(EtsSymbol("stdlib:Math", "Math", EtsNamedType("Math"), at, external = true))
    fun call(name: String, args: List<EtsExpression>) = EtsCall(EtsMember(math, name,
        EtsFunctionType(List(args.size) { EtsTypes.NUMBER }, EtsTypes.NUMBER), at), args, EtsTypes.NUMBER, at)
    val random = EtsBinary("+", call("floor", listOf(EtsBinary("*", call("random", emptyList()),
        number(2147483646), EtsTypes.NUMBER, at))), number(1), EtsTypes.NUMBER, at)
    val assign = EtsExpressionStatement(EtsAssignment(access, random, at))
    return listOf(EtsField(cache, number(0), EtsVisibility.PRIVATE),
        EtsFunction("hashCode", emptyList(), EtsTypes.NUMBER, listOf(
            EtsIf(listOf(EtsBranch(EtsBinary("===", access, number(0), EtsTypes.BOOLEAN, at), listOf(assign))), at),
            EtsReturn(access, at)), at, kind = EtsFunctionKind.METHOD))
}
