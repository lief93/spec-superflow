package dev.ets

import java.io.File

fun main(arguments: Array<String>) {
    val program = globalBuilderFixture()
    fun function(name: String) = program.files.flatMap { it.declarations }.filterIsInstance<EtsFunction>().single { it.name == name }
    val badge = function("Badge")
    val dashboard = function("Dashboard")
    val seen = mutableListOf<EtsProgram>()
    val runtime = EtsRuntimeSupport { part -> seen += part; StandardLibraryRuntime.declarations(part) }
    val modules = emitEtsModules(program, runtime)
    check(modules.keys.toList() == listOf("Badge.ets", "Dashboard.ets", "Labels.ets", "Model.ets", "Values.ets"))
    check(seen.size == program.files.size)
    for (part in seen) {
        val file = part.files.single()
        check(program.files.single { it.sourcePath == file.sourcePath } === file) { "Output moved or rebuilt source declarations" }
        check(file.declarations.all { it.source.file == file.sourcePath })
    }
    check(badge.builder && dashboard.builder && badge.kind == EtsFunctionKind.FUNCTION && dashboard.kind == EtsFunctionKind.FUNCTION)
    check(badge.parameters.map { it.symbol.name } == listOf("model", "onSelect"))
    check(dashboard.parameters.map { it.symbol.name } == listOf("model"))
    val declarations = program.files.flatMap { it.declarations }.filterIsInstance<EtsFunction>().associateBy { it.symbol.id }
    var sourceCalls = 0
    program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
        if (node is EtsReference && node.symbol.id in declarations) {
            check(!node.symbol.external && node.symbol == declarations.getValue(node.symbol.id).symbol)
            sourceCalls++
        }
        if (node is EtsReference) check(node.symbol.name != "this") { "Global builder captured an implicit component receiver" }
    } } }
    check(sourceCalls == 4)
    val badgeText = modules.getValue("Badge.ets")
    val dashboardText = modules.getValue("Dashboard.ets")
    check("@Builder\nexport function Badge(model: LabelModel, onSelect: (() => void))" in badgeText)
    check("@Builder\nexport function Dashboard(model: LabelModel)" in dashboardText)
    check("Badge(model, (): void => {" in dashboardText)
    check("labelLength(labelFor(model));" in dashboardText)
    check("Text(labelFor(model)).onClick(onSelect)" in badgeText)
    check(modules.values.none { "@Component" in it || "this." in it })
    check("function Badge" !in dashboardText && "function Dashboard" !in badgeText)
    val expectedImports = listOf("import { Badge } from \"./Badge\";", "import { labelFor } from \"./Labels\";",
        "import { LabelModel } from \"./Model\";", "import { labelLength } from \"./Values\";")
    check(dashboardText.lines().filter { it.startsWith("import ") } == expectedImports)
    check(badgeText.lines().filter { it.startsWith("import ") } == listOf(
        "import { labelFor } from \"./Labels\";", "import { LabelModel } from \"./Model\";"))
    check(modules.getValue("Labels.ets").lines().count { it.startsWith("function __etsSubstring(") } == 1)
    check(modules.getValue("Labels.ets").lines().count { it.startsWith("function __etsSubstringFrom(") } == 1)
    check(modules.filterKeys { it != "Labels.ets" }.values.none { "function __ets" in it })
    check(emitEtsModules(program.copy(files = program.files.reversed()), StandardLibraryRuntime) == modules)

    fun replaced(original: EtsDeclaration, replacement: EtsDeclaration) = program.copy(files = program.files.map { file ->
        file.copy(declarations = file.declarations.map { if (it === original) replacement else it })
    })
    var negatives = 0
    fun rejects(value: EtsProgram, message: String, source: SourceSpan) {
        seen.clear()
        val failure = runCatching { emitEtsModules(value, runtime) }.exceptionOrNull()
        check(failure is InvalidTarget && message in failure.message.orEmpty()) { "Expected $message, got $failure" }
        check(failure.source == source) { "Lost failure source: ${failure.source} instead of $source" }
        check(seen.isEmpty()) { "Invalid target reached runtime selection" }
        negatives++
    }
    rejects(replaced(badge, badge.copy(exported = false)), "not exported", dashboard.source)
    val labelLength = function("labelLength")
    rejects(replaced(labelLength, labelLength.copy(exported = false)), "not exported", dashboard.source)
    rejects(program.copy(files = program.files.filter { it.sourcePath != badge.source.file }), "Source UI invocation requires a declared builder", dashboard.source)
    rejects(program.copy(files = program.files.filter { it.sourcePath != labelLength.source.file }), "Unbound target symbol", dashboard.source)
    val localBadge = badge.copy(source = SourceSpan(dashboard.source.file, 100, 105), exported = false)
    rejects(program.copy(files = program.files.map { file ->
        if (file.sourcePath == dashboard.source.file) file.copy(declarations = file.declarations + localBadge) else file
    }), "Conflicting module binding", dashboard.source)
    val column = dashboard.body.single() as EtsUiElement
    val invocation = column.children!!.single() as EtsUiElement
    val unknown = invocation.copy(call = invocation.call.copy(callee = EtsReference(
        badge.symbol.copy(id = "missing:Badge"), dashboard.source)))
    rejects(replaced(dashboard, dashboard.copy(body = listOf(column.copy(children = listOf(unknown))))),
        "Source UI invocation requires a declared builder", dashboard.source)

    // A same-named builder in an unrelated file is legal and must not be imported by spelling.
    val unrelated = badge.copy(source = SourceSpan("source/Other.kt", 1, 2))
    val separate = emitEtsModules(program.copy(files = program.files + EtsFile("source/Other.kt", listOf(unrelated))),
        StandardLibraryRuntime)
    check(separate.getValue("Dashboard.ets") == dashboardText)
    check("@Builder\nexport function Badge(" in separate.getValue("Other.ets"))

    if (arguments.isNotEmpty()) {
        val output = File(arguments.single())
        check(!output.exists()) { "Output exists: $output" }
        check(output.mkdirs())
        modules.forEach { (name, content) -> File(output, name).writeText(content) }
    }
    println("PASS global builders: source ownership, exact symbols/names/parameters, nested callback imports, runtime closure, $negatives source-linked negatives")
}
