package dev.ets

private class Module(
    override val id: String,
    override val sourceCalls: Set<String> = setOf("sample.$id"),
    override val sourceTypes: Set<String> = emptySet(),
    override val rootDefaultCalls: Set<String> = emptySet(),
    override val projectCalls: List<AdapterProjectCall> = emptyList(),
    override val targetCalls: List<AdapterTargetCall> = emptyList(),
    override val targetValues: List<AdapterTargetValue> = emptyList(),
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
    val provided = AdapterTargetValue("sample.state", "state", EtsNamedType("State"))
    val targetWithValue = AdapterTargetApi(emptyMap(), mapOf(provided.id to provided))
    check(targetWithValue.value(provided.id, EtsNamedType("State", symbolId = "source:state"), source).symbol.type ==
        EtsNamedType("State", symbolId = "source:state"))
    val wrongValue = runCatching { targetWithValue.value(provided.id, EtsTypes.STRING, source) }.exceptionOrNull()
    check(wrongValue is Unsupported && wrongValue.diagnostic.code == "PROJECT_ADAPTER_RETURN_TYPE" &&
        wrongValue.diagnostic.source == source)
    fun rejected(vararg modules: AdapterModule) {
        check(runCatching { AdapterModules(modules.toList()) }.exceptionOrNull() is IllegalArgumentException)
    }
    rejected(Module(""))
    rejected(Module("a"), Module("a"))
    rejected(Module("a", emptySet()))
    rejected(Module("a", setOf("")))
    rejected(Module("a", setOf("sample.shared")), Module("b", setOf("sample.shared")))
    rejected(Module("a", sourceTypes = setOf("sample.Type")), Module("b", sourceTypes = setOf("sample.Type")))
    rejected(Module("a", rootDefaultCalls = setOf("sample.other")))
    rejected(Module("a", targetCalls = listOf(declaration)), Module("b", targetCalls = listOf(declaration)))
    val identity = AdapterCallIdentity("sample.provide", 1, parameters = emptyList(), returnType = "T of sample.provide")
    val binding = AdapterProjectCall(identity, "sample.State", EtsNamedType("State"))
    rejected(Module("a", projectCalls = listOf(binding)), Module("b", projectCalls = listOf(binding)))
    rejected(Module("a", projectCalls = listOf(binding)), Module("b", projectCalls =
        listOf(binding.copy(resolvedSourceReturnType = "sample.Other", targetReturnType = EtsNamedType("Other")))))
    rejected(Module("a", projectCalls = listOf(binding)), Module("b", sourceCalls = setOf("sample.provide")))
    rejected(Module("a", targetValues = listOf(provided)), Module("b", targetValues = listOf(provided)))
    rejected(Module("a", targetCalls = listOf(declaration)),
        Module("b", targetValues = listOf(AdapterTargetValue(declaration.id, "value", number))))
    rejected(Module("a", imports = listOf(EtsImport("one", "Value"))), Module("b", imports = listOf(EtsImport("two", "Value"))))
    val created = mutableListOf<String>()
    val modules = AdapterModules(listOf(Module("b", created = created), Module("a", created = created)))
    check(modules.rules().size == 2 && created == listOf("a", "b"))
    check(modules.imports.isEmpty())
    check(AdapterModules().rules().isEmpty())
    val root = EtsFile("Root.kt", emptyList())
    val first = EtsFile("First.kt", emptyList())
    val second = EtsFile("Second.kt", emptyList())
    val native = EtsClass("NativeContract", emptyList(), source, kind = EtsClassKind.INTERFACE)
    val import = EtsImport("native", "NativeContract")
    val chain = object : CallRule {
        override fun lower(call: org.jetbrains.kotlin.ir.expressions.IrCall, language: Language, scope: Scope): EtsExpression? = null
        override fun targetFiles(program: EtsProgram) =
            if (first in program.files) listOf(first, second) else listOf(first)
        override fun targetImports(program: EtsProgram) = if (second in program.files) listOf(import) else emptyList()
        override fun targetContracts(program: EtsProgram) = if (second in program.files) listOf(native) else emptyList()
    }
    val linked = linkAdapterDeclarations(EtsProgram(listOf(root)), listOf(chain, chain))
    check(linked.files == listOf(root, first, second))
    check(linked.imports == listOf(import))
    check(linked.externalClasses.values.toList() == listOf(native))
    check(linkAdapterDeclarations(linked, listOf(chain)) == linked)
    val conflicting = object : CallRule by chain {
        override fun targetFiles(program: EtsProgram) = listOf(first.copy(declarations = listOf(native)))
    }
    check(runCatching { linkAdapterDeclarations(linked, listOf(conflicting)) }.exceptionOrNull() is IllegalArgumentException)
    val conflictingType = object : CallRule by chain {
        override fun targetContracts(program: EtsProgram) = listOf(native.copy(exported = true))
    }
    check(runCatching { linkAdapterDeclarations(linked, listOf(conflictingType)) }.exceptionOrNull() is IllegalArgumentException)
    println("PASS: adapter contract, deterministic providers, conflicts, shared target validation")
}
