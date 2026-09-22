@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import java.util.Base64
import java.util.Properties
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

/** Resource names come from materialization, never from an integer R value or source spelling. */
class ImageResources(private val resources: Map<String, String> = emptyMap(),
    private val files: Map<String, File> = emptyMap(), private val ids: Map<String, Int> = emptyMap(),
    private val unavailable: Map<String, String> = emptyMap(), private val unavailableIds: Map<Int, String> = emptyMap(),
    private val provenance: File? = null) : CallRule {
    private val used = linkedSetOf<String>()
    private var lookupUsed = false
    private val at = SourceSpan("EtsImageResources.kt", 0, 0)
    private val lookupSymbol = etsFunctionSymbol("__etsPainterResource", listOf(EtsTypes.NUMBER), RESOURCE, at)
    companion object {
        val RESOURCE = EtsNamedType("Resource", external = true)

        fun read(file: File): ImageResources {
            val values = object : Properties() {
                override fun put(key: Any, value: Any): Any? {
                    require(!containsKey(key)) { "Duplicate image resource symbol: $key" }
                    return super.put(key, value)
                }
            }
            file.inputStream().use(values::load)
            val resources = values.stringPropertyNames().associateWith(values::getProperty)
            val media = resources.mapValues { (symbol, name) ->
                require(Regex("[A-Za-z_][A-Za-z0-9_.]*\\.R\\.(drawable|mipmap)\\.[A-Za-z_][A-Za-z0-9_]*").matches(symbol)) {
                    "Invalid image resource symbol: $symbol"
                }
                require(Regex("[a-z][a-z0-9_]*").matches(name)) { "Invalid target media name: $name" }
                val files = file.parentFile.resolve("media").listFiles().orEmpty().filter { it.nameWithoutExtension == name }
                require(files.size == 1 && files.single().isFile && files.single().extension in setOf("png", "jpg", "jpeg", "webp", "svg")) {
                    "Image resource has no unique materialized media file: $symbol"
                }
                files.single()
            }
            val idFile = file.parentFile.resolve("source-resource-ids.properties")
            val ids = if (idFile.isFile) {
                val values = object : Properties() {
                    override fun put(key: Any, value: Any): Any? {
                        require(!containsKey(key)) { "Duplicate image resource ID symbol: $key" }
                        return super.put(key, value)
                    }
                }
                idFile.inputStream().use(values::load)
                values.stringPropertyNames().associateWith { symbol ->
                    require(symbol in resources) { "Image resource ID has no materialized image: $symbol" }
                    val number = java.lang.Long.decode(values.getProperty(symbol))
                    require(number in 1..Int.MAX_VALUE.toLong()) { "Invalid Android image resource ID: $symbol" }
                    number.toInt()
                }.also { mapping -> require(mapping.values.toSet().size == mapping.size) { "Ambiguous Android image resource IDs" } }
            } else emptyMap()
            val unsupportedFile = file.parentFile.resolve("unsupported-image-resources.properties")
            val unavailable = if (unsupportedFile.isFile) {
                val values = Properties()
                unsupportedFile.inputStream().use(values::load)
                values.stringPropertyNames().associateWith { symbol ->
                    require(Regex("[A-Za-z_][A-Za-z0-9_.]*\\.R\\.(drawable|mipmap)\\.[A-Za-z_][A-Za-z0-9_]*").matches(symbol)) {
                        "Invalid unsupported image resource symbol: $symbol"
                    }
                    String(Base64.getDecoder().decode(values.getProperty(symbol)), Charsets.UTF_8)
                }
            } else emptyMap()
            require(resources.keys.intersect(unavailable.keys).isEmpty()) { "Image resource cannot be both materialized and unsupported" }
            val unsupportedIdsFile = file.parentFile.resolve("unsupported-image-resource-ids.properties")
            val unavailableIds = if (unsupportedIdsFile.isFile) {
                val values = Properties()
                unsupportedIdsFile.inputStream().use(values::load)
                values.stringPropertyNames().associate { id ->
                    val number = id.toLong().also { require(it in 1..Int.MAX_VALUE.toLong()) { "Invalid unsupported image resource ID: $id" } }.toInt()
                    number to String(Base64.getDecoder().decode(values.getProperty(id)), Charsets.UTF_8)
                }
            } else emptyMap()
            val provenance = file.parentFile.resolve("image-resource-origins.json").takeIf(File::isFile)
            return ImageResources(resources, media, ids, unavailable, unavailableIds, provenance)
        }
    }

    fun artifacts(): Map<String, File> = used.associate { symbol ->
        "base/media/${files.getValue(symbol).name}" to files.getValue(symbol)
    } + if (used.isNotEmpty() && provenance != null) mapOf("image-resource-origins.json" to provenance) else emptyMap()

    override fun lowerField(value: IrGetField, language: Language, scope: Scope): EtsExpression? {
        if (value.receiver != null) return null
        val symbol = symbolName(value.symbol.owner)
        if (!Regex(".+\\.R\\.(drawable|mipmap)\\.[A-Za-z_][A-Za-z0-9_]*").matches(symbol)) return null
        unavailable[symbol]?.let { reject(value, language, "Unsupported Android image resource $symbol: $it") }
        val id = ids[symbol] ?: reject(value, language,
            "Image resource ID requires the selected build's R.txt metadata: $symbol; materialize with --symbols")
        used += symbol
        return EtsLiteral(id, EtsTypes.NUMBER, language.source(value))
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        if (!lookupUsed) return emptyList()
        val parameter = EtsParameter(EtsSymbol("imageResource:id", "id", EtsTypes.NUMBER, at))
        val cases = ids.map { (symbol, id) -> EtsBranch(
            EtsBinary("===", EtsReference(parameter.symbol), EtsLiteral(id, EtsTypes.NUMBER, at), EtsTypes.BOOLEAN, at),
            listOf(EtsReturn(targetResource(symbol, at), at))) }
        val fail = EtsCall(EtsReference(EtsSymbol("stdlib:__etsIllegalArgumentException", "__etsIllegalArgumentException",
            EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.NEVER), at, true)),
            listOf(EtsLiteral("Unmapped Android painter resource ID", EtsTypes.STRING, at)), EtsTypes.NEVER, at)
        val function = EtsFunction(lookupSymbol.name, listOf(parameter), RESOURCE,
            listOf(EtsIf(cases, at), EtsReturn(fail, at)), at, exported = true)
        return listOf(EtsFile(at.file!!, listOf(function)))
    }

    override fun mapType(type: IrType, language: Language): EtsType? =
        if (type.classFqName?.asString() == "androidx.compose.ui.graphics.painter.Painter") RESOURCE else null

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        if (symbolName(call.symbol.owner) != "androidx.compose.ui.res.painterResource") return null
        val id = argument(call, "id") ?: reject(call, language, "painterResource requires id")
        return resource(id, language, scope)
    }

    private fun resource(value: IrExpression, language: Language, scope: Scope): EtsExpression {
        if (value is IrGetValue && value.symbol !in scope.bindings)
            scope.aliases[value.symbol]?.let { return resource(it, language, scope) }
        ((value as? IrConst)?.value as? Int)?.let { id ->
            unavailableIds[id]?.let { reject(value, language, it) }
        }
        if (value is IrWhen && value.branches.size == 2 && value.branches.last() is IrElseBranch) {
            return EtsConditional(language.expression(value.branches[0].condition, scope),
                resource(value.branches[0].result, language, scope), resource(value.branches[1].result, language, scope),
                RESOURCE, language.source(value))
        }
        val symbol = when (value) {
            is IrGetField -> symbolName(value.symbol.owner)
            else -> null
        }
        if (symbol != null && Regex(".+\\.R\\.(drawable|mipmap)\\.[A-Za-z_][A-Za-z0-9_]*").matches(symbol)) {
            unavailable[symbol]?.let { reject(value, language, "Unsupported Android image resource $symbol: $it") }
            if (symbol !in resources) reject(value, language, "Unmapped image resource: $symbol; supply materialized --image-resources")
            return targetResource(symbol, language.source(value))
        }
        if (ids.isEmpty()) reject(value, language, "Dynamic painterResource ID requires the selected build's R.txt metadata; materialize with --symbols")
        val id = language.expression(value, scope)
        if (id.type != EtsTypes.NUMBER) reject(value, language, "painterResource requires an Int resource ID")
        lookupUsed = true
        used += ids.keys
        return EtsCall(EtsReference(lookupSymbol, language.source(value)), listOf(id), RESOURCE, language.source(value))
    }

    private fun targetResource(symbol: String, source: SourceSpan): EtsExpression {
        used += symbol
        val name = resources.getValue(symbol)
        val function = EtsReference(EtsSymbol("arkui:resource", "\$r", EtsFunctionType(listOf(EtsTypes.STRING), RESOURCE), source, true))
        return EtsCall(function, listOf(EtsLiteral("app.media.$name", EtsTypes.STRING, source)), RESOURCE, source)
    }

    private fun reject(value: IrExpression, language: Language, message: String): Nothing =
        throw Unsupported(Diagnostic("UNSUPPORTED", message, language.source(value)))
}
