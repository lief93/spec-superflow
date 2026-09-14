@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.bridges

import dev.ets.*
import java.io.File
import org.jetbrains.kotlin.backend.common.bridges.generateBridges
import org.jetbrains.kotlin.ir.backend.js.lower.IrBasedFunctionHandle
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.util.*

private class Signature(val function: IrSimpleFunction, private val name: String) {
    override fun equals(other: Any?): Boolean = other is Signature && name == other.name
    override fun hashCode(): Int = name.hashCode()
}

fun main(args: Array<String>) {
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(2)) { module ->
        val owners = module.files.flatMap { it.declarations }.filterIsInstance<IrClass>()
        val methods = owners.flatMap { it.declarations.filterIsInstance<IrSimpleFunction>() }
            .filter { !it.isFakeOverride && it.correspondingPropertySymbol == null }
        val backend = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules()))
        val program = backend.lower(module)
        val classes = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>()
        val targets = classes.flatMap { it.members }.filterIsInstance<EtsFunction>()
        fun id(function: IrSimpleFunction) = etsFunctionSymbol(function.name.asString(), emptyList(), EtsTypes.VOID,
            SourceSpan(function.file.fileEntry.name, function.startOffset, function.endOffset)).id
        val declarations = methods.associateWith { original -> targets.single { it.symbol.id == id(original) } }
        for ((method, implementation) in declarations) {
            check(implementation.parameters.map { it.symbol.name } == method.valueParameters.map { it.name.asString() })
            check(implementation.returnType == backend.language.type(method.returnType))
        }
        for (name in listOf("SpecificProducer", "IdentityProducer", "PresentProducer")) {
            val owner = classes.single { it.name == name }
            check(owner.members.filterIsInstance<EtsFunction>().count { it.kind == EtsFunctionKind.METHOD } == 1)
            check(owner.members.filterIsInstance<EtsFunction>().none { it.sourceName?.startsWith("<bridge:") == true })
        }
        val boundedRead = program.files.flatMap { it.declarations }.filterIsInstance<EtsFunction>().single { it.name == "boundedRead" }
        val read = (boundedRead.body.single() as EtsReturn).value as EtsMember
        val bounded = read.receiver as EtsMember
        check(bounded.receiver.type is EtsTypeParameterType && bounded.receiver !is EtsCast)
        val view = classes.single { it.name == "CovariantView" }.members.filterIsInstance<EtsField>().single()
        val stored = classes.single { it.name == "CovariantValue" }.members.filterIsInstance<EtsField>().single()
        check(bounded.symbolId == view.symbol.id && read.symbolId == stored.symbol.id)
        check(view.source.file != stored.source.file)
        for (wrong in listOf<String?>(null, "wrong:property")) {
            val changed = program.copy(files = program.files.map { file -> file.copy(declarations = file.declarations.map {
                if (it === boundedRead) boundedRead.copy(body = listOf(EtsReturn(read.copy(receiver = bounded.copy(symbolId = wrong)), read.source))) else it
            }) })
            val failure = runCatching { EtsValidator().validate(changed, perFileNames = true) }.exceptionOrNull()
            check(failure is InvalidTarget && failure.source.file == boundedRead.source.file)
        }
        var edges = 0
        var inheritedEdges = 0
        for (method in owners.flatMap { it.declarations.filterIsInstance<IrSimpleFunction>() }.filter { it.correspondingPropertySymbol == null }) {
            val bridges = generateBridges(IrBasedFunctionHandle(method)) {
                Signature(it.function, declarations.getValue(it.function).name)
            }
            val owner = classes.single { it.symbol.id == etsClassSymbol(method.parentAsClass.name.asString(),
                SourceSpan(method.parentAsClass.file.fileEntry.name, method.parentAsClass.startOffset, method.parentAsClass.endOffset)).id }
            for ((from, to) in bridges) {
                val destination = declarations.getValue(to.function)
                if (!method.isFakeOverride) check(destination === declarations.getValue(method))
                val original = declarations.getValue(from.function)
                val bridge = owner.members.filterIsInstance<EtsFunction>().single { it.name == original.name }
                check(bridge.symbol.id != original.symbol.id && bridge.symbol.id != destination.symbol.id)
                check(bridge.overrides.contains(original.symbol.id))
                check(bridge.source == if (method.isFakeOverride) owner.source else destination.source)
                check(bridge.body.size == 1)
                val call = when (val statement = bridge.body.single()) {
                    is EtsReturn -> statement.value as EtsCall
                    is EtsExpressionStatement -> statement.expression as EtsCall
                    else -> error("Bridge must forward exactly once")
                }
                check((call.callee as EtsMember).symbolId == destination.symbol.id)
                check(call.arguments.map { (it as EtsReference).symbol } == bridge.parameters.map { it.symbol })
                check(call.type == bridge.returnType)
                edges++
                if (method.isFakeOverride) inheritedEdges++
            }
        }
        check(edges >= 11 && inheritedEdges >= 4)
        val bareEntries = classes.single { it.name == "BareJoined" }.members.filterIsInstance<EtsFunction>()
            .filter { it.kind == EtsFunctionKind.METHOD }
        check(bareEntries.size == 2 && bareEntries.all { it.abstract && it.body.isEmpty() })
        for (name in listOf("InheritedJoined", "RetainedFakeChoice")) {
            check(classes.single { it.name == name }.members.filterIsInstance<EtsFunction>().none { it.kind == EtsFunctionKind.METHOD })
        }
        val owner = classes.single { it.name == "JoinedText" }
        val bridge = owner.members.filterIsInstance<EtsFunction>().single { it.sourceName?.startsWith("<bridge:") == true }
        val implementation = owner.members.filterIsInstance<EtsFunction>().single { it.kind == EtsFunctionKind.METHOD && it !== bridge }
        fun replace(members: List<EtsClassMember>) = program.copy(files = program.files.map { file ->
            file.copy(declarations = file.declarations.map { if (it === owner) owner.copy(members = members) else it })
        })
        fun reject(label: String, changed: EtsProgram) {
            val error = runCatching { EtsValidator().validate(changed, perFileNames = true) }.exceptionOrNull()
            check(error is InvalidTarget) { "$label: expected InvalidTarget, got $error" }
            check(error.source.file == owner.source.file)
        }
        reject("Missing inherited bridge entry", replace(owner.members.filterNot { it === bridge }))
        reject("Duplicate source method identity", replace(owner.members.map {
            if (it === bridge) bridge.copy(sourceName = implementation.sourceName ?: implementation.name) else it
        }))
        reject("Wrong inherited slot", replace(owner.members.map {
            if (it === bridge) bridge.copy(overrides = implementation.overrides) else it
        }))
        val call = (bridge.body.single() as EtsReturn).value as EtsCall
        val member = call.callee as EtsMember
        reject("Wrong typed forwarding target", replace(owner.members.map {
            if (it === bridge) bridge.copy(body = listOf(EtsReturn(call.copy(callee = member.copy(symbolId = bridge.symbol.id)), call.source))) else it
        }))
        File(args[1], "lowered.ir").writeText(module.dump())
        println("PASS $edges official bridge edges ($inheritedEdges inherited), original method identities/parameters, typed single forwarding and four invalid-target refusals")
        println("PASS uncast bounded property read, cross-file declaration identities and two identity refusals")
    }
}
