package dev.ets.tests.methodruntime

import dev.ets.*
import java.io.File

private fun methodProgram(fault: String? = null): EtsProgram {
    fun at(file: String, offset: Int = 10) = SourceSpan("$file.kt", offset, offset + 5)
    fun use(parameter: EtsTypeParameter) = EtsTypeParameterType(parameter.id, parameter.name)
    fun array(type: EtsType) = EtsNamedType("Array", listOf(type))
    fun cursor(type: EtsType) = EtsNamedType("__etsIterator", listOf(type), "stdlib:__etsIterator", external = true)
    fun named(declaration: EtsClass, argument: EtsType) = (declaration.symbol.type as EtsNamedType).copy(arguments = listOf(argument))
    fun parameter(id: String, name: String, type: EtsType, source: SourceSpan) = EtsParameter(EtsSymbol(id, name, type, source))
    fun helper(name: String, arguments: List<EtsExpression>, result: EtsType, types: List<EtsType>, source: SourceSpan) =
        EtsCall(EtsReference(EtsSymbol("stdlib:$name", name, EtsFunctionType(arguments.map { it.type }, result), source,
            external = true)), arguments, result, source, types)
    fun convert(file: String, owner: EtsTypeParameter, methodName: String, abstract: Boolean,
        overrides: List<String> = emptyList()): EtsFunction {
        val source = at(file, 20)
        val method = EtsTypeParameter("$file:method:$methodName", methodName,
            if (fault == "override bound" && file == "RuntimeMethodDerived") EtsTypes.NUMBER else null)
        val result = if (fault == "override captures class" && file == "RuntimeMethodDerived") use(owner) else use(method)
        val values = parameter("$file:values", "values", array(use(owner)), source)
        val transform = parameter("$file:transform", "transform", EtsFunctionType(listOf(use(owner)), result), source)
        return EtsFunction("convert", listOf(values, transform), array(result), if (abstract) emptyList() else listOf(EtsReturn(
            helper("__etsListMap", listOf(EtsReference(values.symbol), EtsReference(transform.symbol)), array(result),
                listOf(use(owner), result), source), source)), source, kind = EtsFunctionKind.METHOD,
            typeParameters = listOf(method), abstract = abstract, overrides = overrides)
    }
    val portBinder = EtsTypeParameter("port:C", "C")
    val portMethod = convert("RuntimeMethodPort", portBinder, "R", true)
    val port = EtsClass("RuntimeMethodPort", listOf(portMethod), at("RuntimeMethodPort"), exported = true,
        typeParameters = listOf(portBinder), kind = EtsClassKind.INTERFACE)
    val baseBinder = EtsTypeParameter("base:C", "C")
    val baseMethod = convert("RuntimeMethodBase", baseBinder, "B", false, listOf(portMethod.symbol.id))
    val baseConstructor = EtsFunction("constructor", emptyList(), EtsTypes.VOID, emptyList(), at("RuntimeMethodBase", 30),
        kind = EtsFunctionKind.CONSTRUCTOR)
    val base = EtsClass("RuntimeMethodBase", listOf(baseConstructor, baseMethod), at("RuntimeMethodBase"), exported = true,
        typeParameters = listOf(baseBinder), interfaces = listOf(named(port, use(baseBinder))))
    val derivedBinder = EtsTypeParameter("derived:C", "C")
    val derivedMethod = convert("RuntimeMethodDerived", derivedBinder, "D", false, listOf(baseMethod.symbol.id))
    val parent = named(base, use(derivedBinder))
    val constructor = EtsFunction("constructor", emptyList(), EtsTypes.VOID,
        listOf(EtsSuperConstructorCall(parent, emptyList(), at("RuntimeMethodDerived", 30))), at("RuntimeMethodDerived", 30),
        kind = EtsFunctionKind.CONSTRUCTOR)
    val derived = EtsClass("RuntimeMethodDerived", listOf(constructor, derivedMethod), at("RuntimeMethodDerived"),
        exported = true, typeParameters = listOf(derivedBinder), baseClass = parent)

    fun consumer(name: String, declaration: EtsClass, owner: EtsTypeParameter, method: EtsFunction, offset: Int): EtsFunction {
        val source = at("RuntimeMethodCalls", offset)
        val c = EtsTypeParameter("$name:C", "C")
        val r = EtsTypeParameter("$name:R", "R")
        val receiver = parameter("$name:receiver", "receiver", named(declaration, use(c)), source)
        val values = parameter("$name:values", "values", array(use(c)), source)
        val transform = parameter("$name:transform", "transform",
            EtsFunctionType(listOf(if (fault == "callback input" && name == "viaPort") use(r) else use(c)), use(r)), source)
        val signature = etsSubstitute(method.symbol.type, mapOf(owner.id to
            if (fault == "class substitution" && name == "viaPort") use(r) else use(c)))
        val member = EtsMember(EtsReference(receiver.symbol), method.name, signature, source,
            if (fault == "foreign member" && name == "viaPort") baseMethod.symbol.id else method.symbol.id)
        val arguments = when {
            fault == "method arity" && name == "viaPort" -> emptyList()
            fault == "method captures class" && name == "viaPort" -> listOf(use(c))
            else -> listOf(use(r))
        }
        val converted = EtsCall(member, listOf(EtsReference(values.symbol), EtsReference(transform.symbol)), array(use(r)), source, arguments)
        val item = parameter("$name:item", "item", use(r), source)
        val predicate = EtsLambda(listOf(item), listOf(EtsReturn(EtsLiteral(true, EtsTypes.BOOLEAN, source), source)), EtsTypes.BOOLEAN, source)
        val filtered = helper("__etsListFilter", listOf(converted, predicate, EtsLiteral(true, EtsTypes.BOOLEAN, source)),
            array(use(r)), listOf(use(r)), source)
        val result = helper("__etsArrayIterator", listOf(filtered, EtsLiteral(true, EtsTypes.BOOLEAN, source)), cursor(use(r)), listOf(use(r)), source)
        return EtsFunction(name, listOf(receiver, values, transform), cursor(use(r)), listOf(EtsReturn(result, source)), source,
            exported = true, typeParameters = listOf(c, r))
    }
    return EtsProgram(listOf(EtsFile("RuntimeMethodPort.kt", listOf(port)), EtsFile("RuntimeMethodBase.kt", listOf(base)),
        EtsFile("RuntimeMethodDerived.kt", listOf(derived)), EtsFile("RuntimeMethodCalls.kt", listOf(
            consumer("viaPort", port, portBinder, portMethod, 10), consumer("viaBase", base, baseBinder, baseMethod, 20),
            consumer("viaDerived", derived, derivedBinder, derivedMethod, 30)))))
}

fun main(args: Array<String>) {
    val program = methodProgram()
    val visits = mutableListOf<EtsProgram>()
    val selected = linkedMapOf<String, List<String>>()
    val provider = EtsRuntimeSupport { part ->
        visits.add(part)
        StandardLibraryRuntime.declarations(part).also { selected[part.files.single().sourcePath] = it }
    }
    val modules = emitEtsModules(program, provider)
    val functions = mapOf("RuntimeMethodPort.kt" to emptyList(), "RuntimeMethodBase.kt" to listOf("__etsListMap"),
        "RuntimeMethodDerived.kt" to listOf("__etsListMap"), "RuntimeMethodCalls.kt" to listOf("__etsListFilter", "__etsArrayIterator"))
    val imports = mapOf("RuntimeMethodPort.kt" to emptyList(),
        "RuntimeMethodBase.kt" to listOf(EtsImport("./RuntimeMethodPort", "RuntimeMethodPort")),
        "RuntimeMethodDerived.kt" to listOf(EtsImport("./RuntimeMethodBase", "RuntimeMethodBase")),
        "RuntimeMethodCalls.kt" to listOf(EtsImport("./RuntimeMethodBase", "RuntimeMethodBase"),
            EtsImport("./RuntimeMethodDerived", "RuntimeMethodDerived"), EtsImport("./RuntimeMethodPort", "RuntimeMethodPort")))
    check(modules.keys == functions.keys.map { it.removeSuffix(".kt") + ".ets" }.toSet())
    check(visits.size == 4 && visits.all { it.files.size == 1 })
    check(visits.map { it.files.single().sourcePath }.toSet() == functions.keys)
    for (part in visits) {
        val file = part.files.single()
        check(file == program.files.single { it.sourcePath == file.sourcePath })
        check(part.imports == imports.getValue(file.sourcePath)) { "Wrong generic member imports: ${part.imports}" }
        val lines = selected.getValue(file.sourcePath)
        val actual = lines.filter { it.startsWith("function ") }
        val expected = functions.getValue(file.sourcePath)
        check(actual.size == expected.size)
        expected.forEachIndexed { index, name -> check(actual[index].startsWith("function $name<")) }
        val classes = lines.filter { it.startsWith("class ") }
        check(classes.size == if (file.sourcePath == "RuntimeMethodCalls.kt") 1 else 0)
        if (classes.isNotEmpty()) check(classes.single().startsWith("class __etsIterator<"))
    }
    val canonical = program.files.take(3).map { (it.declarations.single() as EtsClass).members.filterIsInstance<EtsFunction>().single { it.name == "convert" } }
    check(canonical.map { it.typeParameters.single().id }.distinct().size == 3)
    check(canonical.map { it.typeParameters.single().name } == listOf("R", "B", "D"))
    val members = mutableListOf<EtsMember>()
    program.files.last().declarations.forEach { declaration -> walkEts(declaration) { if (it is EtsMember) members.add(it) } }
    check(members.map { it.symbolId } == canonical.map { it.symbol.id })
    check(emitEtsModules(program.copy(files = program.files.reversed()), StandardLibraryRuntime) == modules)
    for (fault in listOf("method arity", "method captures class", "callback input", "class substitution", "foreign member",
        "override bound", "override captures class")) {
        visits.clear()
        val failure = runCatching { emitEtsModules(methodProgram(fault), provider) }.exceptionOrNull()
        check(failure is InvalidTarget) { "Accepted invalid generic member: $fault / $failure" }
        check(visits.isEmpty()) { "Invalid generic member reached runtime selection: $fault" }
    }
    val output = File(args.single())
    check(!output.exists() && output.mkdirs())
    modules.forEach { (name, text) -> File(output, name).writeText(text) }
    println("PASS four typed generic member modules, distinct override binders, canonical direct/base/interface calls, exact imports/helper closure")
    println("PASS seven malformed binder/call/override negatives before runtime provider; one provider/module and stable module order")
}
