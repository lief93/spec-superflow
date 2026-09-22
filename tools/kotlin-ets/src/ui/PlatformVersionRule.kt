@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.expressions.impl.IrConstImpl
import org.jetbrains.kotlin.ir.irAttribute
import org.jetbrains.kotlin.ir.types.isBoolean
import org.jetbrains.kotlin.ir.types.isUnit
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.IrElementTransformerVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid
import org.jetbrains.kotlin.ir.visitors.acceptVoid
import org.jetbrains.kotlin.ir.visitors.transformChildrenVoid
import java.util.Collections
import java.util.IdentityHashMap

private const val androidSdkInt = "android.os.Build.VERSION.SDK_INT"
private const val androidVersionCodes = "android.os.Build.VERSION_CODES."

internal sealed interface PlatformCapabilityDecision {
    data class TargetMapping(val capability: String) : PlatformCapabilityDecision
    data class Fallback(val capability: String) : PlatformCapabilityDecision
}

internal var IrCall.platformCapabilityDecision: PlatformCapabilityDecision? by
    irAttribute(followAttributeOwner = false)

private val comparisons = setOf(
    "kotlin.internal.ir.eqeq", "kotlin.internal.ir.less", "kotlin.internal.ir.lessorequal",
    "kotlin.internal.ir.greater", "kotlin.internal.ir.greaterorequal",
)

private fun directAndroidVersionPredicate(call: IrCall): Boolean {
    if (!call.type.isBoolean()) return false
    var sdkReads = 0
    var invalidAndroidReference = false
    call.acceptChildrenVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            if (element is IrGetField && sourceFile(element.symbol.owner) == null) {
                val name = symbolName(element.symbol.owner)
                if (name == androidSdkInt) sdkReads++
                else if (!name.startsWith(androidVersionCodes) && name.startsWith("android."))
                    invalidAndroidReference = true
            }
            if (element is IrCall && sourceFile(element.symbol.owner) == null) {
                val name = symbolName(element.symbol.owner)
                if (name.startsWith("android.") && !name.startsWith(androidVersionCodes))
                    invalidAndroidReference = true
            }
            element.acceptChildrenVoid(this)
        }
    })
    return sdkReads == 1 && !invalidAndroidReference && symbolName(call.symbol.owner).lowercase() in comparisons
}

private fun returnedExpression(function: IrSimpleFunction): IrExpression? = when (val body = function.body) {
    is IrExpressionBody -> body.expression
    is IrBlockBody -> (body.statements.singleOrNull() as? IrReturn)?.value
    else -> null
}

private fun sourceAndroidVersionPredicate(call: IrCall, visiting: MutableSet<IrSimpleFunction>): Boolean {
    val function = call.symbol.owner
    if (sourceFile(function) == null || function.dispatchReceiverParameter != null ||
        function.extensionReceiverParameter != null || function.valueParameters.isNotEmpty() ||
        !function.returnType.isBoolean() || !visiting.add(function)) return false
    val result = returnedExpression(function)
    val matches = result is IrCall && (directAndroidVersionPredicate(result) || sourceAndroidVersionPredicate(result, visiting))
    visiting.remove(function)
    return matches
}

/** Resolved calls that represent Android platform-version predicates, following immutable local aliases. */
internal fun androidVersionPredicates(element: IrElement): List<IrCall> {
    val found = mutableListOf<IrCall>()
    val seen = Collections.newSetFromMap(IdentityHashMap<IrCall, Boolean>())
    val visitedValues = Collections.newSetFromMap(IdentityHashMap<IrValueDeclaration, Boolean>())
    fun visit(value: IrElement) {
        value.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                when (element) {
                    is IrCall -> if (directAndroidVersionPredicate(element) ||
                        sourceAndroidVersionPredicate(element, Collections.newSetFromMap(IdentityHashMap()))) {
                        if (seen.add(element)) found += element
                        return
                    }
                    is IrGetValue -> {
                        val declaration = element.symbol.owner
                        val initializer = (declaration as? IrVariable)?.takeUnless { it.isVar }?.initializer
                        if (initializer != null && visitedValues.add(declaration)) visit(initializer)
                    }
                }
                element.acceptChildrenVoid(this)
            }
        })
    }
    visit(element)
    return found
}

private fun emptyUnitFallback(value: IrExpression): Boolean = when (value) {
    is IrGetObjectValue -> value.type.isUnit()
    is IrConst -> value.type.isUnit()
    is IrContainerExpression -> value.statements.all { it is IrExpression && emptyUnitFallback(it) }
    else -> false
}

/** Declared target policy for Android platform-version guards. */
internal class ComposePlatformVersionRule : CallRule {
    override fun prepareSource(declaration: IrDeclaration, diagnostics: DiagnosticSink) {
        val previousFile = diagnostics.currentFile
        diagnostics.currentFile = sourceFile(declaration)?.fileEntry?.name
        try {
            declaration.acceptVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) {
                    if (element in diagnostics.omittedUiElements) return
                    if (element is IrWhen) {
                        val predicates = element.branches.flatMap { branch ->
                            if (branch is IrElseBranch) emptyList() else androidVersionPredicates(branch.condition)
                        }.distinct()
                        if (predicates.isNotEmpty()) {
                            val fallback = (element.branches.lastOrNull() as? IrElseBranch)?.result
                            for (predicate in predicates) {
                                if (predicate.platformCapabilityDecision != null) continue
                                if (fallback == null || emptyUnitFallback(fallback))
                                    diagnostics.unsupported(predicate,
                                        "Android SDK_INT platform-version guard requires a target capability mapping or a meaningful fallback")
                                val capability = "android.platform.version"
                                predicate.platformCapabilityDecision = PlatformCapabilityDecision.Fallback(capability)
                                diagnostics.omitUi(predicate,
                                    "Android SDK_INT platform-version guard selected its fallback through the declared target capability policy",
                                    capability, "platform_capability_fallback",
                                    "The target does not expose an Android SDK level. The guarded source-platform branch is unavailable; its fallback is retained, and surrounding non-platform conditions keep their source evaluation order.",
                                    discarded = listOf(predicate))
                            }
                        }
                    }
                    element.acceptChildrenVoid(this)
                }
            })
            declaration.transformChildrenVoid(object : IrElementTransformerVoid() {
                override fun visitCall(expression: IrCall): IrExpression {
                    when (expression.platformCapabilityDecision) {
                        is PlatformCapabilityDecision.Fallback ->
                            return IrConstImpl.constFalse(expression.startOffset, expression.endOffset, expression.type)
                        is PlatformCapabilityDecision.TargetMapping ->
                            return IrConstImpl.constTrue(expression.startOffset, expression.endOffset, expression.type)
                        null -> Unit
                    }
                    return super.visitCall(expression)
                }
            })
        } finally {
            diagnostics.currentFile = previousFile
        }
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        return when (val decision = call.platformCapabilityDecision) {
            is PlatformCapabilityDecision.Fallback -> EtsLiteral(false, EtsTypes.BOOLEAN, language.source(call))
            is PlatformCapabilityDecision.TargetMapping -> EtsLiteral(true, EtsTypes.BOOLEAN, language.source(call))
            null -> null
        }
    }
}
