package dev.ets

fun checkNestedBindings(program: EtsProgram): Int {
    val classes = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>()
    val node = classes.first { it.name == "Node" }
    val renamed = classes.first { it.sourceName == "Node" }
    val box = classes.first { it.name == "Box" }
    val source = SourceSpan("TypedUse.kt", 10, 20)
    val number = EtsLiteral(1, EtsTypes.NUMBER, source)
    val nodeType = node.symbol.type as EtsNamedType
    val creation = EtsNew(nodeType, listOf(number), source)
    val caller = EtsFunction("typedUse", emptyList(), nodeType, listOf(EtsReturn(creation, source)), source)
    fun pair(declaration: EtsClass, use: EtsFunction) = EtsProgram(listOf(
        EtsFile("Lifted.kt", listOf(declaration)), EtsFile("TypedUse.kt", listOf(use))))
    var rejected = 0
    fun reject(label: String, value: EtsProgram, expected: String, at: SourceSpan = source, modules: Boolean = false) {
        val failure = runCatching {
            if (modules) emitEtsModules(value, StandardLibraryRuntime) else EtsValidator().validate(value, perFileNames = true)
        }.exceptionOrNull()
        check(failure is InvalidTarget && failure.message!!.contains(expected)) { "$label: $failure" }
        check(failure.source == at) { "$label: wrong diagnostic source ${failure.source}, expected $at" }
        rejected++
    }
    fun using(expression: EtsExpression) = caller.copy(returnType = expression.type,
        body = listOf(EtsReturn(expression, source)))
    val renamedType = renamed.symbol.type as EtsNamedType
    reject("Stale emitted type name", pair(renamed, using(EtsNew(renamedType.copy(name = "Node"), listOf(number), source))),
        "name differs")
    reject("Unknown class identity", pair(node, using(creation.copy(classType = nodeType.copy(symbolId = "unknown:Node")))),
        "Unbound target class type")
    reject("Wrong same-source-name identity", EtsProgram(listOf(EtsFile("Lifted.kt", listOf(node, renamed)),
        EtsFile("TypedUse.kt", listOf(using(creation.copy(classType = nodeType.copy(symbolId = renamed.symbol.id))))))), "name differs")
    reject("Stale class value", pair(node, using(EtsReference(node.symbol.copy(name = "Stale"), source))), "Unbound target symbol")
    reject("Duplicate identity after rename", EtsProgram(listOf(EtsFile("First.kt", listOf(renamed)),
        EtsFile("Second.kt", listOf(renamed.copy(name = "Another"))))), "Duplicate target declaration identity", renamed.source)
    val read = node.members.filterIsInstance<EtsFunction>().single { it.name == "read" }
    val member = EtsMember(creation, "read", read.symbol.type, source, read.symbol.id)
    fun call(value: EtsMember) = EtsCall(value, emptyList(), EtsTypes.NUMBER, source)
    reject("Wrong member identity", pair(node, using(call(member.copy(symbolId = "wrong:read")))), "identity")
    reject("Stale member signature", pair(node, using(call(member.copy(type = EtsFunctionType(emptyList(), EtsTypes.STRING))))),
        "substitution")
    val boxType = EtsNamedType(box.name, listOf(EtsTypes.NUMBER), box.symbol.id)
    reject("Missing generic arguments", pair(box, using(EtsNew(boxType.copy(arguments = emptyList()), listOf(number), source))),
        "argument count")
    reject("Unbound generic owner", pair(box, using(EtsNew(boxType.copy(arguments = listOf(EtsTypeParameterType("wrong:T", "T"))),
        listOf(number), source))), "Unbound target type parameter")
    reject("Private class value dependency", pair(node.copy(exported = false), caller), "not exported", modules = true)
    val typeOnly = EtsFunction("typedOnly", listOf(EtsParameter(EtsSymbol("typed:parameter", "value", nodeType, source))),
        EtsTypes.VOID, emptyList(), source)
    reject("Private class type dependency", pair(node.copy(exported = false), typeOnly), "not exported", modules = true)

    val moved = emitEtsModules(pair(node.copy(exported = true), caller), StandardLibraryRuntime)
    check(moved.keys == setOf("Lifted.ets", "TypedUse.ets"))
    check("from \"./Lifted\"" in moved.getValue("TypedUse.ets"))
    check(node.source.file != "Lifted.kt")
    val interfaceSource = SourceSpan("OriginalInterface.kt", 30, 40)
    val method = EtsFunction("read", emptyList(), EtsTypes.NUMBER, emptyList(), interfaceSource,
        kind = EtsFunctionKind.METHOD, abstract = true)
    val port = EtsClass("Port_0", listOf(method), interfaceSource, exported = true, kind = EtsClassKind.INTERFACE, sourceName = "Port")
    check(port.symbol.id == etsClassSymbol("Port", interfaceSource).id)
    val parameter = EtsSymbol("port:argument", "value", port.symbol.type, source)
    val usePort = EtsFunction("usePort", listOf(EtsParameter(parameter)), EtsTypes.NUMBER,
        listOf(EtsReturn(EtsCall(EtsMember(EtsReference(parameter), "read", method.symbol.type, source, method.symbol.id),
            emptyList(), EtsTypes.NUMBER, source), source)), source)
    val interfaceModules = emitEtsModules(pair(port, usePort), StandardLibraryRuntime)
    check("interface Port_0" in interfaceModules.getValue("Lifted.ets"))
    check("import { Port_0 } from \"./Lifted\"" in interfaceModules.getValue("TypedUse.ets"))
    return rejected
}
