@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import java.security.MessageDigest
import java.util.Base64
import java.util.Properties
import org.jetbrains.kotlin.ir.expressions.*

private enum class StringResourceKind(val android: String, val target: String, val prefix: String) {
    STRING("string", "string", "str_"), PLURAL("plurals", "plural", "plu_"), ARRAY("array", "strarray", "arr_");
    companion object {
        fun symbol(value: String): StringResourceKind? = entries.firstOrNull { ".R.${it.android}." in value }
    }
}

/** Values resources remain native resources; selected-build IDs are mapped by resolved symbol. */
class StringResources(
    private val variants: Map<String, Map<String, String>> = emptyMap(),
    private val errors: Map<String, String> = emptyMap(),
    private val ids: Map<String, Int> = emptyMap(),
    private val pluralVariants: Map<String, Map<String, Map<String, String>>> = emptyMap(),
    private val arrayVariants: Map<String, Map<String, List<String>>> = emptyMap(),
    private val unavailableIds: Map<Int, String> = emptyMap(),
    private val provenance: String? = null,
) : CallRule {
    private val used = linkedSetOf<String>()
    private val lookups = linkedSetOf<StringResourceKind>()
    private val at = SourceSpan("EtsStringResources.kt", 0, 0)

    companion object {
        private val SYMBOL = Regex("[A-Za-z_][A-Za-z0-9_.]*\\.R\\.(string|plurals|array)\\.[A-Za-z_][A-Za-z0-9_]*")
        private val QUALIFIER = Regex("[a-z]{2}(_[A-Z]{2})?")

        private fun properties(file: File, label: String): Map<String, String> {
            val values = object : Properties() {
                override fun put(key: Any, value: Any): Any? {
                    require(!containsKey(key)) { "Duplicate $label: $key" }
                    return super.put(key, value)
                }
            }
            file.reader(Charsets.UTF_8).use(values::load)
            return values.stringPropertyNames().associateWith(values::getProperty)
        }

        fun read(directory: File): StringResources {
            require(directory.isDirectory) { "String resource input must be a directory: $directory" }
            val strings = linkedMapOf<String, Map<String, String>>()
            val plurals = linkedMapOf<String, Map<String, Map<String, String>>>()
            val arrays = linkedMapOf<String, Map<String, List<String>>>()
            for (file in directory.listFiles().orEmpty().filter { it.extension == "properties" }) {
                val name = file.nameWithoutExtension
                when {
                    name == "source-resource-ids" || name.startsWith("unsupported") ||
                        name == "dimensions" || name == "dimension-qualifiers" -> Unit
                    name.startsWith("plurals-") -> {
                        val qualifier = name.removePrefix("plurals-")
                        require(qualifier == "base" || QUALIFIER.matches(qualifier)) { "Unsupported resource qualifier: $file" }
                        val grouped = linkedMapOf<String, MutableMap<String, String>>()
                        properties(file, "plural resource entry").forEach { (key, value) ->
                            val match = Regex("^(.+\\.R\\.plurals\\.[A-Za-z_][A-Za-z0-9_]*)\\.(zero|one|two|few|many|other)$").matchEntire(key)
                                ?: error("Invalid plural resource entry: $key")
                            grouped.getOrPut(match.groupValues[1]) { linkedMapOf() }[match.groupValues[2]] = value
                        }
                        grouped.forEach { (symbol, values) -> require("other" in values) { "Plural resource requires other: $symbol" } }
                        plurals[qualifier] = grouped
                    }
                    name.startsWith("arrays-") -> {
                        val qualifier = name.removePrefix("arrays-")
                        require(qualifier == "base" || QUALIFIER.matches(qualifier)) { "Unsupported resource qualifier: $file" }
                        val grouped = linkedMapOf<String, MutableMap<Int, String>>()
                        properties(file, "string-array entry").forEach { (key, value) ->
                            val match = Regex("^(.+\\.R\\.array\\.[A-Za-z_][A-Za-z0-9_]*)\\.([0-9]+)$").matchEntire(key)
                                ?: error("Invalid string-array entry: $key")
                            grouped.getOrPut(match.groupValues[1]) { linkedMapOf() }[match.groupValues[2].toInt()] = value
                        }
                        arrays[qualifier] = grouped.mapValues { (symbol, values) ->
                            require(values.keys == (0 until values.size).toSet()) { "Non-contiguous string-array entries: $symbol" }
                            values.toSortedMap().values.toList()
                        }
                    }
                    name == "base" || QUALIFIER.matches(name) -> strings[name] = properties(file, "string resource symbol").also { values ->
                        values.keys.forEach { require(Regex("[A-Za-z_][A-Za-z0-9_.]*\\.R\\.string\\.[A-Za-z_][A-Za-z0-9_]*").matches(it)) {
                            "Invalid string resource symbol: $it" } }
                    }
                    else -> error("Unsupported string resource input file: $file")
                }
            }
            require("base" in strings) { "String resource input requires base.properties" }
            val supported = strings["base"].orEmpty().keys + plurals["base"].orEmpty().keys + arrays["base"].orEmpty().keys
            val errors = linkedMapOf<String, String>()
            directory.resolve("unsupported.properties").takeIf(File::isFile)?.let { errors.putAll(properties(it, "unsupported string resource")) }
            directory.resolve("unsupported-string-resources.properties").takeIf(File::isFile)?.let { file ->
                properties(file, "unsupported values resource").forEach { (symbol, reason) ->
                    require(SYMBOL.matches(symbol)) { "Invalid unsupported values resource symbol: $symbol" }
                    errors[symbol] = String(Base64.getDecoder().decode(reason), Charsets.UTF_8)
                }
            }
            require(supported.intersect(errors.keys).isEmpty()) { "Values resource cannot be both materialized and unsupported" }
            val ids = directory.resolve("source-resource-ids.properties").takeIf(File::isFile)?.let { file ->
                properties(file, "string resource ID symbol").filterKeys { StringResourceKind.symbol(it) != null }.mapValues { (symbol, value) ->
                    require(symbol in supported) { "Values resource ID has no materialized resource: $symbol" }
                    java.lang.Long.decode(value).also { require(it in 1..Int.MAX_VALUE.toLong()) { "Invalid values resource ID: $symbol" } }.toInt()
                }.also { require(it.values.toSet().size == it.size) { "Ambiguous values resource IDs" } }
            }.orEmpty()
            val unavailableIds = directory.resolve("unsupported-string-resource-ids.properties").takeIf(File::isFile)?.let { file ->
                properties(file, "unsupported values resource ID").map { (id, reason) ->
                    id.toLong().also { require(it in 1..Int.MAX_VALUE.toLong()) { "Invalid unsupported values resource ID: $id" } }.toInt() to
                        String(Base64.getDecoder().decode(reason), Charsets.UTF_8)
                }.toMap()
            }.orEmpty()
            require((ids.values.toSet() intersect unavailableIds.keys).isEmpty()) { "Values resource ID cannot be supported and unsupported" }
            val provenance = directory.resolve("string-resource-origins.json").takeIf(File::isFile)?.readText()
            return StringResources(strings, errors, ids, plurals, arrays, unavailableIds, provenance)
        }
    }

    private fun name(symbol: String): String {
        val kind = requireNotNull(StringResourceKind.symbol(symbol))
        return kind.prefix + MessageDigest.getInstance("SHA-256").digest(symbol.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
    }

    fun artifacts(): Map<String, String> {
        val output = linkedMapOf<String, String>()
        variants.toSortedMap().forEach { (qualifier, values) ->
            val entries = used.sorted().mapNotNull { symbol -> values[symbol]?.let { value ->
                "{\"name\":${quote(name(symbol))},\"value\":${quote(value)}}"
            } }
            if (entries.isNotEmpty()) output["$qualifier/element/string.json"] = "{\"string\":[${entries.joinToString(",")}]}\n"
        }
        pluralVariants.toSortedMap().forEach { (qualifier, values) ->
            val entries = used.sorted().mapNotNull { symbol -> values[symbol]?.let { quantities ->
                val items = quantities.toSortedMap().map { (quantity, value) ->
                    "{\"quantity\":${quote(quantity)},\"value\":${quote(value)}}" }
                "{\"name\":${quote(name(symbol))},\"value\":[${items.joinToString(",")}] }"
            } }
            if (entries.isNotEmpty()) output["$qualifier/element/plural.json"] = "{\"plural\":[${entries.joinToString(",")}]}\n"
        }
        arrayVariants.toSortedMap().forEach { (qualifier, values) ->
            val entries = used.sorted().mapNotNull { symbol -> values[symbol]?.let { items ->
                val valuesJson = items.joinToString(",") { "{\"value\":${quote(it)}}" }
                "{\"name\":${quote(name(symbol))},\"value\":[$valuesJson]}"
            } }
            if (entries.isNotEmpty()) output["$qualifier/element/strarray.json"] = "{\"strarray\":[${entries.joinToString(",")}]}\n"
        }
        if (used.isNotEmpty() && provenance != null) output["string-resource-origins.json"] = provenance
        return output
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = when (symbolName(call.symbol.owner)) {
        "android.content.Context.getString" -> {
            val idSource = call.getValueArgument(0)
                ?: reject(call, language, "Context.getString requires a resource id")
            val id = resource(idSource, StringResourceKind.STRING, language, scope)
            val args = call.symbol.owner.valueParameters.getOrNull(1)?.let { call.getValueArgument(1) }
            if (args == null) read(id) else format(id, args, call, language, scope)
        }
        "androidx.compose.ui.res.stringResource" -> {
            val id = resource(argument(call, "id") ?: reject(call, language, "stringResource requires id"), StringResourceKind.STRING, language, scope)
            val args = argument(call, "formatArgs")
            if (call.symbol.owner.valueParameters.any { it.name.asString() == "formatArgs" }) format(id, args, call, language, scope) else read(id)
        }
        "androidx.compose.ui.res.pluralStringResource" -> {
            val id = resource(argument(call, "id") ?: reject(call, language, "pluralStringResource requires id"), StringResourceKind.PLURAL, language, scope)
            val countValue = argument(call, "count") ?: argument(call, "quantity")
                ?: reject(call, language, "pluralStringResource requires count")
            val count = language.expression(countValue, scope)
            if (count.type != EtsTypes.NUMBER) reject(countValue, language, "pluralStringResource count requires Int")
            val args = argument(call, "formatArgs")?.let { language.expression(it, scope) }
                ?: EtsArray(emptyList(), EtsTypes.OBJECT, language.source(call))
            EtsCall(EtsReference(EtsSymbol("compose:formatPlural", "__etsFormatPlural", pluralFormatType,
                language.source(call), true)), listOf(id, count, args), EtsTypes.STRING, language.source(call))
        }
        else -> null
    }

    private fun format(id: EtsExpression, args: IrExpression?, call: IrCall, language: Language, scope: Scope): EtsExpression {
        val values = args?.let { language.expression(it, scope) } ?: EtsArray(emptyList(), EtsTypes.OBJECT, language.source(call))
        return EtsCall(EtsReference(EtsSymbol("compose:formatString", "__etsFormatString", stringFormatType,
            language.source(call), true)), listOf(id, values), EtsTypes.STRING, language.source(call))
    }

    override fun lowerField(value: IrGetField, language: Language, scope: Scope): EtsExpression? {
        if (value.receiver != null) return null
        val symbol = symbolName(value.symbol.owner)
        val kind = StringResourceKind.symbol(symbol) ?: return null
        checkSymbol(symbol, kind, value, language)
        val id = ids[symbol] ?: reject(value, language, "Values resource ID requires the selected build's R.txt metadata: $symbol; materialize with --symbols")
        used += symbol
        return EtsLiteral(id, EtsTypes.NUMBER, language.source(value))
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> = if (lookups.isEmpty()) emptyList() else listOf(EtsFile(at.file!!,
        lookups.map { kind ->
            val parameter = EtsParameter(EtsSymbol("${kind.android}Resource:id", "id", EtsTypes.NUMBER, at))
            val cases = ids.filterKeys { StringResourceKind.symbol(it) == kind }.map { (symbol, id) -> EtsBranch(
                EtsBinary("===", EtsReference(parameter.symbol), EtsLiteral(id, EtsTypes.NUMBER, at), EtsTypes.BOOLEAN, at),
                listOf(EtsReturn(targetId(symbol, at), at))) }
            val fail = EtsCall(EtsReference(EtsSymbol("stdlib:__etsIllegalArgumentException", "__etsIllegalArgumentException",
                EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.NEVER), at, true)),
                listOf(EtsLiteral("Unmapped Android ${kind.android} resource ID", EtsTypes.STRING, at)), EtsTypes.NEVER, at)
            val lookup = lookup(kind)
            EtsFunction(lookup.name, listOf(parameter), EtsTypes.NUMBER,
                listOf(EtsIf(cases, at), EtsReturn(fail, at)), at, exported = true)
        }))

    private fun lookup(kind: StringResourceKind) = etsFunctionSymbol(when (kind) {
        StringResourceKind.STRING -> "__etsStringResourceId"
        StringResourceKind.PLURAL -> "__etsPluralResourceId"
        StringResourceKind.ARRAY -> "__etsStringArrayResourceId"
    }, listOf(EtsTypes.NUMBER), EtsTypes.NUMBER, at)

    private fun resource(value: IrExpression, kind: StringResourceKind, language: Language, scope: Scope): EtsExpression {
        if (value is IrGetValue && value.symbol !in scope.bindings) scope.aliases[value.symbol]?.let { return resource(it, kind, language, scope) }
        ((value as? IrConst)?.value as? Int)?.let { id ->
            unavailableIds[id]?.let { reject(value, language, it) }
            val symbol = ids.entries.singleOrNull { it.value == id }?.key
            if (symbol != null) {
                if (StringResourceKind.symbol(symbol) != kind) reject(value, language, "Resource ID $id is ${StringResourceKind.symbol(symbol)?.android}, not ${kind.android}")
                return targetId(symbol, language.source(value))
            }
            if (ids.isNotEmpty()) reject(value, language, "Unknown selected-build Android ${kind.android} resource ID: $id")
        }
        if (value is IrWhen && value.branches.size == 2 && value.branches.last() is IrElseBranch) {
            return EtsConditional(language.expression(value.branches[0].condition, scope),
                resource(value.branches[0].result, kind, language, scope), resource(value.branches[1].result, kind, language, scope),
                EtsTypes.NUMBER, language.source(value))
        }
        val symbol = (value as? IrGetField)?.takeIf { it.receiver == null }?.symbol?.owner?.let(::symbolName)
        if (symbol != null) {
            checkSymbol(symbol, kind, value, language)
            return targetId(symbol, language.source(value))
        }
        val available = ids.filterKeys { StringResourceKind.symbol(it) == kind }
        if (available.isEmpty()) reject(value, language,
            "Dynamic ${if (kind == StringResourceKind.PLURAL) "pluralStringResource" else "stringResource"} ID requires the selected build's R.txt metadata; materialize with --symbols")
        val id = language.expression(value, scope)
        if (id.type != EtsTypes.NUMBER) reject(value, language, "${kind.android} resource requires an Int resource ID")
        lookups += kind
        used += available.keys
        return EtsCall(EtsReference(lookup(kind), language.source(value)), listOf(id), EtsTypes.NUMBER, language.source(value))
    }

    private fun checkSymbol(symbol: String, expected: StringResourceKind, value: IrExpression, language: Language) {
        val actual = StringResourceKind.symbol(symbol)
        if (actual != expected) reject(value, language, "Resource $symbol is ${actual?.android}, not ${expected.android}")
        errors[symbol]?.let { reject(value, language, "Unsupported Android values resource $symbol: $it") }
        val supported = when (expected) {
            StringResourceKind.STRING -> symbol in variants["base"].orEmpty()
            StringResourceKind.PLURAL -> symbol in pluralVariants["base"].orEmpty()
            StringResourceKind.ARRAY -> symbol in arrayVariants["base"].orEmpty()
        }
        if (!supported) reject(value, language, "Unmapped ${expected.android} resource: $symbol; supply materialized --string-resources")
    }

    private fun targetId(symbol: String, source: SourceSpan): EtsExpression {
        used += symbol
        val kind = requireNotNull(StringResourceKind.symbol(symbol))
        val resourceType = EtsNamedType("Resource", external = true)
        val reference = EtsCall(EtsReference(EtsSymbol("arkui:resource", "\$r",
            EtsFunctionType(listOf(EtsTypes.STRING), resourceType), source, true)),
            listOf(EtsLiteral("app.${kind.target}.${name(symbol)}", EtsTypes.STRING, source)), resourceType, source)
        return EtsMember(reference, "id", EtsTypes.NUMBER, source, "arkui:Resource.id")
    }

    private fun read(id: EtsExpression): EtsExpression {
        val source = id.source
        val contextType = EtsNamedType("Context")
        val context = EtsCall(EtsReference(EtsSymbol("arkui:getContext", "getContext",
            EtsFunctionType(emptyList(), contextType), source, true)), emptyList(), contextType, source)
        val manager = EtsMember(context, "resourceManager", EtsNamedType("ResourceManager"), source)
        return EtsCall(EtsMember(manager, "getStringSync", EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.STRING), source,
            "arkui:ResourceManager.getStringSync"), listOf(id), EtsTypes.STRING, source)
    }

    private fun reject(value: IrExpression, language: Language, message: String): Nothing =
        throw Unsupported(Diagnostic("UNSUPPORTED", message, language.source(value)))
}
