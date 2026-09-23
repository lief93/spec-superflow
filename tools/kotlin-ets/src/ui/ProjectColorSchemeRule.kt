@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.declarations.IrDeclaration

private val currentProjectPalette = etsFunctionSymbol("__etsCurrentProjectColorScheme",
    emptyList(), materialColorSchemeType, SourceSpan("EtsProjectColorScheme.kt", 0, 0))

internal fun currentProjectColorScheme(at: SourceSpan): EtsExpression =
    EtsCall(EtsReference(currentProjectPalette), emptyList(), materialColorSchemeType, at)

/** Project resource palettes intentionally replace Android wallpaper-derived colors. */
internal class ComposeProjectColorSchemeRule : CallRule {
    private val at = SourceSpan("EtsProjectColorScheme.kt", 0, 0)
    private val managerType = EtsNamedType("__etsResourceManager.ResourceManager", external = true)
    private val configurationType = EtsNamedType("__etsResourceManager.Configuration", external = true)
    private val paletteType = etsClassSymbol("EtsProjectColorScheme", at).type as EtsNamedType
    private val reader = colorReader()
    private val factory = colorFactory()
    private var requiresResources = false

    override fun prepareSource(declaration: IrDeclaration, diagnostics: DiagnosticSink) {
        requiresResources = projectAndroidTheme(declaration, diagnostics) || requiresResources
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val api = symbolName(owner)
        if (api !in setOf("androidx.compose.material3.dynamicLightColorScheme",
                "androidx.compose.material3.dynamicDarkColorScheme")) return null
        if (owner.valueParameters.map { it.name.asString() } != listOf("context") ||
            owner.dispatchReceiverParameter != null || owner.extensionReceiverParameter != null)
            throw Unsupported(Diagnostic("UNSUPPORTED", "Unsupported dynamic ColorScheme signature", language.source(call)))
        requiresResources = true
        val context = argument(call, "context") ?: throw Unsupported(Diagnostic("UNSUPPORTED",
            "Project ColorScheme requires a native host Context", language.source(call)))
        return EtsCall(EtsReference(factory.symbol), listOf(language.expression(context, scope),
            EtsLiteral(api.endsWith(".dynamicDarkColorScheme"), EtsTypes.BOOLEAN, language.source(call))),
            materialColorSchemeType, language.source(call))
    }

    fun artifacts(): Map<String, String> = if (!requiresResources) emptyMap() else mapOf(
        "base/element/color.json" to colorResources(dark = false),
        "dark/element/color.json" to colorResources(dark = true),
    )

    private fun colorResources(dark: Boolean): String = buildString {
        append("{\n  \"color\": [\n")
        materialColorSchemeDefaults.entries.forEachIndexed { index, (role, defaults) ->
            val name = role.replace(Regex("([A-Z])")) { "_" + it.value.lowercase() }
            val value = (if (dark) defaults.second else defaults.first).toString(16).uppercase().padStart(8, '0')
            append("    { \"name\": \"kotlin_ets_material_").append(name)
                .append("\", \"value\": \"#").append(value).append("\" }")
            if (index != materialColorSchemeDefaults.size - 1) append(',')
            append('\n')
        }
        append("  ]\n}\n")
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        var used = false
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) {
            if (it is EtsReference && it.symbol.id in setOf(factory.symbol.id, currentProjectPalette.id)) used = true
        } } }
        return if (used) listOf(EtsFile(at.file!!, listOf(reader, paletteClass(), factory, currentFactory()))) else emptyList()
    }

    override fun targetImports(program: EtsProgram): List<EtsImport> =
        if (targetFiles(program).isNotEmpty()) listOf(EtsImport("@ohos.resourceManager", "__etsResourceManager", default = true)) else emptyList()

    private fun colorReader(): EtsFunction {
        val manager = EtsParameter(EtsSymbol("project-theme:manager", "resources", managerType, at))
        val name = EtsParameter(EtsSymbol("project-theme:resource", "resourceName", EtsTypes.STRING, at))
        val read = EtsCall(EtsMember(EtsReference(manager.symbol), "getColorByNameSync",
            EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.NUMBER), at), listOf(EtsReference(name.symbol)), EtsTypes.NUMBER, at)
        val caught = EtsSymbol("project-theme:error", "error", EtsTypes.OBJECT, at)
        val errorType = EtsNamedType("Error", external = true)
        val message = EtsBinary("+", EtsBinary("+", EtsLiteral("Cannot read project theme color: ", EtsTypes.STRING, at),
            EtsReference(name.symbol), EtsTypes.STRING, at),
            EtsBinary("+", EtsLiteral("; ", EtsTypes.STRING, at),
                EtsMember(EtsCast(EtsReference(caught), errorType, at), "message", EtsTypes.STRING, at), EtsTypes.STRING, at), EtsTypes.STRING, at)
        return EtsFunction("__etsProjectThemeColor", listOf(manager, name), EtsTypes.NUMBER, listOf(
            EtsTry(listOf(EtsReturn(read, at)), EtsCatch(caught, listOf(EtsThrow(EtsNew(errorType, listOf(message), at), at))), source = at)), at)
    }

    private fun currentFactory(): EtsFunction {
        val context = EtsCall(EtsReference(EtsSymbol("arkui:getContext", "getContext",
            EtsFunctionType(emptyList(), nativeHostContextType), at, external = true)), emptyList(), nativeHostContextType, at)
        val resources = EtsMember(context, "resourceManager", managerType, at)
        return EtsFunction(currentProjectPalette.name, emptyList(), materialColorSchemeType,
            listOf(EtsReturn(EtsNew(paletteType, listOf(resources), at), at)), at,
            exported = true)
    }

    private fun colorFactory(): EtsFunction {
        val context = EtsParameter(EtsSymbol("project-theme:factory-context", "context", nativeHostContextType, at))
        val dark = EtsParameter(EtsSymbol("project-theme:dark", "dark", EtsTypes.BOOLEAN, at))
        val host = EtsMember(EtsReference(context.symbol), "resourceManager", managerType, at)
        val configuration = EtsSymbol("project-theme:configuration", "configuration", configurationType, at)
        val resources = EtsSymbol("project-theme:resources", "resources", managerType, at)
        val config = EtsCall(EtsMember(host, "getConfigurationSync",
            EtsFunctionType(emptyList(), configurationType), at), emptyList(), configurationType, at)
        val colorModeType = EtsNamedType("__etsResourceManager.ColorMode", external = true)
        val api = EtsReference(EtsSymbol("arkui:resource-manager", "__etsResourceManager",
            EtsNamedType("ResourceManagerApi", external = true), at, external = true))
        val mode = EtsMember(api, "ColorMode", colorModeType, at)
        val setMode = EtsAssignment(EtsMember(EtsReference(configuration), "colorMode", colorModeType, at),
            EtsConditional(EtsReference(dark.symbol), EtsMember(mode, "DARK", colorModeType, at),
                EtsMember(mode, "LIGHT", colorModeType, at), colorModeType, at), at)
        val override = EtsCall(EtsMember(host, "getOverrideResourceManager",
            EtsFunctionType(listOf(configurationType), managerType), at), listOf(EtsReference(configuration)), managerType, at)
        return EtsFunction("__etsProjectColorScheme", listOf(context, dark), materialColorSchemeType,
            listOf(EtsVariable(configuration, config, false), EtsExpressionStatement(setMode),
                EtsVariable(resources, override, false), EtsReturn(EtsNew(paletteType, listOf(EtsReference(resources)), at), at)), at, exported = true)
    }

    private fun paletteClass(): EtsClass {
        val resources = EtsSymbol("project-theme:stored-resources", "resources", managerType, at)
        val parameter = EtsParameter(EtsSymbol("project-theme:resource-parameter", "resources", managerType, at))
        val receiver = EtsReference(EtsSymbol("project-theme:this", "this", paletteType, at, external = true))
        val manager = EtsMember(receiver, resources.name, managerType, at, resources.id)
        val constructor = EtsFunction("constructor", listOf(parameter), EtsTypes.VOID,
            listOf(EtsExpressionStatement(EtsAssignment(manager, EtsReference(parameter.symbol), at))),
            at, kind = EtsFunctionKind.CONSTRUCTOR)
        val getters = materialColorSchemeDefaults.keys.map { role ->
            val suffix = role.replace(Regex("([A-Z])")) { "_" + it.value.lowercase() }
            val name = EtsLiteral("kotlin_ets_material_$suffix", EtsTypes.STRING, at)
            val read = EtsCall(EtsReference(reader.symbol), listOf(manager, name), EtsTypes.NUMBER, at)
            EtsFunction(role, emptyList(), EtsTypes.NUMBER, listOf(EtsReturn(read, at)), at, kind = EtsFunctionKind.GETTER)
        }
        return EtsClass(paletteType.name, listOf(EtsField(resources, visibility = EtsVisibility.PRIVATE, readonly = true), constructor) + getters,
            at, exported = true, interfaces = listOf(materialColorSchemeType))
    }
}
