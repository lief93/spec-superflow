@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

/** Request values are separate from native loading and never reduced to their URL. */
internal class CoilImageRequestRule : CallRule {
    override fun targetFiles(program: EtsProgram) = imageRequestValueFiles(program)
    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        if (sourceFile(owner) != null) return null
        return when (symbolName(owner)) {
            "coil.request.ImageRequest" -> imageRequestType
            "coil.request.ImageRequest.Builder" -> imageRequestBuilderType
            "coil.decode.Decoder.Factory", "coil.decode.SvgDecoder.Factory" -> svgDecoderType
            else -> null
        }
    }
    override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner.parent as IrClass
        if (sourceFile(owner) != null) return null
        val at = language.source(call)
        return when (symbolName(owner)) {
            "coil.request.ImageRequest.Builder" -> {
                if (call.symbol.owner.valueParameters.map { it.name.asString() } != listOf("context"))
                    reject(call, language, "ImageRequest builder copying is not supported")
                val context = argument(call, "context") as? IrCall
                val current = context?.symbol?.owner?.correspondingPropertySymbol?.owner?.let(::symbolName)
                val local = (context?.dispatchReceiver as? IrCall)?.symbol?.owner?.correspondingPropertySymbol?.owner?.let(::symbolName)
                if (current !in setOf("androidx.compose.runtime.CompositionLocal.current", "androidx.compose.runtime.ProvidableCompositionLocal.current") ||
                    local != "androidx.compose.ui.platform.LocalContext")
                    reject(call, language, "ImageRequest requires direct LocalContext.current; arbitrary Context must be adapted explicitly")
                // Native loading owns this ambient platform context. No source Context-producing call is discarded.
                EtsNew(imageRequestBuilderType, emptyList(), at)
            }
            "coil.decode.SvgDecoder.Factory" -> {
                if (call.symbol.owner.valueParameters.indices.any { call.getValueArgument(it) != null })
                    reject(call, language, "SvgDecoder requires default intrinsic-size behavior")
                EtsNew(svgDecoderType, emptyList(), at)
            }
            else -> null
        }
    }
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val parent = owner.parent as? IrClass ?: return null
        if (symbolName(parent) != "coil.request.ImageRequest.Builder") return null
        val name = owner.name.asString()
        if (name !in setOf("data", "decoderFactory", "crossfade", "build")) return null
        val receiver = call.dispatchReceiver ?: reject(call, language, "ImageRequest builder requires receiver")
        val targetReceiver = language.expression(receiver, scope)
        val arguments = owner.valueParameters.mapIndexed { index, parameter ->
            val input = call.getValueArgument(index) ?: reject(call, language, "Missing request argument ${parameter.name}")
            val value = language.expression(input, scope)
            when (name) {
                "data" -> {
                    if (!etsAssignable(value.type, EtsNullableType(EtsTypes.STRING)))
                        reject(input, language, "ImageRequest data supports string/null values; other loader models require adaptation")
                    value
                }
                "crossfade" -> when (value.type) {
                    EtsTypes.BOOLEAN -> EtsConditional(value, EtsLiteral(100, EtsTypes.NUMBER, language.source(input)),
                        EtsLiteral(0, EtsTypes.NUMBER, language.source(input)), EtsTypes.NUMBER, language.source(input))
                    EtsTypes.NUMBER -> value
                    else -> reject(input, language, "Invalid crossfade argument")
                }
                else -> value
            }
        }
        val result = if (name == "build") imageRequestType else imageRequestBuilderType
        val types = when (name) {
            "data" -> listOf(EtsNullableType(EtsTypes.STRING))
            "decoderFactory" -> listOf(svgDecoderType)
            "crossfade" -> listOf(EtsTypes.NUMBER)
            else -> emptyList()
        }
        val at = language.source(call)
        return EtsCall(EtsMember(targetReceiver, name, EtsFunctionType(types, result), at), arguments, result, at)
    }
    private fun reject(value: IrExpression, language: Language, message: String): Nothing =
        throw Unsupported(Diagnostic("UNSUPPORTED", message, language.source(value)))
}
