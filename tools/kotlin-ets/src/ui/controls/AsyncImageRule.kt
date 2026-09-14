@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.net.URI
import org.jetbrains.kotlin.ir.expressions.*

/** Bounded Coil 2 URL overload. No request construction, loader or callbacks are discarded. */
internal class ComposeAsyncImageRule(
    private val target: ArkUiCalls,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) != "coil.compose.AsyncImage") return null
        target.checkArguments(call, setOf("model", "contentDescription", "modifier", "contentScale", "alpha"))
        val model = argument(call, "model") ?: target.diagnostics.unsupported(call, "AsyncImage requires model")
        val url = model as? IrConst ?: target.diagnostics.unsupported(model,
            "AsyncImage currently requires a literal HTTP(S) URL; request objects and dynamic models need loader adaptation")
        val address = url.value as? String
        val uri = address?.let { runCatching { URI(it) }.getOrNull() }
        if (uri == null || uri.scheme !in setOf("http", "https") || uri.host.isNullOrBlank() || uri.userInfo != null)
            target.diagnostics.unsupported(model, "AsyncImage requires an HTTP(S) URL without embedded credentials")
        val attrs = imageDescription(call, language, scope, target).toMutableList()
        val scale = argument(call, "contentScale")?.let { imageScale(it, scope, target) } ?: "Contain"
        attrs += target.attribute("objectFit", listOf(target.enumValue("ImageFit", scale, call)), call)
        argument(call, "alpha")?.let { attrs += target.attribute("opacity", listOf(language.expression(it, scope)), call) }
        return ComposeElement(target.native("Image", listOf(target.literal(address!!, model)), call).copy(attributes = attrs))
    }
}
