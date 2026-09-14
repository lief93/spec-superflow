@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.config.KotlinCompilerVersion
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrGetValue
import org.jetbrains.kotlin.ir.symbols.IrTypeParameterSymbol
import org.jetbrains.kotlin.ir.types.IrSimpleType
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    check(KotlinCompilerVersion.VERSION == "2.1.20")
    val program = withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[1], args[0])) { module ->
        File(args[2], "actual.ir").writeText(module.dump())
        val calls = mutableListOf<IrCall>()
        module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
            override fun visitCall(expression: IrCall) {
                if ((expression.dispatchReceiver?.type as? IrSimpleType)?.classifier is IrTypeParameterSymbol) calls += expression
                super.visitCall(expression)
            }
        })
        check(calls.size == 8) { "Expected eight original bounded member receiver calls, got ${calls.size}" }
        val backend = EtsBackend(DiagnosticSink(args[0]), listOf(StandardLibraryRules()))
        val program = backend.lower(module)
        val nodes = mutableListOf<EtsNode>()
        program.files.forEach { file -> file.declarations.forEach { walkEts(it, nodes::add) } }
        val bindings = calls.map { call ->
            val real = call.symbol.owner.collectRealOverrides().single()
            val member = nodes.filterIsInstance<EtsMember>().single {
                it.symbolId != null && it.source.start == call.startOffset && it.source.end == call.endOffset
            }
            val origin = SourceSpan(sourceFile(real)!!.fileEntry.name, real.startOffset, real.endOffset)
            check(member.symbolId == etsFunctionSymbol(real.name.asString(), emptyList(), EtsTypes.VOID, origin).id)
            check(member.name == real.name.asString())
            check(member.receiver.type == backend.language.type(call.dispatchReceiver!!.type))
            check(member.receiver.type is EtsTypeParameterType && member.receiver !is EtsCast)
            check((member.type as EtsFunctionType).result == backend.language.type(call.type))
            "${call.dispatchReceiver!!.type.render()}.${symbolName(real)} -> ${member.symbolId}; ${member.type}"
        }
        File(args[2], "bindings.txt").writeText(bindings.joinToString("\n"))
        val functions = program.files.flatMap { it.declarations }.filterIsInstance<EtsFunction>().associateBy { it.name }
        val chain = functions.getValue("chainedRead").typeParameters
        check(chain.map { it.name } == listOf("A", "U", "T"))
        check(chain[2].upperBound == EtsTypeParameterType(chain[1].id, "U"))
        val self = functions.getValue("selfBound").typeParameters.single()
        val selfBound = self.upperBound as EtsNamedType
        check(selfBound.name == "Self" && selfBound.symbolId != null)
        check(selfBound.arguments == listOf(EtsTypeParameterType(self.id, "T")))
        val ordered = functions.getValue("ordered")
        check(ordered.parameters.map { it.symbol.name } == listOf("factory", "argument"))
        val orderedNodes = mutableListOf<EtsNode>()
        walkEts(ordered, orderedNodes::add)
        for (parameter in ordered.parameters) {
            check(orderedNodes.filterIsInstance<EtsReference>().count { it.symbol == parameter.symbol } == 1)
        }
        EtsValidator().validate(program)
        println("PASS eight actual bounded receiver calls, canonical member IDs, uncast T receivers, binder chains, named F-bound and single-use effectful arguments")
        program
    }
    EtsValidator().validate(program)
    File(args[2], "BoundedReceivers.ets").writeText(emitEtsProgram(program, StandardLibraryRuntime))
    println("PASS detached bounded receiver validation and complete untouched ETS emission")
    temporaryOrigins(File(args[0]).resolveSibling("TemporaryOrigins.kt"), args[1], File(args[2]))
}

private fun temporaryOrigins(input: File, classpath: String, output: File) {
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", classpath, input.path)) { module ->
        File(output, "temporary-origins.ir").writeText(module.dump())
        val declarations = module.files.single().declarations
        val function = declarations.filterIsInstance<IrSimpleFunction>().single { it.name.asString() == "temporaryNames" }
        val variables = mutableListOf<IrVariable>()
        val reads = mutableListOf<IrGetValue>()
        function.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
            override fun visitVariable(declaration: IrVariable) { variables += declaration; super.visitVariable(declaration) }
            override fun visitGetValue(expression: IrGetValue) { reads += expression }
        })
        val receivers = variables.filter { it.origin == IrDeclarationOrigin.IR_TEMPORARY_VARIABLE_FOR_INLINED_EXTENSION_RECEIVER }
        check(receivers.size == 2)
        val language = LanguageLowering(DiagnosticSink(input.path), listOf(StandardLibraryRules()))
        val target = language.function(function, Scope())
        check(target.parameters.single().symbol.name == "__etsTmp0")
        val nodes = mutableListOf<EtsNode>()
        walkEts(target, nodes::add)
        check(nodes.filterIsInstance<EtsVariable>().none { it.symbol.name in setOf("this", "__etsTmp0") })
        for (receiver in receivers) {
            val uses = reads.filter { it.symbol == receiver.symbol }
            check(uses.size >= 2)
            val initializer = receiver.initializer as IrGetValue
            val source = language.source(receiver)
            val scope = Scope(bindings = linkedMapOf(
                function.valueParameters.single().symbol to EtsReference(target.parameters.single().symbol),
                initializer.symbol to EtsReference(EtsSymbol("probe:initializer", "box", language.type(receiver.type), source)),
            ))
            val emitted = language.statements(function.factory.createBlockBody(function.startOffset, function.endOffset, listOf(receiver) + uses), scope)
            val bound = (scope.bindings.getValue(receiver.symbol) as EtsReference).symbol
            check(bound.name !in setOf("this", "__etsTmp0"))
            check((emitted.first() as EtsVariable).symbol == bound)
            check(emitted.drop(1).all { (it as EtsExpressionStatement).expression == EtsReference(bound, it.source) })
        }
        val strictSource = declarations.filterIsInstance<IrSimpleFunction>().single { it.name.asString() == "strictValues" }
        val strictLanguage = LanguageLowering(DiagnosticSink(input.path), listOf(StandardLibraryRules()))
        val strictTarget = strictLanguage.function(strictSource, Scope())
        val strictNodes = mutableListOf<EtsNode>()
        walkEts(strictTarget, strictNodes::add)
        val preserved = setOf("eval_0", "arguments_2")
        check(strictNodes.filterIsInstance<EtsVariable>().map { it.symbol.name }.toSet() == preserved)
        strictSource.valueParameters.zip(strictTarget.parameters).forEach { (original, parameter) ->
            check(!etsRestrictedValueBinding(parameter.symbol.name) && parameter.symbol.name !in preserved)
            check(parameter.symbol.name.startsWith("${original.name}_"))
            check(parameter.symbol.source == SourceSpan(input.path, original.startOffset, original.endOffset))
            check(strictNodes.filterIsInstance<EtsReference>().count { it.symbol == parameter.symbol } == 2)
        }
        File(output, "strict-binding-names.txt").writeText(strictSource.valueParameters.zip(strictTarget.parameters).joinToString("\n") { (original, parameter) ->
            "${original.name} -> ${parameter.symbol.name}; ${parameter.symbol.id}; ${parameter.symbol.source}"
        })
        val classes = declarations.filterIsInstance<IrClass>().map(language::clazz)
        val fields = classes.single { it.name == "StrictFields" }.members
        check(fields.filterIsInstance<EtsField>().map { it.symbol.name }.toSet() == setOf("arguments", "eval"))
        val constructor = fields.filterIsInstance<EtsFunction>().single { it.kind == EtsFunctionKind.CONSTRUCTOR }
        check(constructor.parameters.none { etsRestrictedValueBinding(it.symbol.name) })
        val methods = classes.single { it.name == "StrictMethods" }.members.filterIsInstance<EtsFunction>()
        check(methods.filter { it.kind == EtsFunctionKind.METHOD }.map { it.name }.toSet() == setOf("arguments", "eval"))
        check(classes.single { it.name == "TypeNames" }.typeParameters.map { it.name } == listOf("eval", "arguments"))
        EtsValidator().validate(EtsProgram(listOf(EtsFile(input.path, classes + target + strictTarget))))
        println("PASS two official extension receiver origins, repeated IrValueSymbol binding, preserved source parameter and __etsTmp0 collision avoidance; target reserved guard unchanged")
        println("PASS strict value binding aliases, preserved fields/methods/type binders, repeated references, source provenance and collision avoidance")
    }
}
