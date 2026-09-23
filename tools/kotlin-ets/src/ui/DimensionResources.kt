@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import java.util.Properties
import org.jetbrains.kotlin.ir.expressions.*

/** Selected Android dp resources. Unsupported Android qualifiers are explicit report-mode fallbacks. */
internal class DimensionResources(
    private val values: Map<String, Double> = emptyMap(),
    private val ids: Map<String, Int> = emptyMap(),
    private val qualifiers: Map<String, String> = emptyMap(),
) : CallRule {
    companion object {
        private val SYMBOL = Regex("[A-Za-z_][A-Za-z0-9_.]*\\.R\\.dimen\\.[a-z_][a-z0-9_]*")

        private fun properties(file: File): Map<String, String> {
            val result = object : Properties() {
                override fun put(key: Any, value: Any): Any? {
                    require(!containsKey(key)) { "Duplicate dimension resource entry: $key" }
                    return super.put(key, value)
                }
            }
            file.reader(Charsets.UTF_8).use(result::load)
            return result.stringPropertyNames().associateWith(result::getProperty)
        }

        fun read(directory: File): DimensionResources {
            require(directory.isDirectory) { "Dimension resource input must be a directory: $directory" }
            val values = properties(directory.resolve("dimensions.properties")).mapValues { (symbol, value) ->
                require(SYMBOL.matches(symbol)) { "Invalid dimension resource symbol: $symbol" }
                value.toDouble().also { require(it.isFinite()) { "Invalid dimension resource value: $symbol" } }
            }
            val qualifiers = properties(directory.resolve("dimension-qualifiers.properties")).onEach { (symbol, value) ->
                require(symbol in values && value.isNotBlank()) { "Invalid qualified dimension fallback: $symbol" }
            }
            val ids = properties(directory.resolve("source-resource-ids.properties"))
                .filterKeys(SYMBOL::matches).mapValues { (symbol, value) ->
                    require(symbol in values) { "Dimension resource ID has no materialized base value: $symbol" }
                    java.lang.Long.decode(value).also {
                        require(it in 1..Int.MAX_VALUE.toLong()) { "Invalid dimension resource ID: $symbol" }
                    }.toInt()
                }
            return DimensionResources(values, ids, qualifiers)
        }
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        if (symbolName(call.symbol.owner) != "androidx.compose.ui.res.dimensionResource") return null
        val source = argument(call, "id") ?: reject(call, language, "dimensionResource requires id")
        val symbol = symbol(source, scope) ?: ((source as? IrConst)?.value as? Int)?.let { id ->
            ids.entries.singleOrNull { it.value == id }?.key
        } ?: reject(source, language, "Dynamic dimensionResource ID requires selected-build dimension metadata")
        val value = values[symbol] ?: reject(source, language, "Unmapped dimension resource: $symbol")
        qualifiers[symbol]?.let { variants ->
            language.diagnostics?.omitUi(call,
                "Android dimension qualifiers are unavailable on the target: $symbol ($variants)",
                symbol, "dimension_qualifier_fallback",
                "The target uses the selected resource's base dp value; qualified Android widths are not applied.",
                discarded = emptyList())
                ?: reject(call, language, "Dimension fallback requires diagnostics")
        }
        return EtsLiteral(value, EtsTypes.NUMBER, language.source(call))
    }

    private fun symbol(value: IrExpression, scope: Scope): String? {
        if (value is IrGetValue && value.symbol !in scope.bindings)
            scope.aliases[value.symbol]?.let { return symbol(it, scope) }
        return (value as? IrGetField)?.takeIf { it.receiver == null }?.symbol?.owner?.let(::symbolName)
            ?.takeIf(SYMBOL::matches)
    }

    private fun reject(value: IrExpression, language: Language, message: String): Nothing =
        throw Unsupported(Diagnostic("UNSUPPORTED", message, language.source(value)))
}
