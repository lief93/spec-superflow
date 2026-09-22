@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import dev.ets.widgets.ColorTransform
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

private val colorTransformSource = SourceSpan("EtsColorTransform.kt", 0, 0)
private val optionalColorChannelType = EtsNullableType(EtsTypes.NUMBER)
private val colorCopy = etsFunctionSymbol("__etsCopyColor", listOf(EtsTypes.NUMBER,
    optionalColorChannelType, optionalColorChannelType, optionalColorChannelType, optionalColorChannelType),
    EtsTypes.NUMBER, colorTransformSource)

/** sRGB Color values use the unsigned ARGB representation accepted by ArkUI. */
internal class ComposeColorValueRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        return if (symbolName(owner) == colorType && sourceFile(owner) == null) EtsTypes.NUMBER else null
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val name = symbolName(owner)
        val at = language.source(call)
        fun number(value: Long) = EtsLiteral(value, EtsTypes.NUMBER, at)
        val property = owner.correspondingPropertySymbol?.owner?.let(::symbolName)
        colors.entries.firstOrNull { property == "$colorType.Companion.${it.key}" }?.let {
            return number(it.value)
        }
        if (property == "$colorType.Companion.Unspecified") throw Unsupported(Diagnostic(
            "UNSUPPORTED", "Color.Unspecified requires inherited/default color selection; it is not an ARGB value", at))
        if (name == colorType && owner.valueParameters.size == 1) {
            val value = call.getValueArgument(0) ?: return null
            return when (owner.valueParameters.single().type.classOrNull?.owner?.let(::symbolName)) {
                "kotlin.Int" -> EtsBinary(">>>", language.expression(value, scope), number(0), EtsTypes.NUMBER, at)
                // Color(Long) uses only the low 32 bits; do not route it through
                // a lossy general Long-to-number conversion.
                "kotlin.Long" -> (value as? IrConst)?.value?.let { it as? Long }?.let {
                    number(it and 0xFFFFFFFFL)
                }
                else -> null
            }
        }
        if (name == "androidx.compose.ui.graphics.toArgb" && owner.valueParameters.isEmpty()) {
            val receiver = call.extensionReceiver ?: return null
            if (receiver.type.classOrNull?.owner?.let(::symbolName) != colorType) return null
            return EtsBinary("|", language.expression(receiver, scope), number(0), EtsTypes.NUMBER, at)
        }
        if (name == "$colorType.copy") {
            val parameters = owner.valueParameters
            val receiver = call.dispatchReceiver
            if (parameters.map { it.name.asString() } != listOf("alpha", "red", "green", "blue") ||
                parameters.any { !it.type.isFloat() } || owner.extensionReceiverParameter != null ||
                owner.dispatchReceiverParameter?.type?.classOrNull?.owner?.let(::symbolName) != colorType ||
                owner.returnType.classOrNull?.owner?.let(::symbolName) != colorType ||
                call.type.classOrNull?.owner?.let(::symbolName) != colorType || receiver == null)
                throw Unsupported(Diagnostic("UNSUPPORTED", "Unsupported Color.copy signature", at))
            val transform = ColorTransform(receiver, argument(call, "alpha"), argument(call, "red"),
                argument(call, "green"), argument(call, "blue"), at)
            return lower(transform, language, scope)
        }
        return null
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        var used = false
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) {
            if (it is EtsReference && it.symbol.id == colorCopy.id) used = true
        } } }
        return if (used) listOf(colorTransformFile()) else emptyList()
    }

    override fun targetImports(program: EtsProgram): List<EtsImport> =
        if (targetFiles(program).isNotEmpty()) listOf(EtsImport("@ohos.arkui.node", "ColorMetrics")) else emptyList()

    private fun lower(transform: ColorTransform<IrExpression, SourceSpan>, language: Language,
        scope: Scope): EtsExpression {
        fun channel(value: IrExpression?) = value?.let { language.expression(it, scope) }
            ?: EtsLiteral(null, EtsTypes.NULL, transform.source)
        return EtsCall(EtsReference(colorCopy, transform.source), listOf(
            language.expression(transform.input, scope), channel(transform.alpha), channel(transform.red),
            channel(transform.green), channel(transform.blue)), EtsTypes.NUMBER, transform.source)
    }
}

private fun colorTransformFile(): EtsFile {
    val at = colorTransformSource
    fun parameter(id: String, name: String, type: EtsType) =
        EtsParameter(EtsSymbol("color-transform:$id", name, type, at))
    val value = parameter("channel:value", "value", EtsTypes.NUMBER)
    val math = EtsReference(EtsSymbol("target:math", "Math", EtsNamedType("Math", external = true), at, true))
    fun mathCall(name: String, arguments: List<EtsExpression>) = EtsCall(EtsMember(math, name,
        EtsFunctionType(List(arguments.size) { EtsTypes.NUMBER }, EtsTypes.NUMBER), at),
        arguments, EtsTypes.NUMBER, at)
    val clamped = mathCall("min", listOf(EtsLiteral(1, EtsTypes.NUMBER, at), mathCall("max",
        listOf(EtsLiteral(0, EtsTypes.NUMBER, at), EtsReference(value.symbol)))))
    val rounded = EtsBinary("|", mathCall("floor", listOf(EtsBinary("+", EtsBinary("*", clamped,
        EtsLiteral(255, EtsTypes.NUMBER, at), EtsTypes.NUMBER, at), EtsLiteral(0.5, EtsTypes.NUMBER, at),
        EtsTypes.NUMBER, at))), EtsLiteral(0, EtsTypes.NUMBER, at), EtsTypes.NUMBER, at)
    val channel = EtsFunction("__etsColorChannel", listOf(value), EtsTypes.NUMBER,
        listOf(EtsReturn(rounded, at)), at)

    val color = parameter("color", "color", EtsTypes.NUMBER)
    val alpha = parameter("alpha", "alpha", optionalColorChannelType)
    val red = parameter("red", "red", optionalColorChannelType)
    val green = parameter("green", "green", optionalColorChannelType)
    val blue = parameter("blue", "blue", optionalColorChannelType)
    val metricsType = EtsNamedType("ColorMetrics", external = true)
    val metricsApi = EtsReference(EtsSymbol("arkui:color-metrics", "ColorMetrics",
        EtsNamedType("ColorMetricsApi", external = true), at, true))
    fun metricsCall(name: String, arguments: List<EtsExpression>, parameters: List<EtsType>) =
        EtsCall(EtsMember(metricsApi, name, EtsFunctionType(parameters, metricsType), at),
            arguments, metricsType, at)
    val source = EtsSymbol("color-transform:source", "source", metricsType, at)
    val result = EtsSymbol("color-transform:result", "result", metricsType, at)
    fun member(symbol: EtsSymbol, name: String) = EtsMember(EtsReference(symbol), name, EtsTypes.NUMBER, at)
    fun selected(parameter: EtsParameter, name: String): EtsExpression {
        val normalized = EtsBinary("??", EtsReference(parameter.symbol),
            EtsBinary("/", member(source, name), EtsLiteral(255, EtsTypes.NUMBER, at), EtsTypes.NUMBER, at),
            EtsTypes.NUMBER, at)
        return EtsCall(EtsReference(channel.symbol), listOf(normalized), EtsTypes.NUMBER, at)
    }
    val outputAlpha = EtsSymbol("color-transform:output-alpha", "outputAlpha", EtsTypes.NUMBER, at)
    val outputRed = EtsSymbol("color-transform:output-red", "outputRed", EtsTypes.NUMBER, at)
    val outputGreen = EtsSymbol("color-transform:output-green", "outputGreen", EtsTypes.NUMBER, at)
    val outputBlue = EtsSymbol("color-transform:output-blue", "outputBlue", EtsTypes.NUMBER, at)
    val rgba = metricsCall("rgba", listOf(EtsReference(outputRed), EtsReference(outputGreen),
        EtsReference(outputBlue), EtsBinary("/", EtsReference(outputAlpha), EtsLiteral(255, EtsTypes.NUMBER, at),
            EtsTypes.NUMBER, at)), listOf(EtsTypes.NUMBER, EtsTypes.NUMBER, EtsTypes.NUMBER, EtsTypes.NUMBER))
    fun weighted(name: String, weight: Long) = EtsBinary("*", member(result, name),
        EtsLiteral(weight, EtsTypes.NUMBER, at), EtsTypes.NUMBER, at)
    val packed = EtsBinary("+", EtsBinary("+", weighted("alpha", 0x1000000), weighted("red", 0x10000),
        EtsTypes.NUMBER, at), EtsBinary("+", weighted("green", 0x100), member(result, "blue"),
        EtsTypes.NUMBER, at), EtsTypes.NUMBER, at)
    val copy = EtsFunction(colorCopy.name, listOf(color, alpha, red, green, blue), EtsTypes.NUMBER, listOf(
        EtsVariable(source, metricsCall("numeric", listOf(EtsReference(color.symbol)), listOf(EtsTypes.NUMBER)), false),
        EtsVariable(outputAlpha, selected(alpha, "alpha"), false),
        EtsVariable(outputRed, selected(red, "red"), false),
        EtsVariable(outputGreen, selected(green, "green"), false),
        EtsVariable(outputBlue, selected(blue, "blue"), false),
        EtsVariable(result, rgba, false), EtsReturn(packed, at)), at, exported = true)
    return EtsFile(at.file!!, listOf(channel, copy))
}

private const val colorType = "androidx.compose.ui.graphics.Color"
private val colors = mapOf(
    "Black" to 0xFF000000L, "DarkGray" to 0xFF444444L, "Gray" to 0xFF888888L,
    "LightGray" to 0xFFCCCCCCL, "White" to 0xFFFFFFFFL, "Red" to 0xFFFF0000L,
    "Green" to 0xFF00FF00L, "Blue" to 0xFF0000FFL, "Yellow" to 0xFFFFFF00L,
    "Cyan" to 0xFF00FFFFL, "Magenta" to 0xFFFF00FFL, "Transparent" to 0L,
)
