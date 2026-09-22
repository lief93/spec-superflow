@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import dev.ets.widgets.ThemeModeRead
import dev.ets.widgets.ThemeModeSource
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.isBoolean

private val themeModeSource = SourceSpan("EtsThemeMode.kt", 0, 0)
private val themeModeReader = etsFunctionSymbol("__etsIsSystemInDarkTheme",
    emptyList(), EtsTypes.BOOLEAN, themeModeSource)

/** Reads Compose theme mode from the current Harmony application configuration. */
internal class ComposeThemeModeRule : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null || symbolName(owner) !=
            "androidx.compose.foundation.isSystemInDarkTheme") return null
        if (owner.valueParameters.isNotEmpty() || owner.dispatchReceiverParameter != null ||
            owner.extensionReceiverParameter != null || !owner.returnType.isBoolean() || !call.type.isBoolean())
            throw Unsupported(Diagnostic("UNSUPPORTED", "Unsupported isSystemInDarkTheme signature", language.source(call)))
        val read = ThemeModeRead(ThemeModeSource.APPLICATION_CONFIGURATION, language.source(call))
        return lower(read)
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        var used = false
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) {
            if (it is EtsReference && it.symbol.id == themeModeReader.id) used = true
        } } }
        return if (used) listOf(EtsFile(themeModeSource.file!!, listOf(helper()))) else emptyList()
    }

    override fun targetImports(program: EtsProgram): List<EtsImport> =
        if (targetFiles(program).isNotEmpty())
            listOf(EtsImport("@ohos.resourceManager", "__etsResourceManager", default = true)) else emptyList()

    private fun lower(read: ThemeModeRead<SourceSpan>): EtsExpression = when (read.source) {
        ThemeModeSource.APPLICATION_CONFIGURATION ->
            EtsCall(EtsReference(themeModeReader, read.location), emptyList(), EtsTypes.BOOLEAN, read.location)
    }

    private fun helper(): EtsFunction {
        val at = themeModeSource
        val managerType = EtsNamedType("__etsResourceManager.ResourceManager", external = true)
        val configurationType = EtsNamedType("__etsResourceManager.Configuration", external = true)
        val colorModeType = EtsNamedType("__etsResourceManager.ColorMode", external = true)
        val context = EtsCall(EtsReference(EtsSymbol("arkui:getContext", "getContext",
            EtsFunctionType(emptyList(), nativeHostContextType), at, external = true)),
            emptyList(), nativeHostContextType, at)
        val resources = EtsMember(context, "resourceManager", managerType, at)
        val configuration = EtsCall(EtsMember(resources, "getConfigurationSync",
            EtsFunctionType(emptyList(), configurationType), at), emptyList(), configurationType, at)
        val mode = EtsMember(configuration, "colorMode", colorModeType, at)
        val api = EtsReference(EtsSymbol("arkui:resource-manager", "__etsResourceManager",
            EtsNamedType("ResourceManagerApi", external = true), at, external = true))
        val dark = EtsMember(EtsMember(api, "ColorMode", colorModeType, at), "DARK", colorModeType, at)
        return EtsFunction(themeModeReader.name, emptyList(), EtsTypes.BOOLEAN,
            listOf(EtsReturn(EtsBinary("===", mode, dark, EtsTypes.BOOLEAN, at), at)), at, exported = true)
    }
}
