package dev.ets.tests.generics

import dev.ets.*

fun main(args: Array<String>) {
    val program = withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(1)) { module ->
        EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())).lower(module)
    }
    val declarations = program.files.flatMap { it.declarations }
    val functions = declarations.filterIsInstance<EtsFunction>().associateBy { it.name }
    val classes = declarations.filterIsInstance<EtsClass>().associateBy { it.name }
    val nodes = mutableListOf<EtsNode>()
    declarations.forEach { walkEts(it, nodes::add) }
    check(nodes.filterIsInstance<EtsBlock>().none { it.statements.isEmpty() }) {
        "Removed local declarations must not leave empty target blocks"
    }
    val scopedNodes = mutableListOf<EtsNode>()
    walkEts(functions.getValue("scopedLocal"), scopedNodes::add)
    check(scopedNodes.filterIsInstance<EtsBlock>().any { block ->
        block.statements.any { it is EtsVariable && it.symbol.name == "value" }
    }) { "Nonempty shadowing scope must remain a target block" }
    val identity = functions.getValue("identity")
    val parameter = identity.typeParameters.single()
    val t = EtsTypeParameterType(parameter.id, "T")
    check(identity.parameters.single().symbol.type == t && identity.returnType == t)
    check(functions.getValue("choose").typeParameters.single().id != parameter.id)
    val calls = nodes.filterIsInstance<EtsCall>()
    val identities = calls.filter { (it.callee as? EtsReference)?.symbol?.id == identity.symbol.id }
    check(identities.map { it.typeArguments.single() }.toSet() == setOf(EtsTypes.NUMBER, EtsTypes.STRING))
    check(identities.all { (it.callee as EtsReference).symbol == identity.symbol })
    check(calls.any { (it.callee as? EtsReference)?.symbol?.name == "choose" && it.arguments.last() is EtsUndefined })
    val box = classes.getValue("Box")
    val boxNumber = EtsNamedType("Box", listOf(EtsTypes.NUMBER), box.symbol.id)
    val construction = nodes.filterIsInstance<EtsNew>().first { it.classType == boxNumber }
    val mapped = calls.first { (it.callee as? EtsMember)?.name == "mapped" }
    val mappedSignature = mapped.callee.type as EtsFunctionType
    check((mappedSignature.parameters.single() as EtsFunctionType).parameters.single() == EtsTypes.NUMBER)
    check(etsInstantiate(mappedSignature, mapped.typeArguments).result == boxNumber)
    check(mapped.type == boxNumber)
    check(nodes.filterIsInstance<EtsMember>().any { it.name == "observed" && it.type == EtsTypes.NUMBER })
    check(classes.values.all { (it.symbol.type as EtsNamedType).symbolId == it.symbol.id })

    val captured = functions.getValue("capturedLocal")
    val capturedNodes = mutableListOf<EtsNode>()
    walkEts(captured, capturedNodes::add)
    val liftedSymbol = (capturedNodes.filterIsInstance<EtsCall>().single().callee as EtsReference).symbol
    val lifted = functions.values.single { it.symbol.id == liftedSymbol.id }
    check(captured.typeParameters.single().id != lifted.typeParameters.single().id)
    check(lifted.parameters.single().symbol.type == lifted.returnType)
    check((lifted.returnType as EtsTypeParameterType).id == lifted.typeParameters.single().id)
    val localBox = classes.getValue("LocalBox")
    val liftedMember = localBox.members.filterIsInstance<EtsFunction>().single { it.static }
    check(liftedMember.typeParameters.single().id != localBox.typeParameters.single().id)
    check(calls.any { (it.callee as? EtsMember)?.let { member ->
        member.name == liftedMember.name && (member.receiver as? EtsReference)?.symbol == localBox.symbol
    } == true })

    val other = EtsTypeParameterType("other:T", "T")
    check(etsSubstitute(other, mapOf(t.id to EtsTypes.NUMBER)) == other)
    check(!etsAssignable(t, other))
    val nested = EtsFunctionType(listOf(t), other, listOf(parameter))
    check(etsSubstitute(nested, mapOf(t.id to EtsTypes.NUMBER, other.id to EtsTypes.STRING)) ==
        nested.copy(result = EtsTypes.STRING))
    check(etsSubstitute(EtsNullableType(t), mapOf(t.id to EtsNullableType(EtsTypes.STRING))) == EtsNullableType(EtsTypes.STRING))
    check(!etsAssignable(boxNumber, boxNumber.copy(arguments = listOf(EtsTypes.OBJECT))))
    check(!etsAssignable(boxNumber, boxNumber.copy(symbolId = "another:Box")))

    // Official lifting copies captured type parameters onto class-owned static helpers.
    val staticSource = SourceSpan("static.kt", 1, 2)
    val classT = EtsTypeParameter("static:class:T", "T")
    val methodT = EtsTypeParameter("static:method:T", "T")
    val methodType = EtsTypeParameterType(methodT.id, methodT.name)
    val argument = EtsSymbol("static:argument", "value", methodType, staticSource)
    val helper = EtsFunction("lifted", listOf(EtsParameter(argument)), methodType,
        listOf(EtsReturn(EtsReference(argument), staticSource)), staticSource,
        kind = EtsFunctionKind.METHOD, static = true, typeParameters = listOf(methodT))
    val container = EtsClass("Container", listOf(helper), staticSource, typeParameters = listOf(classT))
    val staticCall = EtsCall(EtsMember(EtsReference(container.symbol), helper.name, helper.symbol.type, staticSource),
        listOf(EtsLiteral(2, EtsTypes.NUMBER, staticSource)), EtsTypes.NUMBER, staticSource, listOf(EtsTypes.NUMBER))
    val caller = EtsFunction("staticCaller", emptyList(), EtsTypes.NUMBER,
        listOf(EtsReturn(staticCall, staticSource)), staticSource)
    val staticProgram = EtsProgram(listOf(EtsFile("static.kt", listOf(container, caller))))
    EtsValidator().validate(staticProgram)
    try {
        EtsValidator().validate(staticProgram.copy(files = listOf(EtsFile("static.kt", listOf(
            container.copy(members = listOf(helper.copy(returnType = EtsTypeParameterType(classT.id, classT.name)))))))))
        error("Accepted original class type parameter in a static helper")
    } catch (failure: InvalidTarget) {
        check(failure.message?.contains("Unbound target type parameter") == true)
    }

    val source = SourceSpan("negative.kt", 1, 2)
    var rejected = 0
    fun rejects(value: EtsExpression, expected: String) {
        val probe = EtsFunction("negative", emptyList(), EtsTypes.VOID,
            listOf(EtsExpressionStatement(value)), source)
        val changed = program.copy(files = program.files + EtsFile("negative.kt", listOf(probe)))
        try {
            EtsValidator().validate(changed)
            error("Accepted malformed generic target: $value")
        } catch (failure: InvalidTarget) {
            check(failure.message?.contains(expected) == true) { "Wrong rejection: ${failure.message}; expected $expected" }
            rejected++
        }
    }
    val number = EtsLiteral(1, EtsTypes.NUMBER, source)
    val text = EtsLiteral("wrong", EtsTypes.STRING, source)
    val call = EtsCall(EtsReference(identity.symbol), listOf(number), EtsTypes.NUMBER, source, listOf(EtsTypes.NUMBER))
    rejects(call.copy(typeArguments = emptyList()), "argument count")
    rejects(call.copy(typeArguments = listOf(EtsTypes.NUMBER, EtsTypes.STRING)), "argument count")
    rejects(call.copy(arguments = emptyList()), "instantiated signature")
    rejects(call.copy(arguments = listOf(text)), "type mismatch")
    rejects(call.copy(type = EtsTypes.STRING), "instantiated signature")
    rejects(call.copy(type = EtsTypes.OBJECT), "instantiated signature")
    rejects(call.copy(typeArguments = listOf(other)), "Unbound target type parameter")
    rejects(call.copy(callee = EtsReference(identity.symbol.copy(type = etsInstantiate(identity.symbol.type as EtsFunctionType, call.typeArguments)))), "Unbound target symbol")
    val standalone = construction.copy(arguments = listOf(number))
    rejects(standalone.copy(arguments = listOf(text)), "type mismatch")
    rejects(standalone.copy(classType = boxNumber.copy(arguments = emptyList())), "argument count")
    rejects(standalone.copy(classType = boxNumber.copy(symbolId = "wrong:Box")), "Unbound target class type")
    rejects(standalone.copy(classType = boxNumber.copy(name = "Wrong")), "name differs")
    rejects(EtsMember(standalone, "value", EtsTypes.STRING, source), "receiver substitution")
    rejects(EtsMember(standalone, "missing", EtsTypes.NUMBER, source), "Unknown target class member")
    val bounded = functions.getValue("nonNull")
    rejects(EtsCall(EtsReference(bounded.symbol), listOf(EtsLiteral(null, EtsTypes.NULL, source)),
        EtsTypes.NULL, source, listOf(EtsTypes.NULL)), "upper bound")
    rejects(EtsLambda(emptyList(), listOf(identity), EtsTypes.VOID, source), "Nested target function")
    rejects(EtsLambda(emptyList(), listOf(EtsFunction("inside", emptyList(), EtsTypes.VOID,
        emptyList(), source)), EtsTypes.VOID, source), "Nested target function")
    EtsValidator().validate(program)
    println("PASS: genuine IR generic identities, actual function/class/member substitutions, defaults and $rejected malformed targets rejected")
}
