@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.net.URI
import org.jetbrains.kotlin.ir.expressions.*

/** Coil 2 request descriptors are consumed by an owned native loading component. */
internal class ComposeAsyncImageRule(
    private val target: ArkUiCalls,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) != "coil.compose.AsyncImage") return null
        target.checkArguments(call, setOf("model", "contentDescription", "modifier", "contentScale", "alpha", "placeholder"))
        val model = argument(call, "model") ?: target.diagnostics.unsupported(call, "AsyncImage requires model")
        val address = (model as? IrConst)?.value as? String
        if (address != null) {
            val uri = runCatching { URI(address) }.getOrNull()
            if (uri == null || uri.scheme !in setOf("http", "https") || uri.host.isNullOrBlank() || uri.userInfo != null)
                target.diagnostics.unsupported(model, "AsyncImage requires an HTTP(S) URL without embedded credentials")
        }
        val attrs = imageDescription(call, language, scope, target).toMutableList()
        val scale = argument(call, "contentScale")?.let { language.expression(it, scope) } ?: target.enumValue("ImageFit", "Contain", call)
        argument(call, "alpha")?.let { attrs += target.attribute("opacity", listOf(language.expression(it, scope)), call) }
        if (address != null && argument(call, "placeholder") == null) {
            attrs += target.attribute("objectFit", listOf(scale), call)
            return ComposeElement(target.native("Image", listOf(target.literal(address, model)), call).copy(attributes = attrs))
        }
        val at = language.source(call)
        val value = language.expression(model, scope)
        val request = if (value.type == imageRequestType) value else {
            if (!etsAssignable(value.type, EtsNullableType(EtsTypes.STRING)))
                target.diagnostics.unsupported(model, "AsyncImage requires a string/null model or a supported ImageRequest")
            EtsNew(imageRequestType, listOf(value, EtsLiteral(0, EtsTypes.NUMBER, at), EtsLiteral(null, EtsTypes.NULL, at)), at)
        }
        val placeholder = argument(call, "placeholder")?.let { language.expression(it, scope) } ?: EtsLiteral(null, EtsTypes.NULL, at)
        if (!etsAssignable(placeholder.type, EtsNullableType(ImageResources.RESOURCE)))
            target.diagnostics.unsupported(call, "AsyncImage placeholder requires a supported resource Painter or null")
        val child = EtsUiComponent(EtsReference(asyncImageSymbol, at), linkedMapOf(
            "request" to request, "placeholder" to placeholder, "fit" to scale), at)
        return ComposeElement(target.native("Stack", listOf(target.stackOptions(call)), call, listOf(child)).copy(attributes = attrs),
            orderedArguments = listOf(request, placeholder), requiresBoundedSize = true)
    }
}
