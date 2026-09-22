@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import dev.ets.widgets.TypographyContext
import dev.ets.widgets.TypographySlot
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrExpression
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.types.isUnit

internal class ComposeProvideTextStyleRule(private val target: ArkUiCalls,
    private val provide: (EtsExpression, IrExpression, Scope) -> List<EtsStatement>) : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null

    override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null || symbolName(owner) != "androidx.compose.material3.ProvideTextStyle") return null
        val at = language.source(call)
        if (owner.valueParameters.map { it.name.asString() } != listOf("value", "content") ||
            owner.dispatchReceiverParameter != null || owner.extensionReceiverParameter != null || !owner.returnType.isUnit())
            throw Unsupported(Diagnostic("UNSUPPORTED", "Unsupported ProvideTextStyle signature", at))
        target.checkArguments(call, setOf("value", "content"))
        val value = argument(call, "value")
            ?: throw Unsupported(Diagnostic("UNSUPPORTED", "ProvideTextStyle requires value", at))
        if (value.type.classOrNull?.owner?.let(::symbolName) != "androidx.compose.ui.text.TextStyle")
            throw Unsupported(Diagnostic("UNSUPPORTED", "ProvideTextStyle value requires TextStyle", language.source(value)))
        val content = argument(call, "content")
            ?: throw Unsupported(Diagnostic("UNSUPPORTED", "ProvideTextStyle requires content", at))
        val parent = materialContext(scope, at)
        val model = TypographySlot(TypographyContext(materialCurrentTextStyle(parent, at),
            language.expression(value, scope), at), content, at)
        val style = mergeTextStyles(model.context.inheritedStyle, model.context.providedStyle, model.source)
        val context = EtsNew(materialContextType, listOf(materialScheme(parent, at), materialContentColor(parent, at),
            materialTypography(parent, at), style, materialShapes(parent, at)), at)
        return provide(context, model.content, scope)
    }
}
