@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.klibtest

import dev.ets.*
import java.io.File
import org.jetbrains.kotlin.backend.common.linkage.issues.checkNoUnboundSymbols
import org.jetbrains.kotlin.cli.common.CLIConfigurationKeys
import org.jetbrains.kotlin.cli.common.messages.*
import org.jetbrains.kotlin.cli.jvm.compiler.EnvironmentConfigFiles
import org.jetbrains.kotlin.cli.jvm.compiler.KotlinCoreEnvironment
import org.jetbrains.kotlin.com.intellij.openapi.util.Disposer
import org.jetbrains.kotlin.config.*
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.backend.js.*
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.declarations.impl.IrFactoryImpl
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.linkage.partial.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    val disposable = Disposer.newDisposable()
    try {
        val configuration = CompilerConfiguration().apply {
            put(CommonConfigurationKeys.MODULE_NAME, "ets-klib-proof")
            put(CommonConfigurationKeys.LANGUAGE_VERSION_SETTINGS, LanguageVersionSettingsImpl.DEFAULT)
            put(CLIConfigurationKeys.MESSAGE_COLLECTOR_KEY,
                PrintingMessageCollector(System.err, MessageRenderer.PLAIN_FULL_PATHS, false))
            put(PartialLinkageConfig.KEY, PartialLinkageConfig.DEFAULT)
        }
        val environment = KotlinCoreEnvironment.createForProduction(disposable, configuration, EnvironmentConfigFiles.JS_CONFIG_FILES)
        val structure = ModulesStructure(environment.project, MainModule.Klib(args[1]), configuration,
            args.drop(1), emptyList())
        val loaded = loadIr(structure, IrFactoryImpl)
        loaded.deserializer.checkNoUnboundSymbols(loaded.symbolTable, "before ETS lowering")
        // Explicitly approved libraries, matched through the official resolver's descriptors.
        val translatedPaths = (listOf(args[1]) + args.drop(3)).map { File(it).canonicalPath }.toSet()
        val descriptors = structure.allDependencies.filter { it.libraryFile.canonicalPath in translatedPaths }
            .map { structure.getModuleDescriptor(it) }
        val modules = loaded.allDependencies.filter { module -> descriptors.any { it === module.descriptor } }
        check(modules.size == translatedPaths.size)
        val functions = modules.flatMap { it.files }.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
        check(functions.map { it.name.asString() }.toSet() == setOf("scenario", "adjusted", "buttonLabel", "echo", "offset"))
        functions.forEach { function ->
            check(function.body != null) { "Signature without body: ${function.name}" }
            check(function.file.module in modules)
            check(!File(function.file.fileEntry.name).exists()) { "Producer source still exists" }
            check(function.startOffset >= 0 && function.endOffset > function.startOffset)
            function.acceptChildrenVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) {
                    if (element is IrCall && element.symbol.owner.fqNameWhenAvailable?.asString()?.startsWith("klib") == true) {
                        check(functions.any { it === element.symbol.owner }) { "Call and loaded declaration identities differ" }
                    }
                    element.acceptChildrenVoid(this)
                }
            })
        }
        File(args[0], "loaded.ir").writeText(modules.joinToString("\n") { it.dump() })
        File(args[0], "bodies.txt").writeText(functions.joinToString("\n") {
            "${it.fqNameWhenAvailable}: ${it.file.fileEntry.name}:${it.startOffset}..${it.endOffset}; body=true"
        })
        val backend = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules()))
        val output = emitEtsModules(backend.lower(modules), StandardLibraryRuntime)
        val reversed = emitEtsModules(EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules()))
            .lower(modules.reversed()), StandardLibraryRuntime)
        check(output == reversed) { "Module input order changed ETS output" }
        functions.forEach { check(it.file.module in modules) { "Lowering changed IR ownership" } }
        output.forEach { (name, code) -> File(args[0], name).writeText(code) }
        println("PASS official KLIB loader: three modules, five real bodies, canonical transitive call symbols")
    } finally {
        Disposer.dispose(disposable)
    }
}
