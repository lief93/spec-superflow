package dev.ets

private class Module(
    override val id: String,
    override val sourceCalls: Set<String> = setOf("sample.$id"),
    override val sourceTypes: Set<String> = emptySet(),
    override val targetCalls: List<AdapterTargetCall> = emptyList(),
    override val imports: List<EtsImport> = emptyList(),
    private val created: MutableList<String> = mutableListOf()
) : AdapterModule {
    override fun create(target: AdapterTargetApi, ui: AdapterUiServices?): CallRule {
        created += id
        return CallRule { _, _, _ -> null }
    }
}

fun main() {
    val source = SourceSpan("Adapter.kt", 10, 20)
    val number = EtsTypes.NUMBER
    val declaration = AdapterTargetCall("sample.double", "doubleValue", EtsFunctionType(listOf(number), number))
    val target = AdapterTargetApi(mapOf(declaration.id to declaration))
    fun code(argument: EtsExpression): String {
        val call = target.call(declaration.id, listOf(argument), source)
        val function = EtsFunction("example", emptyList(), number, listOf(EtsReturn(call, source)), source)
        return EtsPrinter().program(EtsProgram(listOf(EtsFile("Adapter.kt", listOf(function)))))
    }
    check("doubleValue(2)" in code(EtsLiteral(2, number, source)))
    val badType = runCatching { code(EtsLiteral("wrong", EtsTypes.STRING, source)) }.exceptionOrNull()
    check(badType is InvalidTarget && badType.source == source)
    check(runCatching { target.call("missing", emptyList(), source) }.exceptionOrNull() is Unsupported)
    check(runCatching { target.call(declaration.id, emptyList(), source) }.exceptionOrNull() is Unsupported)
    fun rejected(vararg modules: AdapterModule) {
        check(runCatching { AdapterModules(modules.toList()) }.exceptionOrNull() is IllegalArgumentException)
    }
    rejected(Module(""))
    rejected(Module("a"), Module("a"))
    rejected(Module("a", emptySet()))
    rejected(Module("a", setOf("")))
    rejected(Module("a", setOf("sample.shared")), Module("b", setOf("sample.shared")))
    rejected(Module("a", sourceTypes = setOf("sample.Type")), Module("b", sourceTypes = setOf("sample.Type")))
    rejected(Module("a", targetCalls = listOf(declaration)), Module("b", targetCalls = listOf(declaration)))
    rejected(Module("a", imports = listOf(EtsImport("one", "Value"))), Module("b", imports = listOf(EtsImport("two", "Value"))))
    val created = mutableListOf<String>()
    val modules = AdapterModules(listOf(Module("b", created = created), Module("a", created = created)))
    check(modules.rules().size == 2 && created == listOf("a", "b"))
    check(modules.imports.isEmpty())
    check(AdapterModules().rules().isEmpty())
    println("PASS: adapter contract, deterministic providers, conflicts, shared target validation")
}
