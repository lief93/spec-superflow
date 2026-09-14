@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.backend.common.lower.FlattenStringConcatenationLowering
import org.jetbrains.kotlin.cli.common.CommonCompilerPerformanceManager
import org.jetbrains.kotlin.cli.common.arguments.*
import org.jetbrains.kotlin.cli.common.fir.FirDiagnosticsCompilerResultsReporter
import org.jetbrains.kotlin.cli.common.messages.*
import org.jetbrains.kotlin.cli.pipeline.ArgumentsPipelineArtifact
import org.jetbrains.kotlin.cli.pipeline.jvm.*
import org.jetbrains.kotlin.com.intellij.openapi.util.Disposer
import org.jetbrains.kotlin.config.Services
import org.jetbrains.kotlin.config.KotlinCompilerVersion
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

private data class DeclarationInfo(val declaration: IrDeclarationWithName, val name: String, val start: Int, val end: Int)
private class Snapshot(module: IrModuleFragment) {
    val declarations = mutableListOf<DeclarationInfo>()
    val plusCalls = mutableListOf<IrCall>()
    val concatenations = mutableListOf<IrStringConcatenation>()
    val literalStrings = mutableListOf<String>()
    val calls = mutableListOf<IrCall>()
    init {
        module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                when (element) {
                    is IrDeclarationWithName -> declarations.add(DeclarationInfo(element, element.name.asString(), element.startOffset, element.endOffset))
                    is IrCall -> {
                        calls.add(element)
                        if (element.symbol.owner.fqNameWhenAvailable?.asString() in setOf("kotlin.plus", "kotlin.String.plus")) plusCalls.add(element)
                    }
                    is IrStringConcatenation -> concatenations.add(element)
                    is IrConst -> if (element.value is String) literalStrings.add(element.value as String)
                }
                element.acceptChildrenVoid(this)
            }
        })
    }
}

fun main(args: Array<String>) {
    check(KotlinCompilerVersion.VERSION == "2.1.20")
    println("Official pass: ${FlattenStringConcatenationLowering::class.java.name}; " +
        "compiler=${KotlinCompilerVersion.VERSION}; " +
        "loadedFrom=${FlattenStringConcatenationLowering::class.java.protectionDomain.codeSource.location}")
    val fixture = args[0]
    val compilerArgs = listOf(fixture, "-no-stdlib", "-no-reflect", "-classpath", args[1])
    val disposable = Disposer.newDisposable()
    val messages = GroupingMessageCollector(PrintingMessageCollector(System.err, MessageRenderer.PLAIN_FULL_PATHS, false), false, false)
    try {
        val options = K2JVMCompilerArguments()
        parseCommandLineArguments(compilerArgs, options)
        val input = ArgumentsPipelineArtifact(options, Services.EMPTY, disposable, messages,
            object : CommonCompilerPerformanceManager("official-lowering-evidence") {})
        val configured = checkNotNull(JvmConfigurationPipelinePhase.executePhase(input))
        val analyzed = checkNotNull(JvmFrontendPipelinePhase.executePhase(configured))
        FirDiagnosticsCompilerResultsReporter.reportToMessageCollector(analyzed.diagnosticCollector, messages, true)
        check(!analyzed.diagnosticCollector.hasErrors && !messages.hasErrors())
        val artifact = checkNotNull(JvmFir2IrPipelinePhase.executePhase(analyzed))
        check(!artifact.diagnosticCollector.hasErrors && !messages.hasErrors())
        val module = artifact.result.irModuleFragment
        val file = module.files.single()
        val fileEntry = file.fileEntry
        val before = Snapshot(module)
        val beforeDump = module.dump()
        File(args[2], "before.ir").writeText(beforeDump)
        check(before.plusCalls.isNotEmpty()) { "Fixture must exercise a non-zero official transformation" }
        val context = createJvmLoweringContext(artifact)
        check(context.irBuiltIns === artifact.result.irBuiltIns)
        check(context.symbolTable === artifact.result.symbolTable)
        check(context.irProviders === artifact.result.components.irProviders)
        check(context.state.factory.currentOutput.isEmpty()) { "Context setup must not generate bytecode" }
        check(module.dump() == beforeDump) { "JVM context construction/linking must not rewrite the source module" }
        check(Snapshot(module).declarations == before.declarations)
        println("PASS real JVM context setup: source IR unchanged, original builtins/symbols/providers, no bytecode")
        lowerStringConcatenations(artifact)
        check(module === artifact.result.irModuleFragment && fileEntry === file.fileEntry)
        val after = Snapshot(module)
        File(args[2], "after.ir").writeText(module.dump())
        check(after.plusCalls.isEmpty()) { "Official String.plus calls must become concatenations/constants" }
        check(before.declarations == after.declarations) { "Declaration identity, names and offsets must be preserved" }
        check(fileEntry.name == fixture)
        check("decimal=1.0:null" in after.literalStrings)
        val recordCalls = before.calls.filter { it.symbol.owner.name.asString() == "record" }
        check(recordCalls.size == 4)
        check(recordCalls.all { call -> after.calls.any { it === call } })
        check(recordCalls.all { it.startOffset >= 0 && it.endOffset > it.startOffset })
        check(after.concatenations.any { concat -> before.plusCalls.any {
            it.startOffset == concat.startOffset && it.endOffset == concat.endOffset
        } }) { "Lowered concatenation must retain its source expression span" }
        println("PASS official IR: String.plus calls ${before.plusCalls.size} -> ${after.plusCalls.size}; " +
            "declarations=${after.declarations.size}; record-call identities=${recordCalls.size}; names, file and offsets preserved")
    } finally {
        messages.flush()
        Disposer.dispose(disposable)
    }
    withKotlinModule(compilerArgs) { module ->
        check(Snapshot(module).plusCalls.isEmpty()) { "Production frontend must apply the official lowering by default" }
    }
    println("PASS production frontend defaults to official lowering")
}
