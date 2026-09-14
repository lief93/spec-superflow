package dev.ets

import java.io.File

fun main(arguments: Array<String>) {
    val program = genericMethodFixture()
    val classes = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().associateBy { it.name }
    val functions = program.files.flatMap { it.declarations }.filterIsInstance<EtsFunction>().associateBy { it.name }
    fun method(owner: String, name: String) = classes.getValue(owner).members.filterIsInstance<EtsFunction>().single { it.name == name }
    fun call(function: EtsFunction) = when (val statement = function.body.single()) {
        is EtsReturn -> statement.value as EtsCall
        is EtsExpressionStatement -> statement.expression as EtsCall
        else -> error("Expected call")
    }
    val seen = mutableListOf<EtsProgram>()
    val runtime = EtsRuntimeSupport { part -> seen += part; StandardLibraryRuntime.declarations(part) }
    val modules = emitEtsModules(program, runtime)
    check(modules.keys.toList() == listOf("Holder.ets", "MethodBase.ets", "MethodCalls.ets", "MethodDerived.ets",
        "MethodPort.ets", "Readable.ets", "TokenModel.ets", "TypeCalls.ets"))
    check(seen.size == program.files.size)
    for (part in seen) {
        val file = part.files.single()
        check(file === program.files.single { it.sourcePath == file.sourcePath })
        check(file.declarations.all { it.source.file == file.sourcePath })
    }
    fun imports(name: String) = modules.getValue("$name.ets").lines().filter { it.startsWith("import ") }
    fun expectedImports(vararg names: String) = names.map { "import { $it } from \"./$it\";" }
    check(imports("MethodBase") == expectedImports("MethodPort", "Readable", "TokenModel"))
    check(imports("MethodPort") == expectedImports("Readable"))
    check(imports("TypeCalls") == expectedImports("MethodBase", "TokenModel"))
    check(imports("MethodCalls") == expectedImports("Holder", "MethodBase", "MethodDerived", "MethodPort", "Readable", "TokenModel"))
    check("echo<M>(context: C, value: M): M;" in modules.getValue("MethodPort.ets"))
    check("echo<Value>(context: C, value: Value): Value" in modules.getValue("MethodBase.ets"))
    check("echo<Output>(context: TokenModel, value: Output): Output" in modules.getValue("MethodDerived.ets"))
    check("readChain<View extends Readable<TokenModel>, Element extends View>(reader: Element): TokenModel" in modules.getValue("MethodDerived.ets"))
    check("accept<Bound extends Readable<TokenModel>>(reader: Bound): void" in modules.getValue("MethodBase.ets"))
    check("service.acceptType<TokenModel>();" in modules.getValue("TypeCalls.ets"))
    check("service.echo<string>(context, value)" in modules.getValue("MethodCalls.ets"))
    check("callBounded<Context, Service extends MethodPort<Context>>(service: Service, context: Context, value: number): number" in modules.getValue("MethodCalls.ets"))
    check(modules.values.none { " as " in it || "import { echo }" in it || "import { Value }" in it })
    val echoMethods = listOf("MethodPort", "MethodBase", "MethodDerived").map { method(it, "echo") }
    check(echoMethods.map { it.typeParameters.single().id }.distinct().size == 3)
    check(echoMethods.map { it.typeParameters.single().name } == listOf("M", "Value", "Output"))
    val owners = mapOf("callDirect" to "MethodDerived", "callBase" to "MethodBase", "callInterface" to "MethodPort",
        "callRead" to "MethodDerived", "callChain" to "MethodDerived", "callBounded" to "MethodPort",
        "callInherited" to "MethodBase", "callAccept" to "MethodBase", "callTypeOnly" to "MethodBase")
    for ((name, owner) in owners) {
        val function = functions.getValue(name)
        val invocation = call(function)
        val member = invocation.callee as EtsMember
        val declaration = method(owner, member.name)
        check(member.symbolId == declaration.symbol.id)
        check((member.type as EtsFunctionType).typeParameters.map { it.id } == declaration.typeParameters.map { it.id })
        val receiver = member.receiver as EtsReference
        check(receiver.symbol == function.parameters.first().symbol)
        check(!receiver.symbol.external)
        check(invocation.arguments.map { (it as EtsReference).symbol } == function.parameters.drop(1).map { it.symbol })
        check(invocation.type == function.returnType)
    }
    check((call(functions.getValue("callBounded")).callee as EtsMember).receiver.type is EtsTypeParameterType)
    val baseSignature = call(functions.getValue("callBase")).callee.type as EtsFunctionType
    val baseMethodBinder = method("MethodBase", "echo").typeParameters.single()
    val baseMethodType = EtsTypeParameterType(baseMethodBinder.id, baseMethodBinder.name)
    check(baseSignature.parameters == listOf(classes.getValue("TokenModel").symbol.type, baseMethodType))
    check(baseSignature.result == baseMethodType)
    val boundedSignature = call(functions.getValue("callRead")).callee.type as EtsFunctionType
    val readerBound = boundedSignature.typeParameters.single().upperBound as EtsNamedType
    check(readerBound.symbolId == classes.getValue("Readable").symbol.id)
    check(readerBound.arguments == listOf(classes.getValue("TokenModel").symbol.type))
    check(emitEtsModules(program.copy(files = program.files.reversed()), StandardLibraryRuntime) == modules)

    fun replace(original: EtsDeclaration, replacement: EtsDeclaration) = program.copy(files = program.files.map { file ->
        file.copy(declarations = file.declarations.map { if (it === original) replacement else it })
    })
    var negatives = 0
    fun rejects(value: EtsProgram, source: SourceSpan) {
        seen.clear()
        val failure = runCatching { emitEtsModules(value, runtime) }.exceptionOrNull()
        check(failure is InvalidTarget) { "Expected InvalidTarget, got $failure" }
        check(failure.source == source) { "Wrong source: ${failure.source}; expected $source; $failure" }
        check(seen.isEmpty()) { "Invalid target reached runtime selection" }
        negatives++
    }
    val derived = classes.getValue("MethodDerived")
    fun changedMethod(original: EtsFunction, replacement: EtsFunction) = replace(derived,
        derived.copy(members = derived.members.map { if (it === original) replacement else it }))
    val echo = method("MethodDerived", "echo")
    rejects(changedMethod(echo, echo.copy(overrides = listOf("missing:echo"))), echo.source)
    rejects(changedMethod(echo, echo.copy(typeParameters = echo.typeParameters + EtsTypeParameter("extra:X", "X"))), echo.source)
    val bounded = method("MethodDerived", "readBound")
    rejects(changedMethod(bounded, bounded.copy(typeParameters = listOf(bounded.typeParameters.single().copy(upperBound = null)))), bounded.source)
    rejects(changedMethod(echo, echo.copy(returnType = classes.getValue("TokenModel").symbol.type)), echo.source)
    rejects(changedMethod(echo, echo.copy(parameters = echo.parameters.mapIndexed { index, parameter ->
        if (index == 0) parameter.copy(symbol = parameter.symbol.copy(type = EtsTypes.STRING)) else parameter
    })), echo.source)
    val base = classes.getValue("MethodBase")
    val baseEcho = method("MethodBase", "echo")
    val captured = baseEcho.copy(returnType = EtsTypeParameterType(base.typeParameters.single().id, base.typeParameters.single().name))
    rejects(replace(base, base.copy(members = base.members.map { if (it === baseEcho) captured else it })), baseEcho.source)

    fun changedCall(name: String, transform: (EtsCall) -> EtsCall): EtsProgram {
        val function = functions.getValue(name)
        val invocation = transform(call(function))
        return replace(function, function.copy(body = listOf(when (val statement = function.body.single()) {
            is EtsReturn -> statement.copy(value = invocation)
            is EtsExpressionStatement -> statement.copy(expression = invocation)
            else -> error("Expected call")
        })))
    }
    val direct = call(functions.getValue("callDirect"))
    val directMember = direct.callee as EtsMember
    rejects(changedCall("callDirect") { it.copy(callee = directMember.copy(symbolId = baseEcho.symbol.id)) }, directMember.source)
    val signature = directMember.type as EtsFunctionType
    val renamedBinder = EtsTypeParameter("impostor:Output", "Output")
    val renamed = etsInstantiate(signature, listOf(EtsTypeParameterType(renamedBinder.id, renamedBinder.name)))
        .copy(typeParameters = listOf(renamedBinder))
    rejects(changedCall("callDirect") { it.copy(callee = directMember.copy(type = renamed)) }, directMember.source)
    rejects(changedCall("callDirect") { it.copy(typeArguments = emptyList()) }, direct.source)
    rejects(changedCall("callDirect") { it.copy(typeArguments = listOf(EtsTypes.STRING, EtsTypes.STRING)) }, direct.source)
    val readCall = call(functions.getValue("callRead"))
    rejects(changedCall("callRead") { it.copy(typeArguments = listOf(EtsTypes.STRING)) }, readCall.source)
    rejects(changedCall("callDirect") { it.copy(type = EtsTypes.NUMBER) }, direct.source)
    val wrongArgument = EtsLiteral(5, EtsTypes.NUMBER, SourceSpan("source/MethodCalls.kt", 900, 905))
    rejects(changedCall("callDirect") { it.copy(arguments = listOf(it.arguments.first(), wrongArgument)) }, wrongArgument.source)
    val inherited = call(functions.getValue("callInherited"))
    rejects(changedCall("callInherited") { it.copy(typeArguments = listOf(EtsTypes.STRING)) }, inherited.source)

    val readable = classes.getValue("Readable")
    val model = classes.getValue("TokenModel")
    val accept = method("MethodBase", "accept")
    val boundOnly = base.copy(members = listOf(accept), typeParameters = emptyList(), interfaces = emptyList())
    fun isolated(bound: EtsClass, argument: EtsClass, declaration: EtsClass) = EtsProgram(listOf(bound, argument, declaration)
        .map { EtsFile(it.source.file!!, listOf(it)) })
    rejects(isolated(readable.copy(exported = false), model, boundOnly), accept.source)
    val unknown = accept.copy(typeParameters = listOf(accept.typeParameters.single().copy(upperBound =
        (accept.typeParameters.single().upperBound as EtsNamedType).copy(symbolId = "missing:Readable"))))
    rejects(isolated(readable, model, boundOnly.copy(members = listOf(unknown))), accept.source)
    val typeFunction = functions.getValue("callTypeOnly")
    val typeCall = call(typeFunction)
    val typeMember = typeCall.callee as EtsMember
    val simpleBase = base.copy(members = listOf(method("MethodBase", "acceptType")), interfaces = emptyList())
    val typeProgram = EtsProgram(listOf(EtsFile(simpleBase.source.file!!, listOf(simpleBase)),
        EtsFile(model.source.file!!, listOf(model.copy(exported = false))), EtsFile(typeFunction.source.file!!, listOf(typeFunction))))
    rejects(typeProgram, typeCall.source)
    check((typeMember.type as EtsFunctionType).parameters.isEmpty())
    val colliding = EtsClass("TokenModel", emptyList(), SourceSpan("source/TypeCalls.kt", 200, 205), exported = true)
    rejects(typeProgram.copy(files = typeProgram.files.map { file -> when (file.sourcePath) {
        model.source.file -> file.copy(declarations = listOf(model))
        typeFunction.source.file -> file.copy(declarations = file.declarations + colliding)
        else -> file
    } }), typeCall.source)

    if (arguments.isNotEmpty()) {
        val output = File(arguments.single())
        check(!output.exists()) { "Output exists: $output" }
        check(output.mkdirs())
        modules.forEach { (name, content) -> File(output, name).writeText(content) }
    }
    println("PASS generic method modules: eight files, class/method binders, exact canonical calls, alpha-equivalent overrides, $negatives negatives")
}
