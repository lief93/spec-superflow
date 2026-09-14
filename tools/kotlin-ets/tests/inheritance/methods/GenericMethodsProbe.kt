@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.config.KotlinCompilerVersion
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.defaultType
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    check(KotlinCompilerVersion.VERSION == "2.1.20")
    val input = File(args[0])
    val output = File(args[2])
    val program = withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[1], input.path)) { module ->
        File(output, "actual.ir").writeText(module.dump())
        val functions = mutableListOf<IrSimpleFunction>()
        val calls = mutableListOf<IrCall>()
        module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
            override fun visitSimpleFunction(declaration: IrSimpleFunction) {
                if (!declaration.isFakeOverride && declaration.parent is IrClass && declaration.typeParameters.isNotEmpty()) {
                    functions += declaration
                }
                super.visitSimpleFunction(declaration)
            }
            override fun visitCall(expression: IrCall) {
                val owner = expression.symbol.owner
                if (owner.parent is IrClass && owner.typeParameters.isNotEmpty() && sourceFile(owner) != null) calls += expression
                super.visitCall(expression)
            }
        })
        check(functions.isNotEmpty() && calls.isNotEmpty())
        val backend = EtsBackend(DiagnosticSink(input.path), listOf(StandardLibraryRules()))
        val program = backend.lower(module)
        val nodes = mutableListOf<EtsNode>()
        program.files.forEach { file -> file.declarations.forEach { walkEts(it, nodes::add) } }
        val targets = nodes.filterIsInstance<EtsFunction>()
        val records = mutableListOf<String>()
        for (function in functions) {
            val target = targets.single { it.source.start == function.startOffset && it.name == function.name.asString() }
            check(target.typeParameters.map { it.name } == function.typeParameters.map { it.name.asString() })
            check(target.typeParameters.map { EtsTypeParameterType(it.id, it.name) } ==
                function.typeParameters.map { backend.language.type(it.defaultType) })
            check(target.parameters.map { it.symbol.name } == function.valueParameters.map { it.name.asString() })
            val overrides = function.overriddenSymbols.flatMap { it.owner.collectRealOverrides() }.distinct()
            check(target.overrides.toSet() == overrides.map { real ->
                etsFunctionSymbol(real.name.asString(), emptyList(), EtsTypes.VOID,
                    SourceSpan(sourceFile(real)!!.fileEntry.name, real.startOffset, real.endOffset)).id
            }.toSet())
            records += "declaration ${target.symbol.id}: ${target.symbol.type}; overrides=${target.overrides}"
        }
        for (call in calls) {
            val real = call.symbol.owner.collectRealOverrides().single()
            val target = nodes.filterIsInstance<EtsCall>().single {
                it.callee is EtsMember && it.source.start == call.startOffset && it.source.end == call.endOffset
            }
            val member = target.callee as EtsMember
            val source = SourceSpan(sourceFile(real)!!.fileEntry.name, real.startOffset, real.endOffset)
            check(member.symbolId == etsFunctionSymbol(real.name.asString(), emptyList(), EtsTypes.VOID, source).id)
            check(member.name == real.name.asString())
            check(member.receiver.type == backend.language.type(call.dispatchReceiver!!.type))
            val signature = member.type as EtsFunctionType
            check(signature.typeParameters.map { EtsTypeParameterType(it.id, it.name) } ==
                real.typeParameters.map { backend.language.type(it.defaultType) })
            check(target.typeArguments == real.typeParameters.indices.map { backend.language.type(call.getTypeArgument(it)!!) })
            check(etsInstantiate(signature, target.typeArguments).result == backend.language.type(call.type))
            records += "call ${call.startOffset} ${symbolName(call.symbol.owner)} -> ${member.symbolId}: $signature; args=${target.typeArguments}"
        }
        File(output, "bindings.txt").writeText(records.joinToString("\n"))
        EtsValidator().validate(program)
        println("PASS ${functions.size} generic member declarations and ${calls.size} actual IR calls: names, method-owned binders, canonical IDs, class/method instantiation and detached validation")
        program
    }
    EtsValidator().validate(program)
    File(output, input.nameWithoutExtension + ".ets").writeText(emitEtsProgram(program, StandardLibraryRuntime))
}
