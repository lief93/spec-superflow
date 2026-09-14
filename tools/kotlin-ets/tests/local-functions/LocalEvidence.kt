@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.backend.common.lower.LocalDeclarationsLowering
import org.jetbrains.kotlin.backend.common.lower.SharedVariablesLowering
import org.jetbrains.kotlin.cli.common.CommonCompilerPerformanceManager
import org.jetbrains.kotlin.cli.common.arguments.*
import org.jetbrains.kotlin.cli.common.messages.*
import org.jetbrains.kotlin.cli.pipeline.ArgumentsPipelineArtifact
import org.jetbrains.kotlin.cli.pipeline.jvm.*
import org.jetbrains.kotlin.com.intellij.openapi.util.Disposer
import org.jetbrains.kotlin.config.KotlinCompilerVersion
import org.jetbrains.kotlin.config.Services
import org.jetbrains.kotlin.descriptors.DescriptorVisibilities
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

private class LocalSnapshot(module: IrModuleFragment) {
    val functions = mutableListOf<IrSimpleFunction>()
    val lambdas = mutableListOf<IrFunctionExpression>()
    val variables = mutableListOf<IrVariable>()
    val cells = mutableListOf<IrClass>()
    val constructors = mutableListOf<IrConstructorCall>()
    val accesses = mutableListOf<IrCall>()
    init {
        module.acceptChildrenVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                when (element) {
                    is IrSimpleFunction -> functions.add(element)
                    is IrFunctionExpression -> lambdas.add(element)
                    is IrVariable -> variables.add(element)
                    is IrClass -> if (element.origin === ETS_SHARED_VARIABLE_CELL) cells.add(element)
                    is IrConstructorCall -> constructors.add(element)
                    is IrCall -> accesses.add(element)
                }
                element.acceptChildrenVoid(this)
            }
        })
    }
    val namedLocals get() = functions.filter { it.visibility == DescriptorVisibilities.LOCAL && !it.name.isSpecial }
}

fun main(args: Array<String>) {
    check(KotlinCompilerVersion.VERSION == "2.1.20")
    for (phase in listOf(SharedVariablesLowering::class.java, LocalDeclarationsLowering::class.java)) {
        println("Official phase: ${phase.name}; loadedFrom=${phase.protectionDomain.codeSource.location}")
    }
    val compilerArgs = listOf(args[0], "-no-stdlib", "-no-reflect", "-classpath", args[1])
    val disposable = Disposer.newDisposable()
    val messages = GroupingMessageCollector(PrintingMessageCollector(System.err, MessageRenderer.PLAIN_FULL_PATHS, false), false, false)
    try {
        val options = K2JVMCompilerArguments()
        parseCommandLineArguments(compilerArgs, options)
        val input = ArgumentsPipelineArtifact(options, Services.EMPTY, disposable, messages,
            object : CommonCompilerPerformanceManager("local-lowering-evidence") {})
        val configured = checkNotNull(JvmConfigurationPipelinePhase.executePhase(input))
        val analyzed = checkNotNull(JvmFrontendPipelinePhase.executePhase(configured))
        val artifact = checkNotNull(JvmFir2IrPipelinePhase.executePhase(analyzed))
        check(!artifact.diagnosticCollector.hasErrors && !messages.hasErrors())
        val module = artifact.result.irModuleFragment
        val file = module.files.single()
        val fileEntry = file.fileEntry
        val before = LocalSnapshot(module)
        val locals = before.namedLocals.toList()
        check(locals.isNotEmpty() && before.lambdas.isNotEmpty())
        val sourcePositions = locals.map { it.startOffset to it.endOffset }.toSet()
        val outerFunctions = before.functions.filter { it.parent is IrFile || it.parent is IrClass }
            .associateWith { it.name to it.valueParameters.map { parameter -> parameter.name } }
        val originalVariables = before.variables.associateBy { it.startOffset to it.endOffset }
        File(args[2], "locals-before.ir").writeText(module.dump())
        lowerLocalDeclarations(artifact)
        val after = LocalSnapshot(module)
        File(args[2], "locals-after.ir").writeText(module.dump())
        check(file.fileEntry === fileEntry && file.fileEntry.name == args[0])
        check(after.namedLocals.isEmpty()) { "Named local declarations remain after official lowering" }
        check(before.lambdas.size == after.lambdas.size && before.lambdas.all { lambda -> after.lambdas.any { it === lambda } })
        outerFunctions.forEach { (function, original) ->
            check(function.name == original.first && function.valueParameters.map { it.name } == original.second)
        }
        val lifted = after.functions.filter { it.origin == IrDeclarationOrigin.LOCAL_FUNCTION && it.parent is IrDeclarationContainer }
        check(lifted.size == locals.size)
        check(lifted.all { (it.startOffset to it.endOffset) in sourcePositions && it.fileOrNull === file })
        check(lifted.any { it.typeParameters.isNotEmpty() })
        check(lifted.any { it.parent is IrClass && it.dispatchReceiverParameter == null })
        check(after.cells.isNotEmpty())
        val cellSymbols = after.cells.map { it.symbol }.toSet()
        after.cells.forEach { cell ->
            check(cell.parent === file && cell.typeParameters.size == 1)
            check((cell.startOffset to cell.endOffset) in originalVariables)
            val property = cell.declarations.filterIsInstance<IrProperty>().single()
            check(property.isVar && property.getter?.origin == IrDeclarationOrigin.DEFAULT_PROPERTY_ACCESSOR)
            check(property.setter?.origin == IrDeclarationOrigin.DEFAULT_PROPERTY_ACCESSOR)
            check(property.backingField!!.type.classifierOrNull === cell.typeParameters.single().symbol)
            check(cell.constructors.single().isPrimary)
        }
        val boxed = after.variables.filter { it.type.classOrNull in cellSymbols }
        check(boxed.size >= 3)
        boxed.forEach { variable ->
            val original = originalVariables.getValue(variable.startOffset to variable.endOffset)
            val creation = variable.initializer as IrConstructorCall
            check(variable.symbol !== original.symbol && variable.name == original.name && !variable.isVar)
            check(creation.symbol.owner.parent === variable.type.classOrNull!!.owner)
            check(creation.getTypeArgument(0) == original.type)
            check(creation.getValueArgument(0) != null)
        }
        val cellCalls = after.accesses.filter { (it.symbol.owner.parent as? IrClass)?.symbol in cellSymbols }
        check(cellCalls.isNotEmpty() && cellCalls.all { it.startOffset >= 0 && it.endOffset > it.startOffset })
        check(!module.dump().contains("kotlin.jvm.internal.Ref"))
        println("PASS official local IR: named=${locals.size}->0, lifted=${lifted.size}, cells=${after.cells.size}, " +
            "boxed=${boxed.size}, cellCalls=${cellCalls.size}, lambdas=${after.lambdas.size}; source and type provenance retained")
    } finally {
        messages.flush()
        Disposer.dispose(disposable)
    }
    withKotlinModule(compilerArgs) { module ->
        val production = LocalSnapshot(module)
        check(production.namedLocals.isEmpty() && production.cells.isNotEmpty())
    }
    println("PASS production frontend applies official local/shared lowering by default")
    val ordinarySource = File(args[2], "OrdinaryClosure.kt").apply {
        writeText("""
            fun ordinary(start: Int): () -> Int {
                var value = start
                return { value += 1; value }
            }
        """.trimIndent())
    }
    withKotlinModule(listOf(ordinarySource.absolutePath, "-no-stdlib", "-no-reflect", "-classpath", args[1])) { module ->
        val ordinary = LocalSnapshot(module)
        check(ordinary.cells.isEmpty() && ordinary.namedLocals.isEmpty())
        check(ordinary.lambdas.size == 1 && ordinary.variables.single().isVar)
        File(args[2], "ordinary-closure.ir").writeText(module.dump())
    }
    println("PASS ordinary closure-only body retains native mutable capture without boxing")
}
