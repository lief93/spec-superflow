package dev.ets.tests.boundedruntime

import dev.ets.*
import java.io.File

private data class Fixture(val program: EtsProgram, val member: EtsFunction, val project: EtsFunction)

private fun boundedFixture(fault: String? = null): Fixture {
    fun at(file: String, offset: Int = 10) = SourceSpan("$file.kt", offset, offset + 5)
    fun array(type: EtsType) = EtsNamedType("Array", listOf(type))
    fun cursor(type: EtsType) = EtsNamedType("__etsIterator", listOf(type), "stdlib:__etsIterator", external = true)
    fun use(parameter: EtsTypeParameter) = EtsTypeParameterType(parameter.id, parameter.name)
    fun parameter(id: String, name: String, type: EtsType, source: SourceSpan) = EtsParameter(EtsSymbol(id, name, type, source))
    fun helper(name: String, arguments: List<EtsExpression>, result: EtsType, types: List<EtsType>, source: SourceSpan) =
        EtsCall(EtsReference(EtsSymbol("stdlib:$name", name, EtsFunctionType(arguments.map { it.type }, result), source,
            external = true)), arguments, result, source, types)

    val valueBinder = EtsTypeParameter("Readable:R", "R")
    val read = EtsFunction("read", emptyList(), use(valueBinder), emptyList(), at("RuntimeBoundModel", 20),
        kind = EtsFunctionKind.METHOD, abstract = true)
    val readable = EtsClass("RuntimeReadable", listOf(read), at("RuntimeBoundModel"), exported = true,
        typeParameters = listOf(valueBinder), kind = EtsClassKind.INTERFACE)
    val bound = (readable.symbol.type as EtsNamedType).copy(arguments = listOf(EtsTypes.NUMBER))
    val source = at("RuntimeBoundProject")
    val binder = EtsTypeParameter("project:T", "T", when (fault) {
        "missing bound" -> null
        "unknown bound" -> bound.copy(symbolId = "source:unknown")
        "cyclic bound" -> EtsTypeParameterType("project:T", "T")
        else -> bound
    })
    val values = parameter("project:values", "values", array(use(binder)), source)
    val item = parameter("project:item", "item", use(binder), source)
    val member = EtsMember(EtsReference(item.symbol), if (fault == "unknown member") "missing" else read.name,
        EtsFunctionType(emptyList(), if (fault == "wrong signature") EtsTypes.STRING else EtsTypes.NUMBER), source,
        if (fault == "wrong identity") "function:foreign:read" else read.symbol.id)
    val call = EtsCall(member, emptyList(), (member.type as EtsFunctionType).result, source)
    val transform = EtsLambda(listOf(item), listOf(EtsReturn(call, source)), call.type, source)
    val project = EtsFunction("projectBounded", listOf(values), array(call.type), listOf(EtsReturn(
        helper("__etsListMap", listOf(EtsReference(values.symbol), transform), array(call.type), listOf(use(binder), call.type), source),
        source)), source, exported = true, typeParameters = listOf(binder))

    val filterSource = at("RuntimeBoundFilter")
    val filterBinder = EtsTypeParameter("filter:T", "T", bound)
    val filterValues = parameter("filter:values", "values", array(use(filterBinder)), filterSource)
    val filterItem = parameter("filter:item", "item", use(filterBinder), filterSource)
    val readItem = EtsCall(EtsMember(EtsReference(filterItem.symbol), read.name, EtsFunctionType(emptyList(), EtsTypes.NUMBER),
        filterSource, read.symbol.id), emptyList(), EtsTypes.NUMBER, filterSource)
    val predicate = EtsLambda(listOf(filterItem), listOf(EtsReturn(EtsBinary(">", readItem,
        EtsLiteral(0, EtsTypes.NUMBER, filterSource), EtsTypes.BOOLEAN, filterSource), filterSource)), EtsTypes.BOOLEAN, filterSource)
    val filter = EtsFunction("filterBounded", listOf(filterValues), array(use(filterBinder)), listOf(EtsReturn(
        helper("__etsListFilter", listOf(EtsReference(filterValues.symbol), predicate, EtsLiteral(true, EtsTypes.BOOLEAN, filterSource)),
            array(use(filterBinder)), listOf(use(filterBinder)), filterSource), filterSource)), filterSource,
        exported = true, typeParameters = listOf(filterBinder))

    val consumerSource = at("RuntimeBoundConsumer")
    val consumerBinder = EtsTypeParameter("consumer:T", "T", bound)
    val consumerValues = parameter("consumer:values", "values", array(use(consumerBinder)), consumerSource)
    val filtered = EtsCall(EtsReference(filter.symbol, consumerSource), listOf(EtsReference(consumerValues.symbol)),
        array(use(consumerBinder)), consumerSource, listOf(use(consumerBinder)))
    val consumer = EtsFunction("boundCursor", listOf(consumerValues), cursor(use(consumerBinder)), listOf(EtsReturn(
        helper("__etsArrayIterator", listOf(filtered, EtsLiteral(true, EtsTypes.BOOLEAN, consumerSource)), cursor(use(consumerBinder)),
            listOf(use(consumerBinder)), consumerSource), consumerSource)), consumerSource,
        exported = true, typeParameters = listOf(consumerBinder))
    return Fixture(EtsProgram(listOf(EtsFile("RuntimeBoundModel.kt", listOf(readable)),
        EtsFile("RuntimeBoundProject.kt", listOf(project)), EtsFile("RuntimeBoundFilter.kt", listOf(filter)),
        EtsFile("RuntimeBoundConsumer.kt", listOf(consumer)))), read, project)
}

fun main(args: Array<String>) {
    val fixture = boundedFixture()
    val visits = mutableListOf<EtsProgram>()
    val selection = linkedMapOf<String, List<String>>()
    val provider = EtsRuntimeSupport { part ->
        visits.add(part)
        StandardLibraryRuntime.declarations(part).also { selection[part.files.single().sourcePath] = it }
    }
    val modules = emitEtsModules(fixture.program, provider)
    check(visits.size == 4 && visits.all { it.files.size == 1 })
    check(visits.map { it.files.single().sourcePath }.toSet() == fixture.program.files.map { it.sourcePath }.toSet())
    val functions = mapOf("RuntimeBoundModel.kt" to emptyList(), "RuntimeBoundProject.kt" to listOf("__etsListMap"),
        "RuntimeBoundFilter.kt" to listOf("__etsListFilter"), "RuntimeBoundConsumer.kt" to listOf("__etsArrayIterator"))
    val imports = mapOf("RuntimeBoundModel.kt" to emptyList(),
        "RuntimeBoundProject.kt" to listOf(EtsImport("./RuntimeBoundModel", "RuntimeReadable")),
        "RuntimeBoundFilter.kt" to listOf(EtsImport("./RuntimeBoundModel", "RuntimeReadable")),
        "RuntimeBoundConsumer.kt" to listOf(EtsImport("./RuntimeBoundFilter", "filterBounded"),
            EtsImport("./RuntimeBoundModel", "RuntimeReadable")))
    for (part in visits) {
        val file = part.files.single()
        check(part.imports == imports.getValue(file.sourcePath)) { "Wrong bound/source imports: ${part.imports}" }
        val lines = selection.getValue(file.sourcePath)
        val actualFunctions = lines.filter { it.startsWith("function ") }
        val expected = functions.getValue(file.sourcePath)
        check(actualFunctions.size == expected.size)
        expected.forEachIndexed { index, name -> check(actualFunctions[index].startsWith("function $name<")) }
        val classes = lines.filter { it.startsWith("class ") }
        check(classes.size == if (file.sourcePath == "RuntimeBoundConsumer.kt") 1 else 0)
        if (classes.isNotEmpty()) check(classes.single().startsWith("class __etsIterator<"))
    }
    val members = mutableListOf<EtsMember>()
    walkEts(fixture.project) { if (it is EtsMember) members.add(it) }
    check(members.single().symbolId == fixture.member.symbol.id)
    check(members.single().receiver.type == EtsTypeParameterType("project:T", "T"))
    check(emitEtsModules(fixture.program.copy(files = fixture.program.files.reversed()), StandardLibraryRuntime) == modules)
    for (fault in listOf("missing bound", "unknown bound", "cyclic bound", "unknown member", "wrong signature", "wrong identity")) {
        visits.clear()
        val failure = runCatching { emitEtsModules(boundedFixture(fault).program, provider) }.exceptionOrNull()
        check(failure is InvalidTarget) { "Accepted malformed bounded runtime callback: $fault / $failure" }
        check(visits.isEmpty()) { "Malformed bounded member reached runtime provider: $fault" }
    }
    val output = File(args.single())
    check(!output.exists() && output.mkdirs())
    modules.forEach { (name, text) -> File(output, name).writeText(text) }
    println("PASS four bounded typed modules, exact imports/runtime closure, one provider/module, canonical member identity and order invariance")
    println("PASS six malformed bound/member negatives before runtime selection")
}
