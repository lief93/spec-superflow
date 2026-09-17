@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import java.security.MessageDigest
import java.util.Properties
import org.jetbrains.kotlin.ir.expressions.*

/** Strings remain native resources; resource IDs are resolved symbols, never guessed numbers. */
class StringResources(
    private val variants: Map<String, Map<String, String>> = emptyMap(),
    private val errors: Map<String, String> = emptyMap(),
    private val ids: Map<String, Int> = emptyMap(),
) : CallRule {
    private val used = linkedSetOf<String>()
    private var lookupUsed = false
    private val at = SourceSpan("EtsStringResources.kt", 0, 0)
    private val lookup = etsFunctionSymbol("__etsStringResourceId", listOf(EtsTypes.NUMBER), EtsTypes.NUMBER, at)

    companion object {
        fun read(directory: File): StringResources {
            require(directory.isDirectory) { "String resource input must be a directory: $directory" }
            val packs = directory.listFiles().orEmpty().filter { it.extension == "properties" && it.name != "source-resource-ids.properties" }.associate { file ->
                require(file.nameWithoutExtension == "unsupported" || file.nameWithoutExtension == "base" ||
                    Regex("[a-z]{2}(_[A-Z]{2})?").matches(file.nameWithoutExtension)) { "Unsupported resource qualifier: $file" }
                val values = object : Properties() {
                    override fun put(key: Any, value: Any): Any? {
                        require(!containsKey(key)) { "Duplicate string resource symbol: $key" }
                        return super.put(key, value)
                    }
                }
                file.reader(Charsets.UTF_8).use(values::load)
                file.nameWithoutExtension to values.stringPropertyNames().associateWith { symbol ->
                    require(Regex("[A-Za-z_][A-Za-z0-9_.]*\\.R\\.string\\.[A-Za-z_][A-Za-z0-9_]*").matches(symbol)) {
                        "Invalid string resource symbol: $symbol"
                    }
                    values.getProperty(symbol)
                }
            }
            require("base" in packs) { "String resource input requires base.properties" }
            val idFile = directory.resolve("source-resource-ids.properties")
            val ids = if (idFile.isFile) {
                val values = object : Properties() {
                    override fun put(key: Any, value: Any): Any? {
                        require(!containsKey(key)) { "Duplicate string resource ID symbol: $key" }
                        return super.put(key, value)
                    }
                }
                idFile.reader(Charsets.UTF_8).use(values::load)
                values.stringPropertyNames().associateWith { symbol ->
                    require(symbol in packs.getValue("base")) { "String ID has no materialized resource: $symbol" }
                    val id = java.lang.Long.decode(values.getProperty(symbol))
                    require(id in 1..Int.MAX_VALUE.toLong()) { "Invalid string resource ID: $symbol" }
                    id.toInt()
                }.also { require(it.values.toSet().size == it.size) { "Ambiguous string resource IDs" } }
            } else emptyMap()
            return StringResources(packs - "unsupported", packs["unsupported"].orEmpty(), ids)
        }
    }

    private fun name(symbol: String): String = "str_" + MessageDigest.getInstance("SHA-256")
        .digest(symbol.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }

    fun artifacts(): Map<String, String> = variants.toSortedMap().mapNotNull { (qualifier, values) ->
        val entries = used.sorted().mapNotNull { symbol -> values[symbol]?.let { value ->
            "{\"name\":${quote(name(symbol))},\"value\":${quote(value)}}"
        } }
        if (entries.isEmpty()) null else "$qualifier/element/string.json" to "{\"string\":[${entries.joinToString(",") }]}\n"
    }.toMap()

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        if (symbolName(call.symbol.owner) != "androidx.compose.ui.res.stringResource") return null
        val id = resource(argument(call, "id") ?: reject(call, language, "stringResource requires id"), language, scope)
        val args = argument(call, "formatArgs")
        if (call.symbol.owner.valueParameters.size > 1) {
            val values = args?.let { language.expression(it, scope) }
                ?: EtsArray(emptyList(), EtsTypes.OBJECT, language.source(call))
            return EtsCall(EtsReference(EtsSymbol("compose:formatString", "__etsFormatString", stringFormatType,
                language.source(call), true)), listOf(id, values), EtsTypes.STRING, language.source(call))
        }
        return read(id)
    }

    override fun lowerField(value: IrGetField, language: Language, scope: Scope): EtsExpression? {
        if (value.receiver != null) return null
        val symbol = symbolName(value.symbol.owner)
        if (!Regex(".+\\.R\\.string\\.[A-Za-z_][A-Za-z0-9_]*").matches(symbol)) return null
        checkSymbol(symbol, value, language)
        val id = ids[symbol] ?: reject(value, language, "String resource ID requires the selected build's R.txt metadata: $symbol; materialize with --symbols")
        used += symbol
        return EtsLiteral(id, EtsTypes.NUMBER, language.source(value))
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        if (!lookupUsed) return emptyList()
        val parameter = EtsParameter(EtsSymbol("stringResource:id", "id", EtsTypes.NUMBER, at))
        val cases = ids.filterKeys { it !in errors }.map { (symbol, id) -> EtsBranch(
            EtsBinary("===", EtsReference(parameter.symbol), EtsLiteral(id, EtsTypes.NUMBER, at), EtsTypes.BOOLEAN, at),
            listOf(EtsReturn(targetId(symbol, at), at))) }
        val fail = EtsCall(EtsReference(EtsSymbol("stdlib:__etsIllegalArgumentException", "__etsIllegalArgumentException",
            EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.NEVER), at, true)),
            listOf(EtsLiteral("Unmapped Android string resource ID", EtsTypes.STRING, at)), EtsTypes.NEVER, at)
        return listOf(EtsFile(at.file!!, listOf(EtsFunction(lookup.name, listOf(parameter), EtsTypes.NUMBER,
            listOf(EtsIf(cases, at), EtsReturn(fail, at)), at, exported = true))))
    }

    private fun resource(value: IrExpression, language: Language, scope: Scope): EtsExpression {
        if (value is IrGetValue && value.symbol !in scope.bindings) scope.aliases[value.symbol]?.let { return resource(it, language, scope) }
        if (value is IrWhen && value.branches.size == 2 && value.branches.last() is IrElseBranch) {
            return EtsConditional(language.expression(value.branches[0].condition, scope),
                resource(value.branches[0].result, language, scope), resource(value.branches[1].result, language, scope),
                EtsTypes.NUMBER, language.source(value))
        }
        val symbol = (value as? IrGetField)?.takeIf { it.receiver == null }?.symbol?.owner?.let(::symbolName)
        if (symbol != null) {
            checkSymbol(symbol, value, language)
            used += symbol
            return targetId(symbol, language.source(value))
        }
        if (ids.isEmpty()) reject(value, language, "Dynamic stringResource ID requires the selected build's R.txt metadata; materialize with --symbols")
        val id = language.expression(value, scope)
        if (id.type != EtsTypes.NUMBER) reject(value, language, "stringResource requires an Int resource ID")
        lookupUsed = true
        used += ids.keys.filter { it !in errors }
        return EtsCall(EtsReference(lookup, language.source(value)), listOf(id), EtsTypes.NUMBER, language.source(value))
    }

    private fun checkSymbol(symbol: String, value: IrExpression, language: Language) {
        errors[symbol]?.let { reject(value, language, "Unsupported string resource $symbol: $it") }
        if (symbol !in variants["base"].orEmpty()) reject(value, language,
            "Unmapped string resource: $symbol; supply --string-resources input directory")
    }

    private fun targetId(symbol: String, at: SourceSpan): EtsExpression {
        val resourceType = EtsNamedType("Resource")
        val reference = EtsCall(EtsReference(EtsSymbol("arkui:resource", "\$r",
            EtsFunctionType(listOf(EtsTypes.STRING), resourceType), at, true)),
            listOf(EtsLiteral("app.string.${name(symbol)}", EtsTypes.STRING, at)), resourceType, at)
        return EtsMember(reference, "id", EtsTypes.NUMBER, at, "arkui:Resource.id")
    }

    private fun read(id: EtsExpression): EtsExpression {
        val at = id.source
        val contextType = EtsNamedType("Context")
        val context = EtsCall(EtsReference(EtsSymbol("arkui:getContext", "getContext",
            EtsFunctionType(emptyList(), contextType), at, true)), emptyList(), contextType, at)
        val manager = EtsMember(context, "resourceManager", EtsNamedType("ResourceManager"), at)
        return EtsCall(EtsMember(manager, "getStringSync", EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.STRING), at,
            "arkui:ResourceManager.getStringSync"),
            listOf(id), EtsTypes.STRING, at)
    }

    private fun reject(value: IrExpression, language: Language, message: String): Nothing =
        throw Unsupported(Diagnostic("UNSUPPORTED", message, language.source(value)))
}
