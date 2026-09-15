package dev.ets

fun checkTryContract() {
    val at = SourceSpan("Try.kt", 0, 10)
    val caught = EtsSymbol("caught", "failure", EtsTypes.OBJECT, at)
    val one = EtsLiteral(1, EtsTypes.NUMBER, at)
    val attempt = EtsTry(listOf(EtsReturn(one, at)),
        EtsCatch(caught, listOf(EtsExpressionStatement(EtsReference(caught)), EtsReturn(one, at))),
        listOf(EtsExpressionStatement(one)), at)
    fun program(body: List<EtsStatement>) = EtsProgram(listOf(EtsFile("Try.kt", listOf(
        EtsFunction("attempt", emptyList(), EtsTypes.NUMBER, body, at)))))
    EtsValidator().validate(program(listOf(attempt)))
    EtsValidator().validate(program(listOf(attempt.copy(handler = null))))
    EtsValidator().validate(program(listOf(attempt.copy(finallyBody = null))))
    val printed = EtsPrinter().program(program(listOf(attempt)))
    check("try {" in printed && "catch (failure) {" in printed && "finally {" in printed)
    val visited = mutableListOf<EtsNode>()
    walkEts(attempt, visited::add)
    check(visited.count { it === one } == 3)
    check(visited.any { it is EtsReference && it.symbol == caught })
    fun rejected(body: List<EtsStatement>, reason: String) {
        val failure = runCatching { EtsValidator().validate(program(body)) }.exceptionOrNull()
        check(failure is InvalidTarget && reason in failure.message.orEmpty()) { "$reason: $failure" }
    }
    rejected(listOf(attempt.copy(handler = null, finallyBody = null)), "requires catch or finally")
    rejected(listOf(attempt.copy(handler = attempt.handler!!.copy(parameter = caught.copy(type = EtsTypes.NUMBER)))), "catch binding requires Object")
    rejected(listOf(attempt, EtsExpressionStatement(EtsReference(caught))), "Unbound target symbol")
    rejected(listOf(attempt.copy(finallyBody = listOf(EtsExpressionStatement(EtsReference(caught))))), "Unbound target symbol")
    val badReturn = EtsReturn(EtsLiteral("wrong", EtsTypes.STRING, at), at)
    rejected(listOf(attempt.copy(handler = EtsCatch(caught, listOf(badReturn)))), "type mismatch")
    println("Try target contract: typed bodies, catch scope, finally, traversal/printing and five rejections passed")
}
