@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.irAttribute
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.hasAnnotation
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.name.FqName

private val staticAnimationSource = SourceSpan("EtsStaticAnimation.kt", 0, 0)
private val staticAnimationType = etsClassSymbol("EtsStaticAnimation", staticAnimationSource).type as EtsNamedType
private var IrCall.staticAnimationReported: Boolean? by irAttribute(followAttributeOwner = true)

private fun floatAnimation(type: IrType): Boolean {
    val owner = type.classOrNull?.owner ?: return false
    return sourceFile(owner) == null && symbolName(owner) == "androidx.compose.animation.core.Animatable" &&
        ((type as? IrSimpleType)?.arguments?.firstOrNull() as? IrTypeProjection)?.type?.isFloat() == true
}

private fun animationFactory(call: IrCall): Boolean = sourceFile(call.symbol.owner) == null &&
    symbolName(call.symbol.owner) == "androidx.compose.animation.core.Animatable" && floatAnimation(call.type)

/** A reported static value holder, not an animation engine or a remembered state object. */
internal class ComposeStaticAnimationRule(private val diagnostics: DiagnosticSink) : CallRule {
    override fun prepareSource(declaration: IrDeclaration, diagnostics: DiagnosticSink) {
        if (!diagnostics.reportUiDegradation) return
        val previous = diagnostics.currentFile
        diagnostics.currentFile = sourceFile(declaration)?.fileEntry?.name
        try {
            declaration.acceptVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
                override fun visitSimpleFunction(declaration: IrSimpleFunction) {
                    if (declaration.hasAnnotation(FqName("androidx.compose.runtime.Composable")))
                        (declaration.body as? IrBlockBody)?.let(::project)
                    declaration.acceptChildrenVoid(this)
                }
            })
        } finally { diagnostics.currentFile = previous }
    }

    override fun mapType(type: IrType, language: Language): EtsType? =
        if (diagnostics.reportUiDegradation && floatAnimation(type)) staticAnimationType else null

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        if (!diagnostics.reportUiDegradation || sourceFile(call.symbol.owner) != null) return null
        if (animationFactory(call)) {
            val initial = argument(call, "initialValue") ?: return null
            if (call.staticAnimationReported != true) record(call, "Animation motion is omitted; the explicit initial Float value is retained")
            return EtsNew(staticAnimationType, listOf(language.expression(initial, scope)), language.source(call))
        }
        val property = call.symbol.owner.correspondingPropertySymbol?.owner ?: return null
        val receiver = call.dispatchReceiver ?: return null
        if (property.getter?.symbol == call.symbol && property.name.asString() == "value" && floatAnimation(receiver.type))
            return EtsMember(language.expression(receiver, scope), "value", EtsTypes.NUMBER, language.source(call))
        return null
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        var used = false
        program.files.forEach { it.declarations.forEach { declaration -> walkEts(declaration) {
            if (it is EtsNew && it.type == staticAnimationType) used = true
        } } }
        if (!used) return emptyList()
        val at = staticAnimationSource
        val value = EtsSymbol("static-animation:value", "value", EtsTypes.NUMBER, at)
        val initial = EtsParameter(EtsSymbol("static-animation:initial", "initialValue", EtsTypes.NUMBER, at))
        val self = EtsReference(EtsSymbol("static-animation:this", "this", staticAnimationType, at, external = true))
        val constructor = EtsFunction("constructor", listOf(initial), EtsTypes.VOID, listOf(EtsExpressionStatement(
            EtsAssignment(EtsMember(self, "value", EtsTypes.NUMBER, at, value.id), EtsReference(initial.symbol), at))),
            at, kind = EtsFunctionKind.CONSTRUCTOR)
        return listOf(EtsFile(at.file!!, listOf(EtsClass(staticAnimationType.name,
            listOf(EtsField(value, readonly = true), constructor), at, exported = true))))
    }

    private fun record(call: IrCall, impact: String) {
        diagnostics.omitUi(call, "Animatable is displayed without animation", "androidx.compose.animation.core.Animatable",
            "static_animation_value", impact, discarded = emptyList())
        call.staticAnimationReported = true
    }

    private fun project(body: IrBlockBody) {
        var hasAnimation = false
        body.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrCall && animationFactory(element)) hasAnimation = true
                element.acceptChildrenVoid(this)
            }
        })
        if (!hasAnimation) return
        val originalReads = projectionLocalReads(body)
        fun effectsOnly(node: IrElement): Boolean = when (node) {
            is IrCall -> if (sourceFile(node.symbol.owner) != null) false else when (symbolName(node.symbol.owner)) {
                "androidx.compose.runtime.LaunchedEffect" -> true
                "kotlin.collections.forEach", "kotlin.collections.forEachIndexed", "kotlin.repeat" -> {
                    val action = argument(node, "action") as? IrFunctionExpression
                    val statements = (action?.function?.body as? IrBlockBody)?.statements
                    statements != null && statements.isNotEmpty() && statements.all(::effectsOnly)
                }
                else -> false
            }
            is IrWhen -> node.branches.all { effectsOnly(it.result) }
            is IrContainerExpression -> node.statements.all(::effectsOnly)
            is IrGetObjectValue -> node.type.isUnit()
            else -> false
        }
        body.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                val statements = when (element) {
                    is IrBlockBody -> element.statements
                    is IrContainerExpression -> element.statements
                    else -> null
                }
                statements?.removeAll { statement ->
                    if (statement !is IrGetObjectValue && effectsOnly(statement)) {
                        diagnostics.omitUi(statement, "Animation launch and its enclosing effect-only control flow omitted",
                            "androidx.compose.runtime.LaunchedEffect", "omitted_animation_effect",
                            "No animation coroutine, key/guard/iteration evaluation or callback is executed; static UI remains.")
                        true
                    } else false
                }
                element.acceptChildrenVoid(this)
            }
        })
        body.transformChildrenVoid(object : IrElementTransformerVoid() {
            override fun visitCall(expression: IrCall): IrExpression {
                val external = sourceFile(expression.symbol.owner) == null
                val api = symbolName(expression.symbol.owner)
                if (external && api == "androidx.compose.ui.graphics.graphicsLayer" && argument(expression, "block") != null) {
                    val receiver = expression.extensionReceiver
                    if (receiver != null) {
                        diagnostics.omitUi(expression, "graphicsLayer block omitted in static animation projection", api,
                            "omitted_modifier", "Layer transformations and their private local dependencies are not evaluated; other modifiers remain.",
                            expression.symbol.owner.valueParameters.indices.mapNotNull { expression.getValueArgument(it) })
                        return receiver.transform(this, null)
                    }
                }
                if (external && api == "androidx.compose.runtime.remember" &&
                    expression.symbol.owner.valueParameters.map { it.name.asString() } == listOf("calculation")) {
                    val fn = (argument(expression, "calculation") as? IrFunctionExpression)?.function
                    val result = (fn?.body as? IrBlockBody)?.statements?.singleOrNull()
                    val value = if (result is IrReturn && result.returnTargetSymbol == fn.symbol) result.value else result
                    if (value is IrCall && animationFactory(value)) {
                        record(value, "Animation and remember caching are omitted. Evaluate the explicit initial Float value when the static UI is composed.")
                        return value.transform(this, null)
                    }
                }
                return super.visitCall(expression)
            }
        })
        pruneProjectedLocals(body, originalReads, diagnostics)
    }
}
