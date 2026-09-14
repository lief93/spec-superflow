package dev.ets.tests.builderruntime

import dev.ets.*
import java.io.File

fun main(args: Array<String>) {
    val fixture = builderRuntimeFixture()
    val program = fixture.program
    val seen = mutableListOf<EtsProgram>()
    val selected = linkedMapOf<String, List<String>>()
    val runtime = EtsRuntimeSupport { part ->
        seen.add(part)
        StandardLibraryRuntime.declarations(part).also { lines -> selected[part.files.single().sourcePath] = lines }
    }
    val modules = emitEtsModules(program, runtime)
    val expectedFunctions = mapOf(
        "RuntimeActions.kt" to listOf("__etsIntRem"),
        "RuntimeCaptions.kt" to listOf("__etsSubstring"),
        "RuntimeSummary.kt" to listOf("__etsIntDiv", "__etsListFilter", "__etsSubstring", "__etsSubstringFrom",
            "__etsArrayIterator", "__etsListCount"),
        "RuntimeQuiet.kt" to emptyList(),
        "RuntimeBuilderPage.kt" to emptyList(),
    )
    check(modules.keys == expectedFunctions.keys.map { it.removeSuffix(".kt") + ".ets" }.toSet())
    check(seen.size == program.files.size && seen.all { it.files.size == 1 })
    check(seen.map { it.files.single().sourcePath }.distinct().size == program.files.size)
    val expectedImports = mapOf(
        "RuntimeActions.kt" to emptyList(), "RuntimeCaptions.kt" to emptyList(), "RuntimeQuiet.kt" to emptyList(),
        "RuntimeSummary.kt" to listOf(EtsImport("./RuntimeActions", "onRuntimeMetric"), EtsImport("./RuntimeCaptions", "captionForRuntime")),
        "RuntimeBuilderPage.kt" to listOf(EtsImport("./RuntimeQuiet", "renderRuntimeQuiet"),
            EtsImport("./RuntimeSummary", "renderRuntimeSummary")),
    )
    for (part in seen) {
        val file = part.files.single()
        check(file == program.files.single { it.sourcePath == file.sourcePath }) { "Provider lost original typed declaration" }
        check(part.imports == expectedImports.getValue(file.sourcePath)) { "Wrong source imports for ${file.sourcePath}: ${part.imports}" }
        val expected = expectedFunctions.getValue(file.sourcePath)
        val lines = selected.getValue(file.sourcePath)
        val actualFunctions = lines.filter { it.startsWith("function ") }
        check(actualFunctions.size == expected.size) { "Missing/unused runtime in ${file.sourcePath}: $actualFunctions" }
        expected.forEachIndexed { index, name ->
            check(actualFunctions[index].startsWith("function $name(") || actualFunctions[index].startsWith("function $name<"))
        }
        val classes = lines.filter { it.startsWith("class ") }
        if (file.sourcePath == "RuntimeSummary.kt") check(classes.size == 1 && classes.single().startsWith("class __etsIterator<"))
        else check(classes.isEmpty())
        val output = modules.getValue(file.sourcePath.removeSuffix(".kt") + ".ets")
        expected.forEach { name -> check(output.lines().count { it.startsWith("function $name(") || it.startsWith("function $name<") } == 1) }
        part.imports.forEach { import ->
            check(output.lines().count { it == "import { ${import.name} } from \"${import.module}\";" } == 1)
        }
    }
    val summary = modules.getValue("RuntimeSummary.ets")
    check("@Builder\nexport function renderRuntimeSummary(label: string, values: Array<number>, expanded: boolean)" in summary)
    check("ForEach(" in summary && ".padding({ left:" in summary && ".onClick(" in summary)
    check("function __etsIntRem" !in summary) { "Imported action runtime leaked into builder" }
    check("function __etsListAny" !in summary && "class __etsIntProgression" !in summary)
    check("@Builder\nexport function renderRuntimeQuiet()" in modules.getValue("RuntimeQuiet.ets"))

    val references = mutableListOf<EtsReference>()
    walkEts(fixture.summary) { if (it is EtsReference) references.add(it) }
    for (symbol in listOf(fixture.captions.symbol, fixture.actions.symbol)) {
        check(references.count { it.symbol == symbol } == 1) { "Source declaration identity was replaced" }
        check(!symbol.external)
    }
    val summaryLines = selected.getValue("RuntimeSummary.kt")
    check(summaryLines.indexOfFirst { it.startsWith("class __etsIterator<") } <
        summaryLines.indexOfFirst { it.startsWith("function __etsArrayIterator<") })
    check(summaryLines.indexOfFirst { it.startsWith("function __etsArrayIterator<") } <
        summaryLines.indexOfFirst { it.startsWith("function __etsListCount<") })

    val ordinarySelections = linkedMapOf<String, List<String>>()
    emitEtsModules(fixture.ordinaryProgram, EtsRuntimeSupport { part ->
        StandardLibraryRuntime.declarations(part).also { ordinarySelections[part.files.single().sourcePath] = it }
    })
    check(ordinarySelections.getValue("RuntimeSummary.kt") == summaryLines) { "Builder-specific runtime selection diverged" }
    check(emitEtsModules(program.copy(files = program.files.reversed()), StandardLibraryRuntime) == modules)
    check(StandardLibraryRuntime.declarations(program) == StandardLibraryRuntime.declarations(program.copy(files = program.files.reversed())))

    for (bad in listOf(fixture.countSymbol.copy(id = "stdlib:__etsMissingCount", name = "__etsMissingCount"),
        fixture.countSymbol.copy(name = "__etsDifferentCount"))) {
        val failure = runCatching { emitEtsModules(builderRuntimeFixture(bad).program, StandardLibraryRuntime) }.exceptionOrNull()
        check(failure is IllegalArgumentException && "standard library runtime symbol" in failure.message.orEmpty()) { "Missing nested callback identity rejection: $failure" }
    }
    seen.clear()
    val invalidCallback = runCatching { emitEtsModules(builderRuntimeFixture(uiInCallback = true).program, runtime) }.exceptionOrNull()
    check(invalidCallback is InvalidTarget && invalidCallback.source.file == "RuntimeSummary.kt")
    check(seen.isEmpty()) { "Invalid callback UI reached runtime selection" }

    val output = File(args.single())
    check(!output.exists() && output.mkdirs())
    modules.forEach { (name, text) -> File(output, name).writeText(text) }
    File(output.parentFile, "provider-calls.txt").writeText(expectedFunctions.keys.sorted().joinToString("\n") { file ->
        "$file: functions=${expectedFunctions.getValue(file).joinToString(",")}; imports=${expectedImports.getValue(file)}"
    } + "\n")
    println("PASS five typed modules, one provider invocation/module, exact source imports and runtime closures")
    println("PASS global builder/ordinary expression parity, props/record/callback/ForEach traversal, deduplication/order, no runtime leakage")
    println("PASS callback runtime identity negatives and invalid callback UI rejected before provider")
}
