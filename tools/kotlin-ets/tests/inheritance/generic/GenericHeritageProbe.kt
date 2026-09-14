@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.config.KotlinCompilerVersion
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    check(KotlinCompilerVersion.VERSION == "2.1.20")
    val program = withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[1], args[0])) { module ->
        File(args[2], "actual.ir").writeText(module.dump())
        val calls = mutableListOf<IrCall>()
        module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
            override fun visitCall(expression: IrCall) { calls += expression; super.visitCall(expression) }
        })
        val classes = module.files.flatMap { it.declarations }.filterIsInstance<IrClass>()
        File(args[2], "official-supertypes.txt").writeText(classes.joinToString("\n") {
            "${it.name}: ${getAllSubstitutedSupertypes(it).map { type -> type.render() }.sorted()}"
        })
        val sink = DiagnosticSink(args[0])
        val backend = EtsBackend(sink, listOf(StandardLibraryRules()))
        val program = backend.lower(module)
        val targets = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().associateBy { it.name }
        val forward = targets.getValue("Forward")
        val nested = targets.getValue("Nested")
        check(forward.baseClass!!.arguments == listOf(EtsTypeParameterType(forward.typeParameters.single().id, "U")))
        check(forward.baseClass!!.symbolId == targets.getValue("Storage").symbol.id)
        check(targets.getValue("IntStore").baseClass!!.arguments == listOf(EtsTypes.NUMBER))
        check(nested.baseClass!!.arguments == listOf(EtsNamedType("Array", listOf(EtsTypeParameterType(nested.typeParameters.single().id, "V")))))
        for (name in listOf("Value", "View", "Left", "Right", "Both")) {
            val target = targets.getValue(name)
            check(target.kind == EtsClassKind.INTERFACE && target.typeParameters.size == 1)
            check(target.members.filterIsInstance<EtsFunction>().all { it.abstract && it.body.isEmpty() })
        }
        val both = targets.getValue("Both")
        check(both.interfaces.map { it.symbolId }.toSet() == setOf(targets.getValue("Left").symbol.id, targets.getValue("Right").symbol.id))
        val nodes = mutableListOf<EtsNode>()
        program.files.forEach { file -> file.declarations.forEach { walkEts(it, nodes::add) } }
        val inherited = calls.filter { it.symbol.owner.isFakeOverride &&
            sourceFile(it.symbol.owner) != null && it.symbol.owner.correspondingPropertySymbol == null }
        check(inherited.size >= 5)
        val bindings = inherited.map { call ->
            val real = call.symbol.owner.collectRealOverrides().single()
            val member = nodes.filterIsInstance<EtsMember>().single {
                it.symbolId != null && it.source.start == call.startOffset && it.source.end == call.endOffset
            }
            val origin = SourceSpan(sourceFile(real)!!.fileEntry.name, real.startOffset, real.endOffset)
            check(member.symbolId == etsFunctionSymbol(real.name.asString(), emptyList(), EtsTypes.VOID, origin).id)
            check((member.type as EtsFunctionType).result == backend.language.type(call.type)) {
                "Inherited signature must match the official call's instantiated result: ${call.dump()}"
            }
            "${symbolName(call.symbol.owner)} -> ${member.symbolId}; ${member.type}"
        }
        File(args[2], "bindings.txt").writeText(bindings.joinToString("\n"))
        val storageReplace = targets.getValue("Storage").members.filterIsInstance<EtsFunction>().single { it.name == "replace" }
        val intReplace = targets.getValue("IntStore").members.filterIsInstance<EtsFunction>().single { it.name == "replace" }
        check(intReplace.parameters.single().symbol.name == "next")
        check(intReplace.overrides == listOf(storageReplace.symbol.id))
        targets.values.filter { it.baseClass != null }.forEach { target ->
            val constructor = target.members.filterIsInstance<EtsFunction>().single { it.kind == EtsFunctionKind.CONSTRUCTOR }
            check((constructor.body.first() as EtsSuperConstructorCall).baseClass == target.baseClass)
        }
        EtsValidator().validate(program)
        println("PASS official instantiated heritage, ${inherited.size} canonical fake-override bindings, interface type parameter identities and forwarded constructor types")
        program
    }
    EtsValidator().validate(program)
    File(args[2], "GenericHeritage.ets").writeText(emitEtsProgram(program, StandardLibraryRuntime))
    println("PASS detached generic heritage target validation and complete emitted module")
}
