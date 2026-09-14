@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import java.util.Properties
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

/** Resource names come from materialization, never from an integer R value or source spelling. */
class ImageResources(private val resources: Map<String, String> = emptyMap()) : CallRule {
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
            resources.forEach { (symbol, name) ->
                require(Regex("[A-Za-z_][A-Za-z0-9_.]*\\.R\\.(drawable|mipmap)\\.[A-Za-z_][A-Za-z0-9_]*").matches(symbol)) {
                    "Invalid image resource symbol: $symbol"
                }
                require(Regex("[a-z][a-z0-9_]*").matches(name)) { "Invalid target media name: $name" }
                val files = file.parentFile.resolve("media").listFiles().orEmpty().filter { it.nameWithoutExtension == name }
                require(files.size == 1 && files.single().isFile && files.single().extension in setOf("png", "jpg", "jpeg", "webp", "svg")) {
                    "Image resource has no unique materialized media file: $symbol"
                }
            }
            return ImageResources(resources)
        }
    }

    override fun mapType(type: IrType, language: Language): EtsType? =
        if (type.classFqName?.asString() == "androidx.compose.ui.graphics.painter.Painter") RESOURCE else null

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        if (symbolName(call.symbol.owner) != "androidx.compose.ui.res.painterResource") return null
        val id = argument(call, "id") ?: reject(call, language, "painterResource requires id")
        return resource(id, language, scope)
    }

    private fun resource(value: IrExpression, language: Language, scope: Scope): EtsExpression {
        if (value is IrGetValue) scope.aliases[value.symbol]?.let { return resource(it, language, scope) }
        if (value is IrWhen && value.branches.size == 2 && value.branches.last() is IrElseBranch) {
            return EtsConditional(language.expression(value.branches[0].condition, scope),
                resource(value.branches[0].result, language, scope), resource(value.branches[1].result, language, scope),
                RESOURCE, language.source(value))
        }
        val symbol = when (value) {
            is IrGetField -> if (value.receiver == null) symbolName(value.symbol.owner) else null
            else -> null
        }
        val name = resources[symbol] ?: reject(value, language,
            "Unmapped image resource: ${symbol ?: "resource IDs must retain their resolved R symbol"}; supply materialized --image-resources")
        val source = language.source(value)
        val function = EtsReference(EtsSymbol("arkui:resource", "\$r", EtsFunctionType(listOf(EtsTypes.STRING), RESOURCE), source, true))
        return EtsCall(function, listOf(EtsLiteral("app.media.$name", EtsTypes.STRING, source)), RESOURCE, source)
    }

    private fun reject(value: IrExpression, language: Language, message: String): Nothing =
        throw Unsupported(Diagnostic("UNSUPPORTED", message, language.source(value)))
}
