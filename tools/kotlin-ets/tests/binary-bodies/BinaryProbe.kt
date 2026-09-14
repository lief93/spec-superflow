@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class,
    org.jetbrains.kotlin.ir.util.DelicateSymbolTableApi::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.backend.jvm.*
import org.jetbrains.kotlin.backend.common.serialization.signature.PublicIdSignatureComputer
import org.jetbrains.kotlin.ir.backend.jvm.serialization.JvmIrMangler
import org.jetbrains.kotlin.cli.common.CommonCompilerPerformanceManager
import org.jetbrains.kotlin.cli.common.arguments.*
import org.jetbrains.kotlin.cli.common.messages.*
import org.jetbrains.kotlin.cli.pipeline.ArgumentsPipelineArtifact
import org.jetbrains.kotlin.cli.pipeline.jvm.*
import org.jetbrains.kotlin.com.intellij.openapi.util.Disposer
import org.jetbrains.kotlin.config.Services
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.inline.*
import org.jetbrains.kotlin.backend.common.lower.ReturnableBlockTransformer
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.load.kotlin.JvmPackagePartSource

/** Isolated real K2/FIR-to-IR experiment; never invents or copies a function body. */
fun main(args: Array<String>) {
    val disposable = Disposer.newDisposable()
    val messages = GroupingMessageCollector(PrintingMessageCollector(System.err, MessageRenderer.PLAIN_FULL_PATHS, false), false, false)
    try {
        val options = K2JVMCompilerArguments()
        parseCommandLineArguments(listOf(args[0], "-no-stdlib", "-no-reflect", "-classpath", args[1]), options)
        val input = ArgumentsPipelineArtifact(options, Services.EMPTY, disposable, messages,
            object : CommonCompilerPerformanceManager("binary-body-probe") {})
        val configured = checkNotNull(JvmConfigurationPipelinePhase.executePhase(input))
        val analyzed = checkNotNull(JvmFrontendPipelinePhase.executePhase(configured))
        val artifact = checkNotNull(JvmFir2IrPipelinePhase.executePhase(analyzed))
        check(!artifact.diagnosticCollector.hasErrors && !messages.hasErrors())
        val module = artifact.result.irModuleFragment
        val calls = mutableListOf<IrCall>()
        module.acceptChildrenVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrCall && element.symbol.owner.fqNameWhenAvailable?.asString() == "binarylibrary.binaryTransform") calls.add(element)
                element.acceptChildrenVoid(this)
            }
        })
        check(calls.size == 2)
        val function = calls.first().symbol.owner
        check(calls.all { it.symbol === function.symbol } && function.isInline && function.body == null)
        val source = function.containerSource as JvmPackagePartSource
        val bytes = source.knownJvmBinaryClass?.classHeader?.serializedIr
        println("SIGNATURE bound=${function.symbol.isBound} body=${function.body != null} symbol=${function.symbol.signature} container=${source.javaClass.name}")
        println("SERIALIZED_IR bytes=${bytes?.size ?: 0}")
        if (args[3] == "signature") {
            check(bytes == null)
            println("PASS signature-only JAR has no serialized IR body")
            return
        }
        check(bytes != null && bytes.isNotEmpty()) { "Serialized JAR must contain real IR bytes" }
        File(args[2], "serialized-ir.bin").writeBytes(bytes)
        val context = createJvmLoweringContext(artifact)
        println("CONTEXT builtinsSame=${context.irBuiltIns === artifact.result.irBuiltIns} symbolTableSame=${context.symbolTable === artifact.result.symbolTable} providers=${context.irProviders.map { it.javaClass.name }}")
        val signatures = PublicIdSignatureComputer(JvmIrMangler)
        val signature = signatures.computeSignature(function)
        println("COMPUTED_SIGNATURE $signature")
        if (args[3] in setOf("registered", "linked")) {
            context.symbolTable.declareSimpleFunction(signature, { function.symbol }) { function }
            println("REGISTERED_ORIGINAL_SYMBOL ${context.symbolTable.referenceSimpleFunction(signature) === function.symbol}")
        }
        if (args[3] == "linked") {
            val canonicalClasses = (listOf(context.irBuiltIns.nothingClass.owner) +
                function.valueParameters.mapNotNull { it.type.classOrNull?.owner } +
                listOfNotNull(function.returnType.classOrNull?.owner)).distinct()
            for (declaration in canonicalClasses) {
                context.symbolTable.declareClass(signatures.computeSignature(declaration), { declaration.symbol }) { declaration }
                declaration.declarations.filterIsInstance<IrSimpleFunction>().forEach { member ->
                    context.symbolTable.declareSimpleFunction(signatures.computeSignature(member), { member.symbol }) { member }
                }
            }
            println("REGISTERED_CANONICAL_CLASSES ${canonicalClasses.map { it.fqNameWhenAvailable }}")
        }
        val facadeName = source.facadeClassName ?: source.className
        val facade = createJvmFileFacadeClass(IrDeclarationOrigin.FILE_CLASS,
            facadeName.fqNameForTopLevelClassMaybeWithDollars.shortName(), source) { false }.apply {
            parent = function.parent
            createThisReceiverParameter()
            classNameOverride = facadeName
        }
        // The same parent adjustment performed by official K2 ExternalPackageParentPatcherLowering.
        function.parent = facade
        val deserializer = JvmIrDeserializerImpl()
        println("DESERIALIZER ${deserializer.javaClass.name} loadedFrom=${deserializer.javaClass.protectionDomain.codeSource.location}")
        val loaded = deserializer.deserializeTopLevelClass(facade, context.irBuiltIns, context.symbolTable,
            context.irProviders, context.generatorExtensions)
        println("LOADED result=$loaded originalBody=${function.body != null}")
        File(args[2], "loaded-facade.ir").writeText(facade.dump())
        val inventory = mutableListOf<String>()
        context.symbolTable.forEachDeclarationSymbol { symbol ->
            inventory.add("${symbol.javaClass.simpleName} ${symbol.signature} bound=${symbol.isBound}")
            if (symbol.isBound && symbol.owner is IrSimpleFunction && (symbol.owner as IrSimpleFunction).body != null) {
                File(args[2], "table-function-${inventory.size}.ir").writeText(symbol.owner.dump())
            }
        }
        File(args[2], "symbol-table.txt").writeText(inventory.joinToString("\n"))
        println("SYMBOLS total=${inventory.size} unbound=${inventory.count { it.endsWith("bound=false") }}")
        check(loaded && function.body != null) { "Deserialization must populate the actual resolved call declaration" }
        File(args[2], "loaded-function.ir").writeText(function.dump())
        if (args[3] == "linked") {
            check(inventory.none { it.endsWith("bound=false") }) { "Loaded body retains unbound dependencies" }
            val resolver = object : InlineFunctionResolver(InlineMode.ALL_INLINE_FUNCTIONS) {
                override fun needsInlining(candidate: IrFunction) = candidate === function
            }
            module.files.forEach(CommonInlineCallableReferenceToLambdaPhase(context, resolver)::lower)
            FunctionInlining(context, resolver, produceOuterThisFields = false).inline(module)
            module.transformChildrenVoid(ReturnableBlockTransformer(context))
            module.patchDeclarationParents()
            File(args[2], "after-inline.ir").writeText(module.dump())
            var remaining = 0
            module.acceptChildrenVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) {
                    if (element is IrCall && element.symbol === function.symbol) remaining++
                    element.acceptChildrenVoid(this)
                }
            })
            println("OFFICIAL_INLINE before=${calls.size} after=$remaining")
            check(remaining == 0) { "Official inliner must consume the loaded binary body" }
        }
        println("PASS actual resolved declaration has a loaded binary body; target execution not established")
    } finally {
        messages.flush()
        Disposer.dispose(disposable)
    }
}
