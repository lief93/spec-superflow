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
) : CallRule {
    private val used = linkedSetOf<String>()

    companion object {
        fun read(directory: File): StringResources {
            require(directory.isDirectory) { "String resource input must be a directory: $directory" }
            val packs = directory.listFiles().orEmpty().filter { it.extension == "properties" }.associate { file ->
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
            return StringResources(packs - "unsupported", packs["unsupported"].orEmpty())
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
        if (call.symbol.owner.valueParameters.size != 1) reject(call, language, "Formatted stringResource is not supported")
        return resource(argument(call, "id") ?: reject(call, language, "stringResource requires id"), language, scope)
    }

    private fun resource(value: IrExpression, language: Language, scope: Scope): EtsExpression {
        if (value is IrGetValue) scope.aliases[value.symbol]?.let { return resource(it, language, scope) }
        if (value is IrWhen && value.branches.size == 2 && value.branches.last() is IrElseBranch) {
            return EtsConditional(language.expression(value.branches[0].condition, scope),
                resource(value.branches[0].result, language, scope), resource(value.branches[1].result, language, scope),
                EtsTypes.STRING, language.source(value))
        }
        val symbol = (value as? IrGetField)?.takeIf { it.receiver == null }?.symbol?.owner?.let(::symbolName)
            ?: reject(value, language, "String resource IDs must retain their resolved R symbol")
        errors[symbol]?.let { reject(value, language, "Unsupported string resource $symbol: $it") }
        if (symbol !in variants["base"].orEmpty()) reject(value, language,
            "Unmapped string resource: $symbol; supply --string-resources input directory")
        used += symbol
        val at = language.source(value)
        val resourceType = EtsNamedType("Resource")
        val reference = EtsCall(EtsReference(EtsSymbol("arkui:resource", "\$r",
            EtsFunctionType(listOf(EtsTypes.STRING), resourceType), at, true)),
            listOf(EtsLiteral("app.string.${name(symbol)}", EtsTypes.STRING, at)), resourceType, at)
        val contextType = EtsNamedType("Context")
        val context = EtsCall(EtsReference(EtsSymbol("arkui:getContext", "getContext",
            EtsFunctionType(emptyList(), contextType), at, true)), emptyList(), contextType, at)
        val manager = EtsMember(context, "resourceManager", EtsNamedType("ResourceManager"), at)
        return EtsCall(EtsMember(manager, "getStringSync", EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.STRING), at),
            listOf(EtsMember(reference, "id", EtsTypes.NUMBER, at)), EtsTypes.STRING, at)
    }

    private fun reject(value: IrExpression, language: Language, message: String): Nothing =
        throw Unsupported(Diagnostic("UNSUPPORTED", message, language.source(value)))
}
