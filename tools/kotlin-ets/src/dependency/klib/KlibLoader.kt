package dev.ets.dependency.klib

import java.io.File
import org.jetbrains.kotlin.backend.common.linkage.issues.checkNoUnboundSymbols
import org.jetbrains.kotlin.cli.common.CLIConfigurationKeys
import org.jetbrains.kotlin.cli.common.messages.MessageCollector
import org.jetbrains.kotlin.cli.common.messages.MessageRenderer
import org.jetbrains.kotlin.cli.common.messages.PrintingMessageCollector
import org.jetbrains.kotlin.cli.jvm.compiler.EnvironmentConfigFiles
import org.jetbrains.kotlin.cli.jvm.compiler.KotlinCoreEnvironment
import org.jetbrains.kotlin.com.intellij.openapi.util.Disposer
import org.jetbrains.kotlin.config.CommonConfigurationKeys
import org.jetbrains.kotlin.config.CompilerConfiguration
import org.jetbrains.kotlin.config.LanguageVersionSettingsImpl
import org.jetbrains.kotlin.ir.backend.js.MainModule
import org.jetbrains.kotlin.ir.backend.js.ModulesStructure
import org.jetbrains.kotlin.ir.backend.js.loadIr
import org.jetbrains.kotlin.ir.declarations.IrModuleFragment
import org.jetbrains.kotlin.ir.declarations.impl.IrFactoryImpl
import org.jetbrains.kotlin.ir.linkage.partial.PartialLinkageConfig
import org.jetbrains.kotlin.ir.linkage.partial.PartialLinkageLogLevel
import org.jetbrains.kotlin.ir.linkage.partial.PartialLinkageMode

/**
 * Production KLIB loader. Reuses official ModulesStructure / loadIr / JsIrLinker.
 * Does not copy the linker, invent a combined module, or treat JS stdlib as ETS
 * runtime. Partial linkage is disabled so missing dependencies fail closed.
 */
object KlibLoader {
    fun <T> withKlibModules(
        selection: KlibModuleSelection,
        moduleName: String = "ets-klib",
        emit: (KlibSession) -> T,
    ): T {
        val disposable = Disposer.newDisposable()
        var session: KlibSession? = null
        val collector = PrintingMessageCollector(System.err, MessageRenderer.PLAIN_FULL_PATHS, false)
        try {
            val configuration = CompilerConfiguration().apply {
                put(CommonConfigurationKeys.MODULE_NAME, moduleName)
                put(CommonConfigurationKeys.LANGUAGE_VERSION_SETTINGS, LanguageVersionSettingsImpl.DEFAULT)
                put(CLIConfigurationKeys.MESSAGE_COLLECTOR_KEY, collector)
                put(
                    PartialLinkageConfig.KEY,
                    PartialLinkageConfig(PartialLinkageMode.DISABLE, PartialLinkageLogLevel.ERROR),
                )
            }
            val environment = KotlinCoreEnvironment.createForProduction(
                disposable, configuration, EnvironmentConfigFiles.JS_CONFIG_FILES)
            val structure = ModulesStructure(
                environment.project,
                MainModule.Klib(selection.main.canonicalPath),
                configuration,
                selection.resolverPaths(),
                emptyList(),
            )
            val loaded = loadIr(structure, IrFactoryImpl)
            loaded.deserializer.checkNoUnboundSymbols(loaded.symbolTable, "before ETS lowering")
            val modules = selectTranslatedModules(structure, loaded.allDependencies, selection)
            val created = KlibSession(modules, loaded, selection)
            session = created
            return emit(created)
        } finally {
            session?.close()
            Disposer.dispose(disposable)
        }
    }

    /**
     * Official resolver descriptors identify ownership. Do not use
     * moduleFragmentToUniqueName: in Kotlin 2.1.20 it records only optional
     * klib.jsOutputName.
     */
    internal fun selectTranslatedModules(
        structure: ModulesStructure,
        loaded: List<IrModuleFragment>,
        selection: KlibModuleSelection,
    ): List<IrModuleFragment> {
        val translatedPaths = selection.translatedCanonicalPaths()
        val descriptors = structure.allDependencies
            .filter { File(it.libraryFile.canonicalPath).canonicalPath in translatedPaths }
            .map { structure.getModuleDescriptor(it) }
        val modules = loaded.filter { module -> descriptors.any { it === module.descriptor } }
        check(modules.size == translatedPaths.size) {
            "Official KLIB selection resolved ${modules.size} modules for ${translatedPaths.size} translated libraries"
        }
        return modules
    }
}
