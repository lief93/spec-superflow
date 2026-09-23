package dev.ets

/** Fixed framework support is selected from typed dependencies, never page source text. */
class ComposeRuntime(private val languageRuntime: EtsRuntimeSupport) : EtsRuntimeSupport {
    override fun declarations(program: EtsProgram): List<String> {
        val required = linkedSetOf<String>()
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
            val id = when (node) {
                is EtsReference -> node.symbol.id.takeIf { node.symbol.external }
                is EtsNew -> node.classType.symbolId.takeIf { node.classType.external }
                else -> null
            }
            if (id?.startsWith("compose:") == true) {
                val valid = when (id) {
                    "compose:formatString" -> node is EtsReference && node.symbol.name == "__etsFormatString" && node.type == stringFormatType
                    "compose:formatPlural" -> node is EtsReference && node.symbol.name == "__etsFormatPlural" && node.type == pluralFormatType
                    "compose:boxConstraints" -> {
                        val options = ((node as? EtsReference)?.type as? EtsFunctionType)?.parameters?.singleOrNull() as? EtsRecordType
                        val data = options?.fields?.get("data")
                        node is EtsReference && node.symbol.name == "EtsComposeBoxWithConstraints" && data != null &&
                            node.type == EtsFunctionType(listOf(boxConstraintsOptions(data)), EtsTypes.VOID)
                    }
                    "compose:surface" -> node is EtsReference && node.symbol.name == "EtsComposeSurface" &&
                        node.type == EtsFunctionType(listOf(EtsRecordType("SurfaceOptions",
                            mapOf("content" to EtsFunctionType(emptyList(), EtsTypes.VOID),
                                "column" to EtsTypes.BOOLEAN, "fixedWidth" to EtsTypes.BOOLEAN,
                                "fixedHeight" to EtsTypes.BOOLEAN))), EtsTypes.VOID)
                    "compose:imageTint" -> node is EtsReference && node.symbol.name == "__etsImageTint" &&
                        node.type == EtsFunctionType(listOf(EtsTypes.NUMBER), EtsNamedType("ColorFilter"))
                    "compose:optionalImageFilter" -> node is EtsReference && node.symbol.name == "__etsOptionalImageFilter" &&
                        node.type == EtsFunctionType(listOf(EtsNullableType(EtsNamedType("ColorFilter"))),
                            EtsNamedType("ColorFilter"))
                    "compose:nearestTouch" -> node is EtsReference && node.symbol.name == "__etsNearestTouch" &&
                        node.type == EtsFunctionType(listOf(EtsNamedType("Array", listOf(EtsNamedType("TouchTestInfo"))),
                            EtsTypes.NUMBER, EtsTypes.NUMBER, EtsTypes.NUMBER), EtsNamedType("TouchResult"))
                    "compose:materialTypography" -> node is EtsNew && node.classType == EtsNamedType("__etsMaterialTypography", symbolId = id, external = true) &&
                        node.arguments.size == 4 && node.arguments.all { it.type == EtsTypes.NUMBER }
                    "compose:clearFocus" -> node is EtsReference && node.symbol.name == "__etsClearFocus" &&
                        node.type == EtsFunctionType(emptyList(), EtsTypes.VOID)
                    "compose:activeUIContext" -> node is EtsReference && node.symbol.name == "__etsActiveUIContext" &&
                        node.type == EtsNullableType(focusUIContextType)
                    else -> false
                }
                if (!valid) throw InvalidTarget(node.source, "Invalid framework runtime dependency: $id")
                required += id
            }
        } } }
        return languageRuntime.declarations(program) +
            (if ("compose:formatString" in required || "compose:formatPlural" in required) stringFormatSupport else emptyList()) +
            (if ("compose:formatPlural" in required) pluralFormatSupport else emptyList()) +
            (if ("compose:boxConstraints" in required) constraintsLayoutSupport else emptyList()) +
            (if ("compose:surface" in required) surfaceLayoutSupport else emptyList()) +
            (if ("compose:imageTint" in required || "compose:optionalImageFilter" in required)
                imageTintSupport else emptyList()) +
            (if ("compose:materialTypography" in required) materialTypographySupport else emptyList()) +
            (if ("compose:nearestTouch" in required) touchTargetSupport else emptyList()) +
            (if ("compose:clearFocus" in required || "compose:activeUIContext" in required) focusSupport else emptyList())
    }
}
