package dev.ets

import java.io.File

fun main(arguments: Array<String>) {
    val program = overloadModuleFixture()
    val functions = program.files.flatMap { it.declarations }.filterIsInstance<EtsFunction>().associateBy { it.name }
    val service = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().single { it.name == "OverloadMethods" }
    val members = service.members.filterIsInstance<EtsFunction>().associateBy { it.name }
    val model = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().single { it.name == "TokenModel" }
    fun call(name: String) = (functions.getValue(name).body.single() as EtsReturn).value as EtsCall
    val seen = mutableListOf<EtsProgram>()
    val runtime = EtsRuntimeSupport { part -> seen += part; StandardLibraryRuntime.declarations(part) }
    val modules = emitEtsModules(program, runtime)
    check(modules.keys.toList() == listOf("Numbers.ets", "OverloadCalls.ets", "OverloadMethods.ets", "Texts.ets", "TokenModel.ets"))
    check(seen.size == program.files.size)
    for (part in seen) {
        val file = part.files.single()
        check(file === program.files.single { it.sourcePath == file.sourcePath })
        check(file.declarations.all { it.source.file == file.sourcePath })
    }
    fun imports(name: String) = modules.getValue("$name.ets").lines().filter { it.startsWith("import ") }
    val expected = listOf("Numbers" to listOf("select", "select_0", "select_1", "select_2"), "OverloadMethods" to listOf("OverloadMethods"),
        "Texts" to listOf("render", "render_0", "unchanged"), "TokenModel" to listOf("TokenModel"))
        .flatMap { (file, names) -> names.map { "import { $it } from \"./$file\";" } }
    check(imports("OverloadCalls") == expected)
    check(imports("Texts") == listOf("import { TokenModel } from \"./TokenModel\";"))
    for (name in listOf("Numbers", "OverloadMethods", "TokenModel")) check(imports(name).isEmpty())
    check("export function select(value: number): number" in modules.getValue("Numbers.ets"))
    check("export function select_1(value: number): number" in modules.getValue("Numbers.ets"))
    check("export function select_2(left: number, right: number): number" in modules.getValue("Numbers.ets"))
    check("export function render(value: string): string" in modules.getValue("Texts.ets"))
    check("export function render_0(value: number): number" in modules.getValue("Texts.ets"))
    check("export function select_0(): string" in modules.getValue("Numbers.ets"))
    check("export function unchanged(value: TokenModel): TokenModel" in modules.getValue("Texts.ets"))
    check("choose_1(value: string): string" in modules.getValue("OverloadMethods.ets"))
    check("choose_0(): string" in modules.getValue("OverloadMethods.ets"))
    check("static staticSelect_0(value: string): string" in modules.getValue("OverloadMethods.ets"))
    check("return select_1(value);" in modules.getValue("OverloadCalls.ets"))
    check("return service.choose_1(value);" in modules.getValue("OverloadCalls.ets"))
    check("return OverloadMethods.staticSelect_0(value);" in modules.getValue("OverloadCalls.ets"))
    check(modules.values.none { " as " in it || "typeof " in it || "import { choose" in it })
    for (function in functions.values + members.values) {
        check(function.symbol.name == function.name)
        check(function.symbol.id == "function:${function.source.file}:${function.source.start}:${function.sourceName ?: function.name}")
        val original = function.copy(name = function.sourceName ?: function.name, sourceName = null)
        check(original.symbol.id == function.symbol.id)
        check(original.parameters == function.parameters && original.source == function.source)
    }
    for (name in listOf("select_1", "select_2")) check(functions.getValue(name).sourceName == "select")
    check(functions.getValue("render_0").sourceName == "render")
    for (name in listOf("select", "select_0", "render", "unchanged")) check(functions.getValue(name).sourceName == null)
    val first = functions.getValue("select")
    val second = functions.getValue("select_1")
    check(first.symbol.type == second.symbol.type && first.symbol.id != second.symbol.id)
    check((first.body.single() as EtsReturn).value is EtsReference)
    val secondBody = (second.body.single() as EtsReturn).value as EtsBinary
    check(secondBody.operator == "+" && (secondBody.right as EtsLiteral).value == 1)
    check((call("callFirst").callee as EtsReference).symbol == first.symbol)
    check((call("callSecond").callee as EtsReference).symbol == second.symbol)
    for ((name, function) in functions.filterKeys { it.startsWith("call") }) {
        val invocation = call(name)
        check(invocation.arguments.map { (it as EtsReference).symbol } == function.parameters.filter { it.symbol.name != "service" }.map { it.symbol })
        when (val callee = invocation.callee) {
            is EtsReference -> check(callee.symbol == functions.getValue(callee.symbol.name).symbol && !callee.symbol.external)
            is EtsMember -> {
                val declaration = members.getValue(callee.name)
                check(callee.symbolId == declaration.symbol.id && callee.type == declaration.symbol.type)
                val receiver = callee.receiver as EtsReference
                check(!receiver.symbol.external)
                check(receiver.symbol == if (declaration.static) service.symbol else function.parameters.first().symbol)
            }
            else -> error("Expected resolved source call")
        }
    }
    check(emitEtsModules(program.copy(files = program.files.reversed()), StandardLibraryRuntime) == modules)
    val reordered = emitEtsModules(program.copy(files = program.files.map { it.copy(declarations = it.declarations.reversed()) }), StandardLibraryRuntime)
    for ((name, text) in reordered) check(text.lines().filter { it.startsWith("import ") } == modules.getValue(name).lines().filter { it.startsWith("import ") })
    check("export function select_1(value: number): number" in emitEtsProgram(program, StandardLibraryRuntime))

    fun replace(original: EtsDeclaration, replacement: EtsDeclaration) = program.copy(files = program.files.map { file ->
        file.copy(declarations = file.declarations.map { if (it === original) replacement else it })
    })
    fun changedCall(name: String, transform: (EtsCall) -> EtsCall): EtsProgram {
        val function = functions.getValue(name)
        val statement = function.body.single() as EtsReturn
        return replace(function, function.copy(body = listOf(statement.copy(value = transform(statement.value as EtsCall)))))
    }
    var negatives = 0
    fun rejects(value: EtsProgram, source: SourceSpan) {
        seen.clear()
        val failure = runCatching { emitEtsModules(value, runtime) }.exceptionOrNull()
        check(failure is InvalidTarget) { "Expected InvalidTarget, got $failure" }
        check(failure.source == source) { "Wrong source: ${failure.source}; expected $source; $failure" }
        check(seen.isEmpty()) { "Malformed overload reached runtime selection" }
        negatives++
    }
    val duplicate = second.copy(name = "duplicate", sourceName = "select")
    rejects(program.copy(files = program.files.map { file -> if (file.sourcePath == second.source.file)
        file.copy(declarations = file.declarations + duplicate) else file }), duplicate.source)
    val textMember = members.getValue("choose_1")
    val duplicateMember = textMember.copy(name = "duplicate", sourceName = "choose")
    rejects(replace(service, service.copy(members = service.members + duplicateMember)), duplicateMember.source)
    val secondCall = call("callSecond")
    val secondReference = secondCall.callee as EtsReference
    rejects(replace(second, second.copy(sourceName = "differentSource")), secondReference.source)
    rejects(changedCall("callSecond") { it.copy(callee = secondReference.copy(symbol = second.symbol.copy(id = "missing:select"))) }, secondReference.source)
    rejects(changedCall("callSecond") { it.copy(callee = secondReference.copy(symbol = second.symbol.copy(id = first.symbol.id))) }, secondReference.source)
    rejects(changedCall("callSecond") { it.copy(callee = secondReference.copy(symbol = second.symbol.copy(name = "select"))) }, secondReference.source)
    rejects(changedCall("callSecond") { it.copy(callee = secondReference.copy(symbol = second.symbol.copy(type = EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.STRING)))) }, secondReference.source)
    val memberCall = call("callMemberText")
    val member = memberCall.callee as EtsMember
    rejects(changedCall("callMemberText") { it.copy(callee = member.copy(symbolId = "missing:choose")) }, member.source)
    rejects(changedCall("callMemberText") { it.copy(callee = member.copy(symbolId = members.getValue("choose").symbol.id)) }, member.source)
    rejects(changedCall("callMemberText") { it.copy(callee = member.copy(name = "choose")) }, member.source)
    rejects(changedCall("callMemberText") { it.copy(callee = member.copy(type = members.getValue("choose").symbol.type)) }, member.source)
    rejects(changedCall("callMemberText") { it.copy(callee = member.copy(receiver = EtsReference(service.symbol, member.source))) }, member.source)
    val staticCall = call("callStaticText")
    val staticMember = staticCall.callee as EtsMember
    rejects(changedCall("callStaticText") { it.copy(callee = staticMember.copy(receiver = EtsNew(service.symbol.type as EtsNamedType,
        emptyList(), staticMember.source))) }, staticMember.source)
    rejects(changedCall("callSecond") { it.copy(arguments = it.arguments + EtsLiteral(2, EtsTypes.NUMBER, it.source)) }, secondCall.source)
    rejects(changedCall("callSecond") { it.copy(type = EtsTypes.STRING) }, secondCall.source)
    rejects(replace(second, second.copy(exported = false)), secondReference.source)
    val unchanged = functions.getValue("unchanged")
    rejects(EtsProgram(listOf(EtsFile(model.source.file!!, listOf(model.copy(exported = false))),
        EtsFile(unchanged.source.file!!, listOf(unchanged)))), unchanged.source)
    rejects(replace(second, second.copy(name = "select")), second.source)
    val text = functions.getValue("render")
    val collidingText = text.copy(name = "select", sourceName = "render")
    val textCallFunction = functions.getValue("callText")
    val textReturn = textCallFunction.body.single() as EtsReturn
    val textCall = textReturn.value as EtsCall
    val textReference = textCall.callee as EtsReference
    val updatedCall = textCallFunction.copy(body = listOf(textReturn.copy(value = textCall.copy(callee = textReference.copy(symbol = collidingText.symbol)))))
    rejects(program.copy(files = program.files.map { file -> file.copy(declarations = file.declarations.map { declaration ->
        when { declaration === text -> collidingText; declaration === textCallFunction -> updatedCall; else -> declaration }
    }) }), textReference.source)

    if (arguments.isNotEmpty()) {
        val output = File(arguments.single())
        check(!output.exists()) { "Output exists: $output" }
        check(output.mkdirs())
        modules.forEach { (name, content) -> File(output, name).writeText(content) }
    }
    println("PASS overload modules: five files, sourceName IDs, exact emitted imports, static/instance identity, $negatives negatives")
}
