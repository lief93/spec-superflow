package dev.ets

fun main() {
    val source = SourceSpan("ownership-graph.kt", 0, 1)
    val page = EtsReference(EtsSymbol("page:this", "this", EtsNamedType("Page"), source, external = true))
    fun function(name: String, offset: Int) = EtsFunction(name, emptyList(), EtsTypes.VOID, emptyList(),
        source.copy(start = offset), kind = EtsFunctionKind.METHOD, builder = true)
    fun call(target: EtsFunction) = EtsCall(EtsMember(page, target.name, target.symbol.type, source, target.symbol.id),
        emptyList(), EtsTypes.VOID, source)
    val root = function("Root", 1)
    val leaf = function("Leaf", 2)
    val field = EtsMember(page, "count", EtsTypes.NUMBER, source)
    val fieldRead = EtsExpressionStatement(field)
    val shared = function("Shared", 3).copy(body = listOf(EtsUiElement(call(leaf)), fieldRead))
    val callback = EtsLambda(emptyList(), listOf(fieldRead), EtsTypes.VOID, source)
    val captured = function("Captured", 4).copy(body = listOf(EtsUiElement(call(leaf)), EtsExpressionStatement(callback)))
    val parameter = EtsParameter(EtsSymbol("default", "count", EtsTypes.NUMBER, source), field)
    val default = function("Default", 5).copy(parameters = listOf(parameter), body = listOf(EtsUiElement(call(leaf))))
    val bridge = function("GeneratedBridge", 6)
    val bridged = function("Bridged", 7).copy(body = listOf(EtsUiElement(call(bridge))))
    val caller = function("Caller", 8).copy(body = listOf(EtsUiElement(call(shared))))
    val cycleA = function("CycleA", 9)
    val cycleB = function("CycleB", 10)
    val independentCycle = listOf(cycleA.copy(body = listOf(EtsUiElement(call(cycleB)))),
        cycleB.copy(body = listOf(EtsUiElement(call(cycleA)))))
    val functions = listOf(root, leaf, shared, captured, default, bridged, caller) + independentCycle
    val ownership = BuilderOwnership(functions, root.symbol.id, page.symbol.id)
    check(shared.symbol.id !in ownership.globalIds) { "A reused source-call receiver must not hide its actual page-field occurrence" }
    check(ownership.globalIds == setOf(leaf.symbol.id, cycleA.symbol.id, cycleB.symbol.id))
    val rewritten = ownership.rewrite(shared)
    check(((rewritten.body[0] as EtsUiElement).call.callee as EtsReference).symbol == leaf.symbol)
    check(((rewritten.body[1] as EtsExpressionStatement).expression as EtsMember).receiver === page)
    val anchoredCycle = BuilderOwnership(listOf(root, leaf,
        cycleA.copy(body = listOf(EtsUiElement(call(cycleB)))),
        cycleB.copy(body = listOf(EtsUiElement(call(cycleA)), fieldRead))), root.symbol.id, page.symbol.id)
    check(anchoredCycle.globalIds == setOf(leaf.symbol.id))
    println("PASS shared receiver occurrences, callback/default page captures, bridge/transitive ownership, pure/anchored typed graph cycles and exact rewrite")
}
