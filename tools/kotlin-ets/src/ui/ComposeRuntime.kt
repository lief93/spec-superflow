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
                    "compose:surface" -> node is EtsReference && node.symbol.name == "EtsComposeSurface" &&
                        node.type == EtsFunctionType(listOf(EtsRecordType("SurfaceOptions",
                            mapOf("content" to EtsFunctionType(emptyList(), EtsTypes.VOID),
                                "fixedWidth" to EtsTypes.BOOLEAN, "fixedHeight" to EtsTypes.BOOLEAN))), EtsTypes.VOID)
                    "compose:imageTint" -> node is EtsReference && node.symbol.name == "__etsImageTint" &&
                        node.type == EtsFunctionType(listOf(EtsTypes.NUMBER), EtsNamedType("ColorFilter"))
                    "compose:nearestTouch" -> node is EtsReference && node.symbol.name == "__etsNearestTouch" &&
                        node.type == EtsFunctionType(listOf(EtsNamedType("Array", listOf(EtsNamedType("TouchTestInfo"))),
                            EtsTypes.NUMBER, EtsTypes.NUMBER, EtsTypes.NUMBER), EtsNamedType("TouchResult"))
                    "compose:materialTypography" -> node is EtsNew && node.classType == EtsNamedType("__etsMaterialTypography", symbolId = id, external = true) &&
                        node.arguments.size == 4 && node.arguments.all { it.type == EtsTypes.NUMBER }
                    else -> false
                }
                if (!valid) throw InvalidTarget(node.source, "Invalid framework runtime dependency: $id")
                required += id
            }
        } } }
        return languageRuntime.declarations(program) +
            (if ("compose:surface" in required) surfaceLayoutSupport else emptyList()) +
            (if ("compose:imageTint" in required) imageTintSupport else emptyList()) +
            (if ("compose:materialTypography" in required) materialTypographySupport else emptyList()) +
            (if ("compose:nearestTouch" in required) touchTargetSupport else emptyList())
    }
}
