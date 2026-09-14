package dev.ets

import java.io.File

fun main(arguments: Array<String>) {
    val program = genericHeritageFixture()
    val classes = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().associateBy { it.name }
    val functions = program.files.flatMap { it.declarations }.filterIsInstance<EtsFunction>().associateBy { it.name }
    val seen = mutableListOf<EtsProgram>()
    val runtime = EtsRuntimeSupport { part -> seen += part; StandardLibraryRuntime.declarations(part) }
    val modules = emitEtsModules(program, runtime)
    check(modules.keys.toList() == listOf("Consumers.ets", "Holder.ets", "Middle.ets", "ModelHolder.ets", "Readable.ets", "TextHolder.ets", "TokenModel.ets"))
    for (part in seen) {
        val file = part.files.single()
        check(program.files.single { it.sourcePath == file.sourcePath } === file)
        check(file.declarations.all { it.source.file == file.sourcePath })
    }
    check(seen.size == program.files.size)
    fun imports(name: String) = modules.getValue("$name.ets").lines().filter { it.startsWith("import ") }
    check(imports("Holder") == listOf("import { Readable } from \"./Readable\";"))
    check(imports("Middle") == listOf("import { Holder } from \"./Holder\";"))
    check(imports("ModelHolder") == listOf("import { Middle } from \"./Middle\";", "import { TokenModel } from \"./TokenModel\";"))
    check(imports("TextHolder") == listOf("import { Middle } from \"./Middle\";"))
    check(imports("Readable").isEmpty())
    check(imports("Consumers") == listOf("Holder", "Middle", "ModelHolder", "Readable", "TextHolder", "TokenModel")
        .map { "import { $it } from \"./$it\";" })
    check("export interface Readable<T>" in modules.getValue("Readable.ets"))
    check("export class Holder<T> implements Readable<T>" in modules.getValue("Holder.ets"))
    check("export class Middle<T> extends Holder<T>" in modules.getValue("Middle.ets"))
    check("export class ModelHolder extends Middle<TokenModel>" in modules.getValue("ModelHolder.ets"))
    check("export class TextHolder extends Middle<string>" in modules.getValue("TextHolder.ets"))
    check("constructor(value: T)" in modules.getValue("Middle.ets"))
    check("constructor(value: TokenModel)" in modules.getValue("ModelHolder.ets"))
    for (name in listOf("Middle", "ModelHolder", "TextHolder")) check("super(value);" in modules.getValue("$name.ets"))
    check("export function readGeneric<T>(value: Middle<T>): T" in modules.getValue("Consumers.ets"))
    check("export function readBase(base: Holder<TokenModel>): TokenModel" in modules.getValue("Consumers.ets"))
    check("export function readInterface(view: Readable<TokenModel>): TokenModel" in modules.getValue("Consumers.ets"))
    check(modules.values.none { "import { read }" in it || "import { T }" in it })
    val binderIds = classes.values.flatMap { it.typeParameters }.map { it.id } + functions.getValue("readGeneric").typeParameters.map { it.id }
    check(binderIds.size == 4 && binderIds.distinct().size == binderIds.size)
    val read = classes.getValue("Holder").members.filterIsInstance<EtsFunction>().single { it.name == "read" }
    val directReturn = functions.getValue("readDirect").body.single() as EtsReturn
    val directCall = directReturn.value as EtsCall
    val directMember = directCall.callee as EtsMember
    check(directMember.symbolId == read.symbol.id)
    check(directMember.type == EtsFunctionType(emptyList(), classes.getValue("TokenModel").symbol.type))
    check(emitEtsModules(program.copy(files = program.files.reversed()), StandardLibraryRuntime) == modules)

    fun replaced(original: EtsDeclaration, replacement: EtsDeclaration) = program.copy(files = program.files.map { file ->
        file.copy(declarations = file.declarations.map { if (it === original) replacement else it })
    })
    var negatives = 0
    fun rejects(value: EtsProgram, expectedSource: SourceSpan, message: String? = null) {
        seen.clear()
        val failure = runCatching { emitEtsModules(value, runtime) }.exceptionOrNull()
        check(failure is InvalidTarget) { "Expected source-linked target rejection, got $failure" }
        check(failure.source == expectedSource) { "Wrong failure source: ${failure.source}; expected $expectedSource" }
        if (message != null) check(message in failure.message.orEmpty()) { "Expected $message, got $failure" }
        check(seen.isEmpty()) { "Invalid target reached runtime emission" }
        negatives++
    }
    val modelHolder = classes.getValue("ModelHolder")
    val middle = classes.getValue("Middle")
    val readable = classes.getValue("Readable")
    val model = classes.getValue("TokenModel")
    rejects(replaced(modelHolder, modelHolder.copy(baseClass = modelHolder.baseClass!!.copy(arguments = emptyList()))),
        modelHolder.source, "Generic target argument count differs")
    rejects(replaced(modelHolder, modelHolder.copy(baseClass = modelHolder.baseClass!!.copy(symbolId = "missing:Middle"))),
        modelHolder.source, "Unbound target heritage")
    rejects(replaced(middle, middle.copy(baseClass = middle.baseClass!!.copy(arguments = listOf(EtsTypeParameterType("foreign:T", "T"))))),
        middle.source, "Unbound target type parameter")
    rejects(replaced(modelHolder, modelHolder.copy(interfaces = listOf(
        (readable.symbol.type as EtsNamedType).copy(arguments = listOf(EtsTypes.STRING))))),
        modelHolder.source, "Incompatible target ancestor instantiations")
    val boundSource = SourceSpan("source/Bounded.kt", 1, 2)
    val bounded = EtsClass("Bounded", emptyList(), boundSource, exported = true,
        typeParameters = listOf(EtsTypeParameter("bounded:T", "T", model.symbol.type)))
    val badBoundSource = SourceSpan("source/BadBound.kt", 1, 2)
    val badBound = EtsClass("BadBound", emptyList(), badBoundSource,
        baseClass = (bounded.symbol.type as EtsNamedType).copy(arguments = listOf(EtsTypes.STRING)))
    rejects(EtsProgram(listOf(EtsFile(model.source.file!!, listOf(model)), EtsFile(boundSource.file!!, listOf(bounded)),
        EtsFile(badBoundSource.file!!, listOf(badBound)))), badBoundSource, "Generic target argument violates upper bound")
    val direct = functions.getValue("readDirect")
    fun badMember(member: EtsMember) = replaced(direct, direct.copy(body = listOf(directReturn.copy(value = directCall.copy(callee = member)))))
    rejects(badMember(directMember.copy(symbolId = "missing:read")), directMember.source, "identity")
    rejects(badMember(directMember.copy(type = EtsFunctionType(emptyList(), EtsTypes.STRING))), directMember.source, "substitution")
    val typeOnly = EtsFunction("accept", listOf(EtsParameter(EtsSymbol("typeOnly:readable", "view",
        (readable.symbol.type as EtsNamedType).copy(arguments = listOf(EtsTypes.STRING)), SourceSpan("source/TypeOnly.kt", 1, 2)))),
        EtsTypes.VOID, emptyList(), SourceSpan("source/TypeOnly.kt", 1, 2))
    rejects(EtsProgram(listOf(EtsFile(readable.source.file!!, listOf(readable.copy(exported = false))),
        EtsFile(typeOnly.source.file!!, listOf(typeOnly)))), typeOnly.source, "not exported")
    val hiddenModel = replaced(model, model.copy(exported = false))
    rejects(hiddenModel.copy(files = hiddenModel.files.filter { it.sourcePath != "source/Consumers.kt" }),
        modelHolder.source, "not exported")
    val otherSource = SourceSpan("source/Other.kt", 1, 2)
    val unrelatedModel = EtsClass("TokenModel", listOf(EtsFunction("constructor", emptyList(), EtsTypes.VOID,
        emptyList(), otherSource, kind = EtsFunctionKind.CONSTRUCTOR)), otherSource, exported = false)
    val secondType = unrelatedModel.symbol.type
    val expectedType = (classes.getValue("Holder").symbol.type as EtsNamedType).copy(arguments = listOf(secondType))
    val wrongConstructorSource = SourceSpan("source/Wrong.kt", 1, 2)
    val badArgument = EtsNew(model.symbol.type as EtsNamedType,
        listOf(EtsLiteral("same name, different identity", EtsTypes.STRING, wrongConstructorSource)), wrongConstructorSource)
    val wrong = EtsFunction("wrong", emptyList(), EtsTypes.VOID, listOf(EtsExpressionStatement(
        EtsNew(expectedType, listOf(badArgument), wrongConstructorSource))), wrongConstructorSource)
    rejects(program.copy(files = program.files + EtsFile(unrelatedModel.source.file!!, listOf(unrelatedModel)) +
        EtsFile(wrong.source.file!!, listOf(wrong))), wrongConstructorSource, "mismatch")
    val signatureSource = SourceSpan("source/Collision.kt", 1, 2)
    val duplicateName = EtsFunction("accept", listOf(EtsParameter(EtsSymbol("collision:one", "one", model.symbol.type, signatureSource)),
        EtsParameter(EtsSymbol("collision:two", "two", unrelatedModel.symbol.type, signatureSource))), EtsTypes.VOID, emptyList(), signatureSource)
    rejects(EtsProgram(listOf(EtsFile(model.source.file!!, listOf(model)), EtsFile(unrelatedModel.source.file!!,
        listOf(unrelatedModel.copy(exported = true))), EtsFile(signatureSource.file!!, listOf(duplicateName)))),
        signatureSource, "Conflicting module binding")

    if (arguments.isNotEmpty()) {
        val output = File(arguments.single())
        check(!output.exists()) { "Output exists: $output" }
        check(output.mkdirs())
        modules.forEach { (name, content) -> File(output, name).writeText(content) }
    }
    println("PASS generic heritage modules: seven source files, concrete/parameterized parents, inherited member identities, names, $negatives source-linked negatives")
}
