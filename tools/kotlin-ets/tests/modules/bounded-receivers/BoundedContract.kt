package dev.ets

import java.io.File

fun main(arguments: Array<String>) {
    val program = boundedReceiverFixture()
    val classes = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().associateBy { it.name }
    val functions = program.files.flatMap { it.declarations }.filterIsInstance<EtsFunction>().associateBy { it.name }
    val seen = mutableListOf<EtsProgram>()
    val runtime = EtsRuntimeSupport { part -> seen += part; StandardLibraryRuntime.declarations(part) }
    val modules = emitEtsModules(program, runtime)
    check(modules.keys.toList() == listOf("BoundedCalls.ets", "Holder.ets", "Middle.ets", "ModelHolder.ets", "Readable.ets",
        "ReaderBox.ets", "Signatures.ets", "TextHolder.ets", "TokenModel.ets"))
    check(seen.size == program.files.size)
    for (part in seen) {
        val file = part.files.single()
        check(program.files.single { it.sourcePath == file.sourcePath } === file)
        check(file.declarations.all { it.source.file == file.sourcePath })
    }
    fun imports(file: String) = modules.getValue("$file.ets").lines().filter { it.startsWith("import ") }
    val boundImports = listOf("Middle", "Readable", "TokenModel").map { "import { $it } from \"./$it\";" }
    check(imports("BoundedCalls") == boundImports)
    check(imports("Signatures") == boundImports) { "Bound-only signatures lost their imports" }
    check(imports("ReaderBox") == listOf("Readable", "TokenModel").map { "import { $it } from \"./$it\";" })
    val calls = modules.getValue("BoundedCalls.ets")
    check("readClass<R extends Middle<TokenModel>>(reader: R): TokenModel" in calls)
    check("readInterface<R extends Readable<TokenModel>>(reader: R): TokenModel" in calls)
    check("readParametric<V, R extends Readable<V>>(reader: R): V" in calls)
    check("readChain<R extends Middle<TokenModel>, S extends R>(reader: S): TokenModel" in calls)
    check(calls.lines().count { it.trim() == "return reader.read();" } == 4)
    val boxText = modules.getValue("ReaderBox.ets")
    check("export class ReaderBox<R extends Readable<TokenModel>>" in boxText)
    check("constructor(reader: R)" in boxText && "return this.reader.read();" in boxText)
    check("acceptInterface<R extends Readable<TokenModel>>(reader: R): void" in modules.getValue("Signatures.ets"))
    check(modules.values.none { "import { read }" in it || " as " in it || "import { R }" in it || "import { S }" in it })
    val holderRead = classes.getValue("Holder").members.filterIsInstance<EtsFunction>().single { it.name == "read" }
    val interfaceRead = classes.getValue("Readable").members.filterIsInstance<EtsFunction>().single { it.name == "read" }
    fun member(function: EtsFunction) = ((function.body.single() as EtsReturn).value as EtsCall).callee as EtsMember
    for (name in listOf("readClass", "readInterface", "readParametric", "readChain")) {
        val function = functions.getValue(name)
        val value = member(function)
        check(value.receiver.type is EtsTypeParameterType)
        check((value.receiver as EtsReference).symbol.external.not())
        check(value.symbolId == if (name == "readClass" || name == "readChain") holderRead.symbol.id else interfaceRead.symbol.id)
        check(value.type == EtsFunctionType(emptyList(), function.returnType))
        check(function.parameters.single().symbol.name == "reader")
    }
    check(emitEtsModules(program.copy(files = program.files.reversed()), StandardLibraryRuntime) == modules)

    fun replaced(original: EtsDeclaration, replacement: EtsDeclaration) = program.copy(files = program.files.map { file ->
        file.copy(declarations = file.declarations.map { if (it === original) replacement else it })
    })
    var negatives = 0
    fun rejects(value: EtsProgram, source: SourceSpan, message: String? = null) {
        seen.clear()
        val failure = runCatching { emitEtsModules(value, runtime) }.exceptionOrNull()
        check(failure is InvalidTarget) { "Expected source-linked target rejection, got $failure" }
        check(failure.source == source) { "Wrong failure source: ${failure.source}; expected $source" }
        if (message != null) check(message in failure.message.orEmpty()) { "Expected $message, got $failure" }
        check(seen.isEmpty()) { "Invalid bound receiver reached runtime emission" }
        negatives++
    }
    val interfaceFunction = functions.getValue("readInterface")
    val originalMember = member(interfaceFunction)
    val originalReturn = interfaceFunction.body.single() as EtsReturn
    val originalCall = originalReturn.value as EtsCall
    fun changedMember(value: EtsMember) = replaced(interfaceFunction, interfaceFunction.copy(body = listOf(
        originalReturn.copy(value = originalCall.copy(callee = value)))))
    rejects(changedMember(originalMember.copy(name = "missing")), originalMember.source)
    rejects(changedMember(originalMember.copy(symbolId = null)), originalMember.source)
    rejects(changedMember(originalMember.copy(symbolId = holderRead.symbol.id)), originalMember.source, "identity")
    rejects(changedMember(originalMember.copy(type = EtsFunctionType(emptyList(), EtsTypes.STRING))), originalMember.source, "substitution")
    fun changedBound(bound: EtsType?) = replaced(interfaceFunction, interfaceFunction.copy(typeParameters = listOf(
        interfaceFunction.typeParameters.single().copy(upperBound = bound))))
    val originalBound = interfaceFunction.typeParameters.single().upperBound as EtsNamedType
    rejects(changedBound(null), interfaceFunction.source)
    rejects(changedBound(originalBound.copy(symbolId = "missing:Readable")), interfaceFunction.source)
    rejects(changedBound(originalBound.copy(external = true)), interfaceFunction.source)
    rejects(changedBound(EtsNullableType(originalBound)), interfaceFunction.source)
    val chain = functions.getValue("readChain")
    val first = chain.typeParameters.first()
    val second = chain.typeParameters.last()
    rejects(replaced(chain, chain.copy(typeParameters = listOf(first.copy(upperBound = EtsTypeParameterType(second.id, second.name)),
        second))), chain.source)
    val parametric = functions.getValue("readParametric")
    rejects(replaced(parametric, parametric.copy(typeParameters = parametric.typeParameters.map { parameter ->
        if (parameter.id == parametric.typeParameters.last().id)
            parameter.copy(upperBound = originalBound.copy(arguments = listOf(EtsTypes.STRING))) else parameter
    })), parametric.source)

    val readable = classes.getValue("Readable")
    val model = classes.getValue("TokenModel")
    val signature = functions.getValue("acceptInterface")
    fun isolated(bound: EtsClass, argument: EtsClass, use: EtsDeclaration) = EtsProgram(listOf(
        EtsFile(bound.source.file!!, listOf(bound)), EtsFile(argument.source.file!!, listOf(argument)),
        EtsFile(use.source.file!!, listOf(use))))
    rejects(isolated(readable.copy(exported = false), model, signature), signature.source, "not exported")
    rejects(isolated(readable, model.copy(exported = false), signature), signature.source, "not exported")
    val box = classes.getValue("ReaderBox")
    rejects(isolated(readable.copy(exported = false), model, box), box.source, "not exported")
    val other = EtsClass("Readable", emptyList(), SourceSpan("source/Other.kt", 1, 2), exported = true,
        typeParameters = listOf(EtsTypeParameter("other:T", "T")), kind = EtsClassKind.INTERFACE)
    val secondSource = SourceSpan(signature.source.file, 100, 105)
    val secondBinder = EtsTypeParameter("acceptOther:R", "R",
        (other.symbol.type as EtsNamedType).copy(arguments = listOf(model.symbol.type)))
    val secondSignature = EtsFunction("acceptOther", listOf(EtsParameter(EtsSymbol("acceptOther:reader", "reader",
        EtsTypeParameterType(secondBinder.id, secondBinder.name), secondSource))), EtsTypes.VOID, emptyList(), secondSource,
        exported = true, typeParameters = listOf(secondBinder))
    val signatureProgram = isolated(readable, model, signature)
    rejects(signatureProgram.copy(files = signatureProgram.files.map { file ->
        if (file.sourcePath == signature.source.file) file.copy(declarations = file.declarations + secondSignature) else file
    } + EtsFile(other.source.file!!, listOf(other))), secondSignature.source, "Conflicting module binding")

    if (arguments.isNotEmpty()) {
        val output = File(arguments.single())
        check(!output.exists()) { "Output exists: $output" }
        check(output.mkdirs())
        modules.forEach { (name, content) -> File(output, name).writeText(content) }
    }
    println("PASS bounded receiver modules: source bounds, canonical member IDs, substituted signatures, bound-only imports, $negatives negatives")
}
