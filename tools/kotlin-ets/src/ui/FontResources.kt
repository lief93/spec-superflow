@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import java.security.MessageDigest
import java.util.Properties
import org.jetbrains.kotlin.ir.expressions.*

/** A selected module's font directory, not a scan of arbitrary project sources. */
class FontResources(private val files: Map<String, File> = emptyMap()) {
    private val used = linkedSetOf<String>()
    companion object {
        fun read(file: File): FontResources {
            val properties = object : Properties() {
                override fun put(key: Any, value: Any): Any? {
                    require(!containsKey(key)) { "Duplicate font resource symbol: $key" }
                    return super.put(key, value)
                }
            }
            file.reader(Charsets.UTF_8).use(properties::load)
            return FontResources(properties.stringPropertyNames().associateWith { symbol ->
                require(Regex("[A-Za-z_][A-Za-z0-9_.]*\\.R\\.font\\.[A-Za-z_][A-Za-z0-9_]*").matches(symbol)) {
                    "Invalid font resource symbol: $symbol"
                }
                val relative = properties.getProperty(symbol)
                require(!File(relative).isAbsolute && relative.split('/', '\\').none { it == ".." }) {
                    "Font resource must remain inside the input directory: $symbol"
                }
                file.parentFile.resolve(relative).canonicalFile.also { target ->
                    require(target.toPath().startsWith(file.parentFile.canonicalFile.toPath())) {
                        "Font resource escapes input directory: $symbol"
                    }
                }
            })
        }
    }

    fun artifacts(): Map<String, File> = used.associate { symbol ->
        "rawfile/${targetName(symbol, files.getValue(symbol))}" to files.getValue(symbol)
    }

    fun resolve(expression: IrExpression, language: Language, scope: Scope): String {
        if (expression is IrGetValue) scope.aliases[expression.symbol]?.let { return resolve(it, language, scope) }
        val symbol = (expression as? IrGetField)?.takeIf { it.receiver == null }?.symbol?.owner?.let(::symbolName)
        val file = files[symbol] ?: throw Unsupported(Diagnostic("UNSUPPORTED",
            "Unmapped font resource: ${symbol ?: "requires a resolved R.font symbol"}; supply --font-resources", language.source(expression)))
        if (!file.isFile || file.extension.lowercase() !in setOf("ttf", "otf")) throw Unsupported(Diagnostic("UNSUPPORTED",
            "Font resource requires an existing TTF/OTF file: $symbol", language.source(expression)))
        used += symbol!!
        return targetName(symbol, file)
    }

    private fun targetName(symbol: String, file: File): String = "font_" + MessageDigest.getInstance("SHA-256")
        .digest(symbol.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) } + "." + file.extension.lowercase()
}
