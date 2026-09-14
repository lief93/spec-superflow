package dev.ets.tests.overloadruntime

import dev.ets.*
import java.io.File

private fun overloadProgram(fault: String? = null): EtsProgram {
    fun at(file: String, offset: Int) = SourceSpan("$file.kt", offset, offset + 5)
    val array = EtsNamedType("Array", listOf(EtsTypes.NUMBER))
    val callback = EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.NUMBER)
    val cursor = EtsNamedType("__etsIterator", listOf(EtsTypes.NUMBER), "stdlib:__etsIterator", external = true)
    fun parameter(id: String, name: String, type: EtsType, source: SourceSpan) = EtsParameter(EtsSymbol(id, name, type, source))
    fun helper(name: String, arguments: List<EtsExpression>, result: EtsType, types: List<EtsType>, source: SourceSpan) =
        EtsCall(EtsReference(EtsSymbol("stdlib:$name", name, EtsFunctionType(arguments.map { it.type }, result), source,
            external = true)), arguments, result, source, types)
    fun choice(name: String, offset: Int): EtsFunction {
        val source = at("RuntimeChoices", offset)
        val values = parameter("$name:values", "values", array, source)
        val transform = parameter("$name:transform", "transform", callback, source)
        return EtsFunction(name, listOf(values, transform), array, listOf(EtsReturn(helper("__etsListMap",
            listOf(EtsReference(values.symbol), EtsReference(transform.symbol)), array,
            listOf(EtsTypes.NUMBER, EtsTypes.NUMBER), source), source)), source, exported = true, sourceName = "choose")
    }
    val first = choice("choose", 10)
    val second = choice("chooseNumber", 20)
    fun method(name: String, choice: EtsFunction, offset: Int): EtsFunction {
        val source = at("RuntimeSelector", offset)
        val parameters = choice.parameters.map { parameter("$name:${it.symbol.name}", it.symbol.name, it.symbol.type, source) }
        return EtsFunction(name, parameters, array, listOf(EtsReturn(EtsCall(EtsReference(choice.symbol),
            parameters.map { EtsReference(it.symbol) }, array, source), source)), source,
            kind = EtsFunctionKind.METHOD, sourceName = "select")
    }
    val firstMethod = method("select", first, 20)
    val secondMethod = method("selectNumber", second, 30)
    val selector = EtsClass("RuntimeSelector", listOf(EtsFunction("constructor", emptyList(), EtsTypes.VOID,
        emptyList(), at("RuntimeSelector", 10), kind = EtsFunctionKind.CONSTRUCTOR), firstMethod, secondMethod),
        at("RuntimeSelector", 0), exported = true)
    fun consumer(name: String, target: EtsFunction, member: Boolean, offset: Int): EtsFunction {
        val source = at("RuntimeCalls", offset)
        val receiver = parameter("$name:receiver", "receiver", selector.symbol.type, source)
        val values = parameter("$name:values", "values", array, source)
        val transform = parameter("$name:transform", "transform",
            if (fault == "callback" && name == "viaFirst") EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.NUMBER) else callback, source)
        val symbol = when {
            name != "viaFirst" -> target.symbol
            fault == "unknown id" -> target.symbol.copy(id = "function:missing:10:choose")
            fault == "binding name" -> target.symbol.copy(name = second.name)
            fault == "signature" -> target.symbol.copy(type = EtsFunctionType(listOf(array, callback), EtsTypes.NUMBER))
            else -> target.symbol
        }
        val callee = if (member) EtsMember(EtsReference(receiver.symbol), target.name, target.symbol.type, source,
            if (fault == "member identity" && name == "viaMember") secondMethod.symbol.id else target.symbol.id)
            else EtsReference(symbol, source)
        val mapped = EtsCall(callee, listOf(EtsReference(values.symbol), EtsReference(transform.symbol)), array, source)
        val item = parameter("$name:item", "item", EtsTypes.NUMBER, source)
        val predicate = EtsLambda(listOf(item), listOf(EtsReturn(EtsLiteral(true, EtsTypes.BOOLEAN, source), source)), EtsTypes.BOOLEAN, source)
        val filtered = helper("__etsListFilter", listOf(mapped, predicate, EtsLiteral(false, EtsTypes.BOOLEAN, source)),
            array, listOf(EtsTypes.NUMBER), source)
        return EtsFunction(name, (if (member) listOf(receiver) else emptyList()) + listOf(values, transform), cursor,
            listOf(EtsReturn(helper("__etsArrayIterator", listOf(filtered, EtsLiteral(true, EtsTypes.BOOLEAN, source)),
                cursor, listOf(EtsTypes.NUMBER), source), source)), source, exported = true)
    }
    return EtsProgram(listOf(EtsFile("RuntimeChoices.kt", listOf(
        if (fault == "source identity") first.copy(sourceName = "other") else first, second)),
        EtsFile("RuntimeSelector.kt", listOf(selector)), EtsFile("RuntimeCalls.kt", listOf(
            consumer("viaFirst", first, false, 10), consumer("viaSecond", second, false, 20),
            consumer("viaMember", firstMethod, true, 30)))))
}

fun main(args: Array<String>) {
    val program = overloadProgram()
    val choices = program.files.first().declarations.filterIsInstance<EtsFunction>()
    check(choices.map { it.symbol.type }.distinct().size == 1)
    check(choices.map { it.symbol.id }.distinct().size == 2)
    choices.forEach {
        check(it.symbol.id == "function:${it.source.file}:${it.source.start}:choose")
        check(it.copy(name = "renamedBinding").symbol.id == it.symbol.id)
    }
    val visits = mutableListOf<EtsProgram>()
    val support = linkedMapOf<String, List<String>>()
    val provider = EtsRuntimeSupport { part ->
        visits.add(part)
        StandardLibraryRuntime.declarations(part).also { support[part.files.single().sourcePath] = it }
    }
    val modules = emitEtsModules(program, provider)
    check(visits.size == 3 && visits.all { it.files.size == 1 })
    val expected = mapOf("RuntimeChoices.kt" to listOf("__etsListMap"), "RuntimeSelector.kt" to emptyList(),
        "RuntimeCalls.kt" to listOf("__etsListFilter", "__etsArrayIterator"))
    val imports = mapOf("RuntimeChoices.kt" to emptyList(), "RuntimeSelector.kt" to listOf(
        EtsImport("./RuntimeChoices", "choose"), EtsImport("./RuntimeChoices", "chooseNumber")),
        "RuntimeCalls.kt" to listOf(EtsImport("./RuntimeChoices", "choose"), EtsImport("./RuntimeChoices", "chooseNumber"),
            EtsImport("./RuntimeSelector", "RuntimeSelector")))
    for (part in visits) {
        val file = part.files.single()
        check(file == program.files.single { it.sourcePath == file.sourcePath })
        check(part.imports == imports.getValue(file.sourcePath))
        val lines = support.getValue(file.sourcePath)
        val functions = lines.filter { it.startsWith("function ") }
        check(functions.size == expected.getValue(file.sourcePath).size)
        expected.getValue(file.sourcePath).forEachIndexed { index, name -> check(functions[index].startsWith("function $name<")) }
        check(lines.count { it.startsWith("class ") } == if (file.sourcePath == "RuntimeCalls.kt") 1 else 0)
    }
    check(emitEtsModules(program.copy(files = program.files.reversed()), StandardLibraryRuntime) == modules)
    for (fault in listOf("unknown id", "binding name", "signature", "member identity", "source identity", "callback")) {
        visits.clear()
        val failure = runCatching { emitEtsModules(overloadProgram(fault), provider) }.exceptionOrNull()
        check(failure is InvalidTarget) { "Accepted malformed overload $fault: $failure" }
        check(visits.isEmpty()) { "Malformed overload reached provider: $fault" }
    }
    val directory = File(args.single())
    check(!directory.exists() && directory.mkdirs())
    modules.forEach { (name, text) -> File(directory, name).writeText(text) }
    println("PASS three typed overload modules, preserved source IDs, one provider/module, exact imports/helper closure")
    println("PASS six malformed binding/member/signature negatives before provider; deterministic file order")
}
