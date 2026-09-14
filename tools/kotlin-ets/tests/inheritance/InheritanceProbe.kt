@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.cli.common.CommonCompilerPerformanceManager
import org.jetbrains.kotlin.cli.common.arguments.*
import org.jetbrains.kotlin.cli.common.messages.*
import org.jetbrains.kotlin.cli.pipeline.ArgumentsPipelineArtifact
import org.jetbrains.kotlin.cli.pipeline.jvm.*
import org.jetbrains.kotlin.com.intellij.openapi.util.Disposer
import org.jetbrains.kotlin.config.KotlinCompilerVersion
import org.jetbrains.kotlin.config.Services
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    check(KotlinCompilerVersion.VERSION == "2.1.20")
    val disposable = Disposer.newDisposable()
    val messages = GroupingMessageCollector(PrintingMessageCollector(System.err, MessageRenderer.PLAIN_FULL_PATHS, false), false, false)
    try {
        val options = K2JVMCompilerArguments()
        parseCommandLineArguments(listOf(args[0], "-no-stdlib", "-no-reflect", "-classpath", args[1]), options)
        val input = ArgumentsPipelineArtifact(options, Services.EMPTY, disposable, messages,
            object : CommonCompilerPerformanceManager("inheritance-evidence") {})
        val config = checkNotNull(JvmConfigurationPipelinePhase.executePhase(input))
        val analyzed = checkNotNull(JvmFrontendPipelinePhase.executePhase(config))
        val artifact = checkNotNull(JvmFir2IrPipelinePhase.executePhase(analyzed))
        check(!artifact.diagnosticCollector.hasErrors && !messages.hasErrors())
        val module = artifact.result.irModuleFragment
        File(args[2], "actual.ir").writeText(module.dump())
        val calls = mutableListOf<IrCall>()
        module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
            override fun visitCall(expression: IrCall) { calls.add(expression); super.visitCall(expression) }
        })
        val inherited = calls.filter { it.symbol.owner.isFakeOverride && sourceFile(it.symbol.owner) != null }
        check(inherited.isNotEmpty())
        File(args[2], "bindings.txt").writeText(inherited.joinToString("\n") { call ->
            "${symbolName(call.symbol.owner)} -> ${call.symbol.owner.collectRealOverrides().map(::symbolName)}; ${call.type.render()}"
        })
        val declarations = module.files.flatMap { it.declarations }.filterIsInstance<IrClass>()
        val operation = declarations.single { it.name.asString() == "Operation" }
        val language = LanguageLowering(DiagnosticSink(args[0]), listOf(StandardLibraryRules()))
        val target = language.clazz(operation)
        check(target.name == "Operation")
        val method = target.members.filterIsInstance<EtsFunction>().single()
        check(method.name == "apply" && method.parameters.map { it.symbol.name } == listOf("left", "right"))
        check(target.kind == EtsClassKind.INTERFACE && method.abstract && method.body.isEmpty())
        val program = EtsProgram(module.files.map { file -> EtsFile(file.fileEntry.name, file.declarations.map {
            when (it) {
                is IrClass -> language.clazz(it)
                is IrSimpleFunction -> language.function(it)
                else -> error("Unexpected declaration")
            }
        }) })
        EtsValidator().validate(program)
        val nodes = mutableListOf<EtsNode>()
        program.files.forEach { file -> file.declarations.forEach { walkEts(it, nodes::add) } }
        val members = nodes.filterIsInstance<EtsMember>().filter { it.symbolId != null }
        check(members.isNotEmpty())
        fun expectedSymbol(function: IrSimpleFunction): EtsSymbol = etsFunctionSymbol(function.name.asString(),
            function.valueParameters.map { language.type(it.type) }, language.type(function.returnType),
            SourceSpan(sourceFile(function)?.fileEntry?.name, function.startOffset, function.endOffset))
        inherited.filter { it.symbol.owner.correspondingPropertySymbol == null }.forEach { call ->
            val real = call.symbol.owner.collectRealOverrides().single()
            val reference = members.single { it.source.start == call.startOffset && it.source.end == call.endOffset }
            check(reference.symbolId == expectedSymbol(real).id)
        }
        val targetClasses = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>()
        val base = targetClasses.single { it.name == "Base" }
        val derived = targetClasses.single { it.name == "Derived" }
        check(derived.baseClass?.symbolId == base.symbol.id)
        check(derived.members.filterIsInstance<EtsFunction>().single { it.name == "apply" }.overrides.contains(
            base.members.filterIsInstance<EtsFunction>().single { it.name == "apply" }.symbol.id))
        check(targetClasses.single { it.name == "NamedOperation" }.interfaces.single().symbolId == target.symbol.id)
        check(nodes.filterIsInstance<EtsSuperConstructorCall>().size == 4)
        targetClasses.filter { it.baseClass != null }.forEach { klass ->
            val constructor = klass.members.filterIsInstance<EtsFunction>().single { it.kind == EtsFunctionKind.CONSTRUCTOR }
            check((constructor.body.first() as EtsSuperConstructorCall).baseClass == klass.baseClass)
        }
        File(args[2], "target-bindings.txt").writeText(members.joinToString("\n") { "${it.name}: ${it.symbolId}; ${it.type}" })
        println("PASS Kotlin ${KotlinCompilerVersion.VERSION}: real inherited symbols=${inherited.size}; interface signature names preserved")
        println("PASS full typed hierarchy, canonical member identities, abstract signatures, real constructor delegation and source bindings")
    } finally { messages.flush(); Disposer.dispose(disposable) }
}
